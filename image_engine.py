"""HWPX image extraction and conversion. No Hancom automation required."""
from __future__ import annotations

import csv
import io
import math
import os
import re
import threading
import time
import warnings
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Callable
from collections import deque
from concurrent.futures import ThreadPoolExecutor, Future

from PIL import Image, ImageOps, features

FORMATS = {'JPEG': '.jpg', 'PNG': '.png', 'WEBP': '.webp', 'TIFF': '.tif',
           'BMP': '.bmp', 'GIF': '.gif', 'ICO': '.ico'}
DPI_FORMATS = {'JPEG', 'PNG', 'TIFF', 'BMP', 'WEBP'}
VECTOR_EXTS = {'.svg', '.wmf', '.emf'}
MAX_MEMBER_BYTES = 256 * 1024 * 1024
MAX_OUTPUT_PIXELS = 80_000_000
CONVERSION_MEMORY_BUDGET = 512 * 1024 * 1024
_RASTER_HEADER_LOCK = threading.RLock()


class Cancelled(Exception):
    pass


def checkpoint(cancel: threading.Event | None):
    if cancel is not None and cancel.is_set():
        raise Cancelled('사용자가 중지했습니다.')


def human_location(location: str) -> str:
    return re.sub(r'(?:BodyText/)?[sS]ection(\d+)', lambda m: f'구역 {int(m.group(1)) + 1}', location or '')


def validate_archive_member(name: str) -> str:
    norm = (name or '').replace('\\', '/')
    parts = PurePosixPath(norm).parts
    if not norm or norm.startswith('/') or '..' in parts or any(':' in p for p in parts):
        raise ValueError(f'안전하지 않은 문서 내부 경로입니다: {name}')
    return norm


def safe_name(name: str) -> str:
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name).strip(' .')[:100] or 'image'
    if text.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}:
        text = '_' + text
    return text


def image_members(archive: zipfile.ZipFile):
    members = [m for m in archive.infolist() if not m.is_dir() and
               PurePosixPath(m.filename).parts and PurePosixPath(m.filename).parts[0].lower() == 'bindata']
    return sorted(members, key=lambda m: [int(s) if s.isdigit() else s.lower() for s in re.split(r'(\d+)', m.filename)])


@dataclass(frozen=True)
class Settings:
    format: str = 'JPEG'  # ORIGINAL preserves embedded bytes
    dpi: int | None = None
    resize: str = 'original'  # original, percent, long_edge, fit
    percent: int = 100
    width: int = 1920
    height: int = 1080
    allow_upscale: bool = False
    quality: int = 95
    png_compression: int = 6
    webp_lossless: bool = False
    target_kb: int = 0  # KiB; applies per image
    shrink_for_target: bool = False
    alpha: str = 'keep'  # keep, white, black
    grayscale: bool = False
    rotate: int = 0
    apply_document_crop: bool = False
    naming: str = 'ordinal_name'  # ordinal_name, doc_ordinal, location_ordinal

    def validate(self):
        if self.format not in {*FORMATS, 'ORIGINAL'}:
            raise ValueError('지원하지 않는 저장 형식입니다.')
        if self.format == 'ORIGINAL' and self.apply_document_crop:
            raise ValueError('원본 형식과 본문 자르기는 함께 사용할 수 없습니다. PNG 등 출력 형식을 선택하세요.')
        if self.naming not in {'ordinal_name', 'doc_ordinal', 'location_ordinal'}:
            raise ValueError('파일명 규칙이 잘못되었습니다.')
        if self.resize not in {'original', 'percent', 'long_edge', 'fit'}:
            raise ValueError('해상도 모드가 잘못되었습니다.')
        if self.dpi is not None and not 36 <= self.dpi <= 2400:
            raise ValueError('DPI는 36~2400 범위로 지정하세요.')
        if not 1 <= self.percent <= 400 or not 1 <= self.width <= 30000 or not 1 <= self.height <= 30000:
            raise ValueError('해상도 범위를 확인하세요.')
        if not 1 <= self.quality <= 100 or not 0 <= self.png_compression <= 9:
            raise ValueError('압축 설정 범위를 확인하세요.')
        if self.target_kb < 0 or self.target_kb > 1024000:
            raise ValueError('목표 용량 범위를 확인하세요.')
        if self.alpha not in {'keep', 'white', 'black'} or self.rotate not in {0, 90, 180, 270}:
            raise ValueError('이미지 처리 설정이 잘못되었습니다.')
        if self.format == 'WEBP' and not features.check('webp'):
            raise ValueError('현재 Pillow 설치에 WebP 지원이 없습니다.')


