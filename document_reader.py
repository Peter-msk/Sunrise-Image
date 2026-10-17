"""Document-native image catalog and readers (HWPX, PDF, DOCX, XLSX, PPTX).
Legacy binary HWP (.hwp) is excluded from all program features.
"""
from __future__ import annotations
import io
import math
import posixpath
import re
import zipfile
from dataclasses import dataclass, field, replace
from pathlib import Path, PurePosixPath
from urllib.parse import unquote
from defusedxml import ElementTree as ET
from PIL import Image
from image_engine import MAX_MEMBER_BYTES, VECTOR_EXTS, checkpoint, read_member

SUPPORTED = {
    '.hwpx': '한글 HWPX',
    '.pdf': 'PDF',
    '.docx': 'Word DOCX',
    '.xlsx': 'Excel XLSX',
    '.pptx': 'PowerPoint PPTX',
}
OPTIMIZABLE = {
    '.hwpx': '한글 HWPX',
    '.pdf': 'PDF',
    '.xlsx': 'Excel XLSX',
    '.docx': 'Word DOCX',
    '.pptx': 'PowerPoint PPTX',
}
RASTER_EXTS = {'.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tif', '.tiff', '.webp', '.ico', '.pcx', '.tga', '.jp2', '.j2k', '.avif'}
IMAGE_EXTS = RASTER_EXTS | VECTOR_EXTS
MAX_XML_BYTES = 64 * 1024 * 1024
HANCOM_NOTICE = '지원 문서: 개방형 한글(.hwpx), PDF(.pdf), Excel(.xlsx), Word(.docx), PowerPoint(.pptx) · 구형 한글(.hwp)은 지원 대상에서 제외됩니다.'


def natural(name):
    return [int(s) if s.isdigit() else s.lower() for s in re.split(r'(\d+)', name)]


def local(tag):
    return tag.rsplit('}', 1)[-1]


def safe_xml(archive, name):
    if archive.getinfo(name).file_size > MAX_XML_BYTES:
        raise ValueError('XML 정보가 제한 크기를 초과했습니다.')
    return ET.fromstring(archive.read(name))


@dataclass(frozen=True)
class Crop:
    rect: tuple[float, float, float, float]  # left, top, right, bottom; coordinates, not margins
    extent: tuple[float, float] | None = None
    basis: str = '한글 좌표'
    error: str = ''

    def pixels(self, size):
        if self.error:
            raise ValueError(self.error)
        w, h = size
        ew, eh = self.extent or (w * 75, h * 75)
        if not all(math.isfinite(v) for v in (*self.rect, ew, eh)) or ew <= 0 or eh <= 0:
            raise ValueError('자르기 좌표 또는 원본 기준 크기가 잘못되었습니다.')
        left, top, right, bottom = self.rect
        if right <= left or bottom <= top:
            raise ValueError('자르기 영역의 너비 또는 높이가 0 이하입니다.')
        coords = (left * w / ew, top * h / eh, right * w / ew, bottom * h / eh)
        box = tuple(round(x) for x in coords)
        if box[2] <= box[0] or box[3] <= box[1]:
            raise ValueError('자르기 영역이 1픽셀보다 작습니다.')
        if (box[2] - box[0]) * (box[3] - box[1]) > 80_000_000:
            raise ValueError('자르기 결과가 8천만 픽셀을 초과합니다.')
        if box[2] <= 0 or box[3] <= 0 or box[0] >= w or box[1] >= h:
            raise ValueError('자르기 영역이 원본 이미지와 겹치지 않습니다.')
        note = []
        if self.extent is None:
            note.append('imgDim 미제공: 한글 96 DPI 좌표 기준 적용')
        if box[0] < 0 or box[1] < 0 or box[2] > w or box[3] > h:
            note.append('원본 밖 자르기 영역은 투명 여백으로 유지')
        return box, note


@dataclass(frozen=True)
class ImageItem:
    key: str
    member: str
    name: str
    location: str = '내장 원본'
    format: str = ''
    size: tuple[int, int] | None = None
    stored_bytes: int = 0
    crop: Crop | None = None
    notes: tuple[str, ...] = ()
    error: str = ''
    meta: dict = field(default_factory=dict, compare=False)


@dataclass
class Catalog:
    source: str
    items: list[ImageItem]
    warnings: list[str] = field(default_factory=list)
    fingerprint: tuple[int, int] | None = None


class ZipReader:
    def __init__(self, path, body=False, cancel=None):
        self.path = Path(path)
        self.body = body
        self.cancel = cancel
        try:
            with self.path.open('rb') as fh:
                magic = fh.read(8)
        except OSError as exc:
            raise ValueError(f'문서 파일을 읽을 수 없습니다: {exc}') from exc
        if magic.startswith(b'\xd0\xcf\x11\xe0'):
            raise ValueError('구형 바이너리 문서(HWP/DOC/XLS)이거나 문서보안(DRM)·암호가 설정된 파일입니다. 개방형 문서(.hwpx, .xlsx, .docx, .pptx)로 저장한 뒤 사용하세요.')
        try:
            self.z = zipfile.ZipFile(path)
        except (zipfile.BadZipFile, OSError) as exc:
            raise ValueError(f'손상되었거나 올바르지 않은 문서 파일입니다: {self.path.name}') from exc

    def close(self):
        self.z.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def read(self, item):
        return read_member(self.z, self.z.getinfo(item.member))

    def inspect(self, name):
        m = self.z.getinfo(name)
        fmt = PurePosixPath(name).suffix[1:].upper()
        size = None
        error = ''
        if m.file_size > MAX_MEMBER_BYTES:
            error = '내장 이미지가 256 MB를 초과합니다.'
        elif PurePosixPath(name).suffix.lower() not in VECTOR_EXTS:
            try:
                with self.z.open(m) as h:
                    with Image.open(h) as im:
                        fmt = im.format
                        size = im.size
            except Exception as exc:
                error = '이미지 읽기 불가: ' + str(exc)
        return ImageItem('asset:' + name, name, PurePosixPath(name).name, format=fmt, size=size, stored_bytes=m.file_size, error=error)

    def catalog(self):
        ext = self.path.suffix.lower()
        prefixes = {
            '.hwpx': ('bindata/', 'contents/bindata/'),
            '.docx': ('word/media/',),
            '.xlsx': ('xl/media/',),
            '.pptx': ('ppt/media/',),
        }[ext]
        names = sorted(
            [
                m.filename
                for m in self.z.infolist()
                if not m.is_dir()
                and m.filename.replace('\\', '/').lower().startswith(prefixes)
                and PurePosixPath(m.filename.replace('\\', '/')).suffix.lower() in IMAGE_EXTS
            ],
            key=natural,
        )
        assets = {name: self.inspect(name) for name in names}
        if ext != '.hwpx' or not self.body:
            return Catalog(str(self.path), list(assets.values()))
        mapping = {}
        warnings = []
        name_lookup = {n.replace('\\', '/').lower(): n for n in self.z.namelist()}
        section_names = sorted(
            [n for n in self.z.namelist() if re.fullmatch(r'Contents/section\d+\.xml', n.replace('\\', '/'), re.I)],
            key=natural,
        )
        hpf_name = name_lookup.get('contents/content.hpf')
        if hpf_name:
            root = safe_xml(self.z, hpf_name)
            for el in root.iter():
                if local(el.tag) == 'item' and el.get('id') and el.get('href'):
                    href = unquote(el.get('href')).replace('\\', '/').lstrip('/')
                    normalized = posixpath.normpath(href)
                    actual = name_lookup.get(normalized.lower())
                    if not actual:
                        alt = posixpath.normpath(posixpath.join('Contents', href))
                        actual = name_lookup.get(alt.lower(), normalized)
                    mapping[el.get('id')] = actual
            ordered = [mapping.get(el.get('idref')) for el in root.iter() if local(el.tag) == 'itemref']
            ordered = [n for n in ordered if n in section_names]
            section_names = ordered + [n for n in section_names if n not in ordered]
        for name in names:
            stem = PurePosixPath(name.replace('\\', '/')).stem
            mapping.setdefault(stem, name)
            mapping.setdefault(stem.lower(), name)
        items = []
        used = set()
        for section in section_names:
            checkpoint(self.cancel)
            try:
                root = safe_xml(self.z, section)
            except Exception as exc:
                raise ValueError(f'본문 자르기 정보를 읽지 못했습니다: {section}: {exc}') from exc
            for index, pic in enumerate((e for e in root.iter() if local(e.tag) == 'pic'), 1):
                img = next((e for e in pic.iter() if local(e.tag) == 'img'), None)
                if img is None:
                    continue
                ref = img.get('binaryItemIDRef', '')
                name = mapping.get(ref) or mapping.get(ref.lower())
                if name not in assets:
                    warnings.append(f'{section} 그림 {index}: 내장 이미지 참조를 찾지 못함 ({ref})')
                    continue
                base = assets[name]
                used.add(name)
                clip = next((e for e in pic if local(e.tag) == 'imgClip'), None)
                dim = next((e for e in pic if local(e.tag) == 'imgDim'), None)
                extent = None
                crop = None
                notes = []
                if dim is not None:
                    try:
                        dw, dh = float(dim.get('dimwidth', '0')), float(dim.get('dimheight', '0'))
                        if dw > 0 and dh > 0:
                            extent = (dw, dh)
                    except ValueError:
                        notes.append('원본 기준 크기를 읽지 못함')
                if clip is not None:
                    try:
                        crop = Crop(tuple(float(clip.get(k, '')) for k in ['left', 'top', 'right', 'bottom']), extent)
                    except ValueError:
                        crop = Crop((0, 0, 0, 0), error='본문 자르기 좌표를 해석할 수 없습니다.')
                rotation = next((e for e in pic if local(e.tag) == 'rotationInfo'), None)
                flip = next((e for e in pic if local(e.tag) == 'flip'), None)
                if (rotation is not None and rotation.get('angle', '0') != '0') or (
                    flip is not None and any(flip.get(a, '0') == '1' for a in ['horizontal', 'vertical'])
                ):
                    notes.append('본문 회전·뒤집기 효과는 별도 미반영')
                if img.get('effect', 'REAL_PIC') != 'REAL_PIC' or any(img.get(a, '0') != '0' for a in ['bright', 'contrast']):
                    notes.append('본문 밝기·색상 효과는 별도 미반영')
                key = f'occ:{section}:{index}'
                items.append(replace(base, key=key, location=f'{PurePosixPath(section).stem} · 그림 {index}', crop=crop, notes=tuple(notes)))
        items.extend(replace(a, location='본문 참조 없음 · 내장 원본') for n, a in assets.items() if n not in used)
        if not section_names:
            warnings.append('본문 구역 없음: 자르기 정보 없이 내장 원본 목록 제공')
        return Catalog(str(self.path), items, warnings)