@dataclass
class Conversion:
    data: bytes
    extension: str
    source_size: tuple[int, int] | None
    size: tuple[int, int] | None
    format: str
    quality: int | None
    dpi: tuple[float, float] | None
    notes: list[str]
    target_met: bool | None
    passthrough: bool = False
    source_data: bytes | None = None


def open_raster(data: bytes):
    # Python 3.12 warning filters are global. Serialize only header inspection,
    # leaving expensive pixel decoding outside the lock.
    with _RASTER_HEADER_LOCK:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            im = Image.open(io.BytesIO(data))
    try:
        if Image.MAX_IMAGE_PIXELS and im.width*im.height > Image.MAX_IMAGE_PIXELS:
            raise Image.DecompressionBombWarning('이미지 픽셀 수가 안전 제한을 초과합니다.')
        im.load()
    except Exception:
        im.close();raise
    return im


def resized_size(size: tuple[int, int], s: Settings):
    w, h = size
    ratio = 1.0
    if s.resize == 'percent':
        ratio = s.percent / 100
    elif s.resize == 'long_edge':
        ratio = s.width / max(w, h)
    elif s.resize == 'fit':
        ratio = min(s.width / w, s.height / h)
    if not s.allow_upscale:
        ratio = min(ratio, 1.0)
    result = (max(1, round(w * ratio)), max(1, round(h * ratio)))
    if result[0] * result[1] > MAX_OUTPUT_PIXELS:
        raise ValueError('출력 이미지가 8천만 픽셀을 초과합니다. 해상도를 줄이세요.')
    return result


def _normalize_mode(im: Image.Image) -> Image.Image:
    """Safely normalize 16-bit/float grayscale (I;16, I, F) or CMYK images before RGB/RGBA conversion."""
    if im.mode in {'I;16', 'I;16L', 'I;16B', 'I', 'F'}:
        arr = im.convert('I')
        lo, hi = arr.getextrema()
        if hi > 255:
            divisor = 65535.0 if hi <= 65535 else float(hi)
            scale = 255.0 / divisor
            return arr.point(lambda v: v * scale).convert('L')
        return arr.convert('L')
    if im.mode == 'CMYK':
        return im.convert('RGB')
    return im


def flatten(im: Image.Image, color: str):
    if 'A' not in im.getbands() and 'transparency' not in im.info:
        return im if im.mode == 'RGB' else im.convert('RGB')
    rgba = im.convert('RGBA')
    background = Image.new('RGBA', rgba.size, color)
    return Image.alpha_composite(background, rgba).convert('RGB')


def read_dpi(im):
    dpi = im.info.get('dpi')
    if not dpi and im.format == 'WEBP':
        exif = im.getexif()
        if exif.get(296) == 2:
            dpi = (exif.get(282, 0), exif.get(283, 0))
    try:
        if dpi and len(dpi) == 2 and all(math.isfinite(float(v)) and float(v) > 0 for v in dpi):
            return (float(dpi[0]), float(dpi[1]))
    except (ValueError, TypeError, ZeroDivisionError):
        return None
    return None


def encode(im, s: Settings, quality: int, dpi):
    options = {}
    if dpi and s.format in DPI_FORMATS:
        if s.format == 'WEBP':
            exif = Image.Exif()
            exif[282], exif[283], exif[296] = dpi[0], dpi[1], 2
            options['exif'] = exif.tobytes()
        else:
            options['dpi'] = dpi
    if s.format == 'JPEG':
        # Baseline encoding avoids libjpeg's fixed optimization buffer failures
        # on high-detail, full-chroma images and works with in-memory outputs.
        options.update(quality=quality, subsampling=2 if (s.target_kb or quality <= 90) else 0, optimize=False)
    elif s.format == 'PNG':
        options['compress_level'] = 9 if s.target_kb else s.png_compression
    elif s.format == 'WEBP':
        options.update(quality=quality, lossless=s.webp_lossless, method=4)
    elif s.format == 'TIFF':
        options['compression'] = 'tiff_lzw'
    elif s.format == 'ICO':
        options['sizes'] = [im.size]
    # RGB/RGBA profiles remain valid after resize/rotation. Grayscale output omits RGB profiles.
    if im.info.get('icc_profile') and s.format in {'JPEG', 'PNG', 'TIFF', 'WEBP'}:
        options['icc_profile'] = im.info['icc_profile']
    buffer = io.BytesIO()
    im.save(buffer, s.format, **options)
    return buffer.getvalue()