class PdfReader:
    def __init__(self, path, body=False, cancel=None):
        import pymupdf
        self.fitz = pymupdf
        self.path = Path(path)
        self.cancel = cancel
        try:
            self.doc = pymupdf.open(path)
        except Exception as exc:
            raise ValueError(f'손상되었거나 읽을 수 없는 PDF 문서입니다: {exc}') from exc
        if self.doc.needs_pass:
            self.doc.close()
            raise ValueError('암호가 설정된 PDF는 지원하지 않습니다.')

    def close(self):
        self.doc.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def read(self, item):
        if item.meta.get('inline'):
            page = self.doc[item.meta['page']]
            blocks = page.get_text('dict', flags=self.fitz.TEXT_PRESERVE_IMAGES)['blocks']
            block = next((b for b in blocks if b.get('type') == 1 and b.get('number') == item.meta['block']), None)
            if not block:
                raise ValueError('PDF 인라인 이미지를 찾지 못했습니다.')
            return block['image']
        xref = item.meta['xref']
        extracted = self.doc.extract_image(xref)
        if not extracted:
            raise ValueError('PDF 이미지 데이터를 읽지 못했습니다.')
        if extracted.get('width', 0) * extracted.get('height', 0) > 80_000_000:
            raise ValueError('PDF 이미지가 8천만 픽셀을 초과합니다.')
        smask = extracted.get('smask', 0)
        if smask > 0:
            base = self.fitz.Pixmap(self.doc, xref)
            mask = self.fitz.Pixmap(self.doc, smask)
            if base.colorspace and base.colorspace.n > 3:
                base = self.fitz.Pixmap(self.fitz.csRGB, base)
            if base.alpha:
                base = self.fitz.Pixmap(base, 0)
            composed = self.fitz.Pixmap(base, mask)
            return composed.tobytes('png')
        return extracted['image']

    def catalog(self):
        infos = {}
        items = []
        warnings = []
        for pno, page in enumerate(self.doc):
            checkpoint(self.cancel)
            for info in page.get_image_info(xrefs=True):
                xref = info.get('xref', 0)
                if xref:
                    if xref not in infos:
                        extracted = self.doc.extract_image(xref)
                        if not extracted:
                            continue
                        infos[xref] = len(items)
                        smask = extracted.get('smask', 0)
                        ext = 'png' if smask else extracted.get('ext', 'png')
                        notes = ('PDF 투명 마스크 합성: PNG로 추출',) if smask else ()
                        items.append(
                            ImageItem(
                                f'pdf:xref:{xref}',
                                f'pdf_xref_{xref}.{ext}',
                                f'이미지 {len(items) + 1}.{ext}',
                                location=f'{pno + 1}쪽',
                                format=ext.upper(),
                                size=(info['width'], info['height']),
                                stored_bytes=len(extracted['image']),
                                notes=notes,
                                meta={'xref': xref, 'pages': [pno + 1]},
                            )
                        )
                    else:
                        i = infos[xref]
                        entry = items[i]
                        if pno + 1 not in entry.meta['pages']:
                            pages = entry.meta['pages'] + [pno + 1]
                            items[i] = replace(entry, location=', '.join(map(str, pages)) + '쪽', meta={**entry.meta, 'pages': pages})
                else:
                    block = info.get('number', 0)
                    items.append(
                        ImageItem(
                            f'pdf:inline:{pno}:{block}',
                            f'inline_{pno + 1}_{block}.png',
                            f'인라인 {pno + 1}-{block}.png',
                            location=f'{pno + 1}쪽',
                            format='PNG',
                            size=(info['width'], info['height']),
                            notes=('PDF 인라인 이미지',),
                            meta={'inline': True, 'page': pno, 'block': block},
                        )
                    )
        return Catalog(str(self.path), items, warnings)


def open_document(path, body=False, cancel=None):
    path = Path(path)
    ext = path.suffix.lower()
    if ext == '.hwp':
        raise ValueError('구형 한글(.hwp)은 지원하지 않습니다. 한글에서 개방형 한글(.hwpx)로 저장한 뒤 사용하세요.')
    if ext not in SUPPORTED:
        raise ValueError('지원하지 않는 문서 형식입니다. HWPX·PDF·DOCX·XLSX·PPTX로 저장한 뒤 사용하세요.')
    if ext == '.pdf':
        return PdfReader(path, body, cancel)
    return ZipReader(path, body, cancel)


def scan_document(path, body=False, cancel=None):
    with open_document(path, body, cancel) as reader:
        catalog = reader.catalog()
        st = Path(path).stat()
        catalog.fingerprint = (st.st_size, st.st_mtime_ns)
        return catalog