def convert_image(data: bytes, s: Settings, member_name: str = '', cancel=None, crop_box=None,
                  *, document_crop=None) -> Conversion:
    s.validate()
    if (crop_box is not None or document_crop is not None) and s.format == 'ORIGINAL':
        raise ValueError('본문 자르기를 반영하려면 PNG 등 변환 형식을 선택하세요.')
    checkpoint(cancel)
    if len(data) > MAX_MEMBER_BYTES:
        raise ValueError('내장 이미지가 256 MB를 초과합니다.')
    ext = PurePosixPath(member_name).suffix.lower()
    if s.format == 'ORIGINAL' and ext in VECTOR_EXTS:
        return Conversion(data, ext, None, None, ext[1:].upper(), None, None,
                          ['원본 바이트 저장: 조정 설정 미적용'], None, True)
    with open_raster(data) as original:
        fmt = original.format
        source_size = original.size
        dpi = read_dpi(original)
        if s.format == 'ORIGINAL':
            extension = Image.registered_extensions()
            actual_ext = ext if extension.get(ext) == fmt else next((e for e, f in extension.items() if f == fmt), '.img')
            return Conversion(data, actual_ext, source_size, source_size, fmt, None, dpi,
                              ['원본 바이트 저장: 조정 설정 미적용'], None, True)
        notes = []
        if document_crop is not None:
            crop_box,extra=document_crop.pixels(source_size)
            notes.extend(extra)
        if getattr(original, 'n_frames', 1) > 1:
            notes.append('여러 프레임 중 첫 프레임 저장')
        if crop_box is not None:
            if len(crop_box) != 4 or crop_box[2] <= crop_box[0] or crop_box[3] <= crop_box[1]:
                raise ValueError('잘못된 픽셀 자르기 영역입니다.')
            if (crop_box[2]-crop_box[0])*(crop_box[3]-crop_box[1]) > MAX_OUTPUT_PIXELS:
                raise ValueError('자르기 결과가 8천만 픽셀을 초과합니다.')
            # Crop before RGBA expansion when no transparent padding is needed.
            if 0 <= crop_box[0] < crop_box[2] <= original.width and 0 <= crop_box[1] < crop_box[3] <= original.height:
                prepared = original.crop(crop_box).convert('RGBA')
            else:
                prepared = original.convert('RGBA').crop(crop_box)
            prepared.info.update(original.info)
            try:
                ImageOps.exif_transpose(prepared,in_place=True)
                im = prepared
            except TypeError:
                im = ImageOps.exif_transpose(prepared)
            notes.append('본문 자르기 적용: ' + ', '.join(map(str,crop_box)))
        else:
            orientation = original.getexif().get(274,1)
            try:
                ImageOps.exif_transpose(original,in_place=True)
                im = original
            except TypeError:
                im = ImageOps.exif_transpose(original)
            im = _normalize_mode(im)
        if (original.getexif().get(274,1) if crop_box is not None else orientation) != 1:
            notes.append('EXIF 회전 방향 적용')
        if s.rotate:
            im = im.rotate(-s.rotate, expand=True)
        new_size = resized_size(im.size, s)
        if new_size != im.size:
            im = im.resize(new_size, Image.Resampling.LANCZOS)
        profile = original.info.get('icc_profile') if original.mode in {'RGB', 'RGBA', 'L', 'LA'} else None
        supports_alpha = s.format in {'PNG', 'WEBP', 'TIFF', 'ICO'}
        if s.alpha != 'keep' or not supports_alpha:
            im = flatten(im, 'black' if s.alpha == 'black' else 'white')
            if s.alpha == 'keep' and ('A' in original.getbands() or 'transparency' in original.info):
                notes.append('이 형식에서는 투명 배경을 흰색으로 처리')
        else:
            mode = 'RGBA' if ('A' in im.getbands() or 'transparency' in im.info) else 'RGB'
            if im.mode != mode:im = im.convert(mode)
        if s.grayscale:
            if 'A' in im.getbands():
                a = im.getchannel('A')
                im = ImageOps.grayscale(im).convert('RGBA')
                im.putalpha(a)
            else:
                im = ImageOps.grayscale(im)
            profile = None
        if s.format == 'GIF':
            im = im.convert('RGB').quantize(colors=256)
            notes.append('GIF는 최대 256색으로 변환')
        elif s.format == 'BMP':
            im = im.convert('RGB')
        elif s.format == 'ICO':
            # ICO entries use a square canvas; do not stretch the artwork.
            side = min(256, max(im.size))
            icon = Image.new('RGBA', (side, side), (0, 0, 0, 0) if s.alpha == 'keep' else s.alpha)
            im.thumbnail((side, side), Image.Resampling.LANCZOS)
            icon.alpha_composite(im.convert('RGBA'), ((side - im.width) // 2, (side - im.height) // 2))
            im = icon
            notes.append('ICO: 최대 256×256 정사각 캔버스, 비율 유지')
        im.info.clear()
        if profile:
            im.info['icc_profile'] = profile
        dpi = (s.dpi, s.dpi) if s.dpi is not None else dpi
        if s.format not in DPI_FORMATS:
            if s.dpi:
                notes.append('이 형식은 DPI 설정을 저장하지 않음')
            dpi = None
        lossy = s.format == 'JPEG' or (s.format == 'WEBP' and not s.webp_lossless)
        quality = s.quality
        payload = encode(im, s, quality, dpi)
        target = s.target_kb * 1024
        # Search for the highest tested quality under the user's ceiling.
        def compress(current, default=None):
            checkpoint(cancel)
            if default is None:default = encode(current, s, s.quality, dpi)
            if not target or len(default) <= target or not lossy:
                return default, s.quality
            if s.quality==1:return default,1
            smallest = encode(current, s, 1, dpi)
            if len(smallest) > target:
                return smallest, 1
            best, best_quality = smallest, 1
            low, high = 2, s.quality - 1
            while low <= high:
                checkpoint(cancel)
                mid = (low + high) // 2
                candidate = encode(current, s, mid, dpi)
                if len(candidate) <= target:
                    best, best_quality, low = candidate, mid, mid + 1
                else:
                    high = mid - 1
            return best, best_quality
        if target and len(payload) > target:
            payload, quality = compress(im,payload)
            if s.shrink_for_target:
                for _ in range(16):
                    checkpoint(cancel)
                    if len(payload) <= target or im.size == (1, 1):
                        break
                    ratio = min(0.85, max(0.15, math.sqrt(target / len(payload)) * 0.90))
                    size = (max(1, int(im.width * ratio)), max(1, int(im.height * ratio)))
                    if s.format == 'ICO':
                        size = (max(size), max(size))
                    if size == im.size:
                        break
                    im = im.resize(size, Image.Resampling.LANCZOS)
                    payload, quality = compress(im)
                if im.size != new_size:
                    notes.append('목표 용량을 위해 픽셀 크기 추가 축소')
        met = len(payload) <= target if target else None
        if met is False:
            notes.append('목표 용량 미달성: 현재 결과 저장')
        if s.dpi:
            notes.append('DPI 설정은 픽셀 수를 증가시키지 않음')
        return Conversion(payload, FORMATS[s.format], source_size, im.size, s.format,
                          quality if lossy else None, dpi, notes, met)


def read_member(archive, member):
    if member.file_size > MAX_MEMBER_BYTES:
        raise ValueError('내장 이미지가 256 MB를 초과합니다.')
    with archive.open(member) as handle:
        data = handle.read(MAX_MEMBER_BYTES + 1)
    if len(data) > MAX_MEMBER_BYTES:
        raise ValueError('내장 이미지가 256 MB를 초과합니다.')
    return data


def fresh_folder(destination: Path, name: str):
    base = destination / name
    folder, suffix = base, 2
    while True:
        try:
            folder.mkdir(parents=True, exist_ok=False)
            return folder
        except FileExistsError:
            folder = base.with_name(base.name + f'_{suffix}')
            suffix += 1


def convert_item(data, item, settings, cancel=None):
    crop=item.crop if settings.apply_document_crop else None
    result=convert_image(data,settings,item.member,cancel,document_crop=crop)
    result.notes=list(item.notes)+result.notes
    return result


def _working_bytes(item, settings):
    """Conservative scheduling estimate; one oversized image still runs alone."""
    if not item.size:return CONVERSION_MEMORY_BUDGET
    w,h=item.size
    try:
        if settings.apply_document_crop and item.crop:
            box,_=item.crop.pixels(item.size);cw,ch=box[2]-box[0],box[3]-box[1]
        else:cw,ch=w,h
        ow,oh=resized_size((cw,ch),settings)
        return max(1,item.stored_bytes)*2+(w*h+max(cw*ch,ow*oh))*16
    except Exception:
        return CONVERSION_MEMORY_BUDGET


def _conversion_results(reader, items, settings, cancel, workers, notify_start=lambda item,index:None, converter=None):
    # Readers (especially PyMuPDF) stay on the coordinating thread. Only Pillow
    # conversion of independent byte buffers runs in parallel; writing stays ordered.
    def convert(data,item):
        checkpoint(cancel)
        return len(data),(converter(data,item) if converter else convert_item(data,item,settings,cancel))
    if workers==1:
        for ordinal,item in enumerate(items,1):
            checkpoint(cancel)
            notify_start(item,ordinal)
            size=None
            try:
                data=reader.read(item);size=len(data)
                _,result=convert(data,item)
            except Cancelled:raise
            except Exception as exc:yield item,size,None,exc
            else:yield item,size,result,None
        return
    pending=deque();used=0;cursor=0;completed=0
    with ThreadPoolExecutor(max_workers=workers,thread_name_prefix='SunriseImage') as pool:
        try:
            while cursor<len(items) or pending:
                checkpoint(cancel)
                notify_start(items[completed],completed+1)
                while cursor<len(items) and len(pending)<workers:
                    checkpoint(cancel)
                    item=items[cursor];weight=_working_bytes(item,settings)
                    if pending and used+weight>CONVERSION_MEMORY_BUDGET:break
                    # Never share a document handle between conversion threads.
                    source_bytes=None
                    try:
                        data=reader.read(item)
                        source_bytes=len(data)
                        weight=max(weight,len(data)*2)
                        future=pool.submit(convert,data,item)
                        del data
                    except Cancelled:raise
                    except Exception as exc:
                        future=Future();future.set_exception(exc)
                    pending.append((item,future,weight,source_bytes));used+=weight;cursor+=1
                item,future,weight,source_bytes=pending.popleft()
                try:size,result=future.result()
                except Cancelled:raise
                except Exception as exc:yield item,source_bytes,None,exc
                else:yield item,size,result,None
                used-=weight
                completed+=1
        finally:
            for _,future,_,_ in pending:future.cancel()


def extract_images(source: Path, destination: Path, settings: Settings | None = None,
                   notify: Callable = lambda event: None, cancel=None, selected_keys=None, catalog=None,
                   *, workers=None):
    from document_reader import open_document
    s=settings or Settings();s.validate();checkpoint(cancel)
    started=time.perf_counter()
    if workers is not None and (not isinstance(workers,int) or not 1<=workers<=4):
        raise ValueError('동시 변환 수는 1~4 범위로 지정하세요.')
    saved=failed=warned=processed=0;stopped=False;records=[]
    with open_document(source,s.apply_document_crop,cancel) as reader:
        current=catalog or reader.catalog()
        if catalog and getattr(catalog,'fingerprint',None):
            stat=Path(source).stat()
            if catalog.fingerprint!=(stat.st_size,stat.st_mtime_ns):raise ValueError('목록을 만든 뒤 문서가 변경되었습니다. 목록을 새로고침하세요.')
        items=current.items
        if selected_keys is not None:
            keys=set(selected_keys);known={i.key for i in items}
            if keys-known:raise ValueError('선택 목록이 현재 문서와 일치하지 않습니다. 새로고침하세요.')
            items=[i for i in items if i.key in keys]
        folder=fresh_folder(Path(destination),safe_name(Path(source).stem)+'_'+s.format+('_본문자르기' if s.apply_document_crop and Path(source).suffix.lower() == '.hwpx' else ''))
        notify({'type':'begin','total':len(items),'folder':str(folder)})
        for warning in current.warnings:notify({'type':'warning','message':warning})
        count=workers if workers is not None else min(4,max(1,(os.cpu_count() or 2)-1))
        if workers is None and (len(items)<4 or all(i.size and i.size[0]*i.size[1]<65_536 for i in items)):
            count=1
        def notify_start(item,index):
            notify({'type':'item_start','index':index,'total':len(items),'member':item.member,'key':item.key})
        conversions=_conversion_results(reader,items,s,cancel,count,notify_start)
        try:
            for index,(item,source_bytes,result,error) in enumerate(conversions,1):
                checkpoint(cancel)
                row={'내부 파일':item.member,'목록 ID':item.key,'본문 위치':item.location,'저장 파일':'','상태':'','원본 바이트':item.stored_bytes}
                try:
                    if source_bytes is not None:row['원본 바이트']=source_bytes
                    if error is not None:raise error
                    checkpoint(cancel)
                    stem_part=safe_name(PurePosixPath(item.member).stem)
                    if s.naming=='doc_ordinal':
                        doc_prefix=safe_name(Path(source).stem)[:40]
                        name=f'{doc_prefix}_{index:04d}_{stem_part}{result.extension}'
                    elif s.naming=='location_ordinal':
                        loc_raw=human_location(item.location or '문서').replace('구역 ', '구역')
                        loc_prefix=safe_name(loc_raw.split(',')[0].split('·')[0].strip())[:24] or '문서'
                        name=f'{loc_prefix}_{index:04d}_{stem_part}{result.extension}'
                    else:
                        name=f'{index:04d}_{stem_part}{result.extension}'
                    target=folder/name
                    try:target.write_bytes(result.data)
                    except Exception:
                        target.unlink(missing_ok=True);raise
                    caution=any(any(term in n for term in ['미달성','미반영','미제공','원본 밖']) for n in result.notes)
                    status='주의' if caution else '성공'
                    saved+=1;warned+=status=='주의'
                    row.update({'저장 파일':name,'상태':status,'원본 가로':(result.source_size or ('',''))[0],
                                '원본 세로':(result.source_size or ('',''))[1],'출력 가로':(result.size or ('',''))[0],
                                '출력 세로':(result.size or ('',''))[1],'출력 바이트':len(result.data),
                                'DPI 가로':(result.dpi or ('',''))[0],'DPI 세로':(result.dpi or ('',''))[1],
                                '실제 품질':result.quality or '', '목표 KB':s.target_kb or '',
                                '목표 달성':'예' if result.target_met else ('아니오' if result.target_met is False else '미적용'),
                                '자르기 픽셀':'; '.join(n for n in result.notes if n.startswith('본문 자르기 적용')),
                                '비고':'; '.join(result.notes)})
                except Cancelled:raise
                except Exception as exc:
                    failed+=1;row.update({'상태':'실패','비고':str(exc)})
                records.append(row);processed+=1
                notify({'type':'item','index':index,'total':len(items),'row':row,'folder':str(folder)})
        except Cancelled:stopped=True
        finally:
            conversions.close()
            fields=['내부 파일','목록 ID','본문 위치','저장 파일','상태','원본 바이트','출력 바이트','원본 가로','원본 세로',
                    '출력 가로','출력 세로','DPI 가로','DPI 세로','실제 품질','목표 KB','목표 달성','자르기 픽셀','비고']
            with (folder/'추출결과.csv').open('w',encoding='utf-8-sig',newline='') as handle:
                writer=csv.DictWriter(handle,fieldnames=fields);writer.writeheader();writer.writerows(records)
    return {'folder':str(folder),'saved':saved,'failed':failed,'warned':warned,'processed':processed,'total':len(items),'cancelled':stopped,
            'elapsed_seconds':time.perf_counter()-started}
