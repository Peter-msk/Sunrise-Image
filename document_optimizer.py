"""Optimize embedded images into a new document copy; never overwrite the source."""
from __future__ import annotations
import csv
import html
import os
import posixpath
import re
import shutil
import time
import tempfile
import zipfile
from dataclasses import replace
from pathlib import Path, PurePosixPath
from typing import Callable
from urllib.parse import unquote, quote

from document_reader import OPTIMIZABLE, open_document, read_xml_bytes, safe_xml
from image_engine import (
     FORMATS, VECTOR_EXTS, Cancelled, Settings, _conversion_results,
    checkpoint, convert_image, fresh_folder, open_raster, safe_name, validate_archive_member, csv_record,
)

MIME_BY_EXT = {
    '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png',
    '.webp': 'image/webp', '.tif': 'image/tiff', '.tiff': 'image/tiff',
    '.bmp': 'image/bmp', '.gif': 'image/gif', '.ico': 'image/x-icon',
}
JPEG_PAIR = {'.jpg', '.jpeg'}
TIFF_PAIR = {'.tif', '.tiff'}


def _has_transparency(data: bytes) -> bool:
    try:
        with open_raster(data) as im:
            if im.mode in ('RGBA', 'LA') or (im.mode == 'P' and 'transparency' in im.info):
                alpha = im.convert('RGBA').getchannel('A')
                lo, _ = alpha.getextrema()
                return lo < 255
    except (OSError, ValueError, SyntaxError):
        return False
    return False


def _same_format_ext(ext_a: str, ext_b: str) -> bool:
    a, b = ext_a.lower(), ext_b.lower()
    return a == b or (a in JPEG_PAIR and b in JPEG_PAIR) or (a in TIFF_PAIR and b in TIFF_PAIR)


def _decode_xml_bytes(raw: bytes) -> tuple[str, str]:
    if raw.startswith((b'\xff\xfe', b'\xfe\xff')):
        return raw.decode('utf-16'), 'utf-16'
    declared = re.search(br'<\?xml[^>]*encoding=[\"\']([^\"\']+)', raw[:200], re.I)
    encoding = declared.group(1).decode('ascii') if declared else ('utf-8-sig' if raw.startswith(b'\xef\xbb\xbf') else 'utf-8')
    try:
        return raw.decode(encoding), encoding
    except (UnicodeError, LookupError) as exc:
        raise ValueError('문서 XML 인코딩을 읽을 수 없어 원본을 유지합니다.') from exc


def _update_openxml_rels(xml_text: str, rels_filename: str, member_map: dict[str, str]) -> str:
    rels_dir = posixpath.dirname(rels_filename.replace('\\', '/'))
    base_dir = posixpath.dirname(rels_dir) if rels_dir.endswith('/_rels') or rels_dir == '_rels' else rels_dir

    def replace_relationship(match):
        tag = match.group(0)
        if re.search(r"\bTargetMode\s*=\s*([\"'])External\1", tag, re.I):
            return tag
        def replace_target(target_match):
            prefix, delimiter, target = target_match.group(1, 2, 3)
            raw_t = unquote(html.unescape(target)).replace('\\', '/')
            resolved = raw_t.lstrip('/') if raw_t.startswith('/') else posixpath.normpath(posixpath.join(base_dir, raw_t))
            if resolved not in member_map:
                return target_match.group(0)
            new_member = member_map[resolved]
            new_target = '/' + new_member if raw_t.startswith('/') else posixpath.relpath(new_member, base_dir or '.')
            encoded = html.escape(quote(new_target, safe='/.'), quote=True)
            return f'{prefix}{delimiter}{encoded}{delimiter}'
        return re.sub(r'(\bTarget\s*=\s*)(["\'])([^"\']+)\2', replace_target, tag)
    return re.sub(r'<(?:\w+:)?Relationship\b[^>]*>', replace_relationship, xml_text)



def _update_content_types(xml_text: str, member_map: dict[str, str]) -> str:
    def replace_override(match: re.Match) -> str:
        full_tag, quote, part_name = match.group(0), match.group(1), match.group(2)
        norm = part_name.lstrip('/')
        if norm not in member_map:
            return full_tag
        new_member = member_map[norm]
        new_mime = MIME_BY_EXT.get(PurePosixPath(new_member).suffix.lower(), 'image/jpeg')
        updated = full_tag.replace(f'{quote}{part_name}{quote}', f'{quote}/{new_member}{quote}')
        return re.sub(r'(\bContentType\s*=\s*["\'])([^"\']+)(["\'])', rf'\g<1>{new_mime}\g<3>', updated)

    xml_text = re.sub(r'<Override\b[^>]*\bPartName\s*=\s*(["\'])([^"\']+)\1[^>]*/?>', replace_override, xml_text)
    needed_exts = {PurePosixPath(new_m).suffix.lower().lstrip('.') for new_m in member_map.values() if PurePosixPath(new_m).suffix}
    for ext in sorted(needed_exts):
        mime = MIME_BY_EXT.get('.' + ext)
        if mime and not re.search(rf'<Default\b[^>]*\bExtension\s*=\s*["\']{re.escape(ext)}["\']', xml_text, re.I):
            xml_text = re.sub(r'(</Types\s*>)', f'<Default Extension="{ext}" ContentType="{mime}"/>\\1', xml_text, count=1)
    return xml_text


def _update_hwpx_hpf(xml_text: str, member_map: dict[str, str]) -> tuple[str, dict[str, str]]:
    lower_map = {k.replace('\\', '/').lower(): (k, v) for k, v in member_map.items()}
    id_to_old: dict[str, str] = {}

    def replace_item(match: re.Match) -> str:
        tag = match.group(0)
        href_m = re.search(r'(\bhref\s*=\s*)(["\'])([^"\']+)\2', tag)
        if not href_m:
            return tag
        q, href_val = href_m.group(2), href_m.group(3)
        raw_href = unquote(html.unescape(href_val)).replace('\\', '/')
        norm_href = posixpath.normpath(raw_href).lstrip('/')
        pair = lower_map.get(norm_href.lower())
        relative = False
        if pair is None:
            pair = lower_map.get(posixpath.normpath(posixpath.join('Contents', raw_href)).lower())
            relative = pair is not None
        if pair is None:
            return tag
        old_m, new_m = pair
        id_m = re.search(r'\bid\s*=\s*(["\'])([^"\']+)\1', tag)
        if id_m:
            id_to_old[id_m.group(2)] = old_m
        new_mime = MIME_BY_EXT.get(PurePosixPath(new_m).suffix.lower())
        href_out = posixpath.relpath(new_m, 'Contents') if relative else new_m
        href_out = html.escape(quote(href_out, safe='/.'), quote=True)
        tag = tag[:href_m.start()] + f'{href_m.group(1)}{q}{href_out}{q}' + tag[href_m.end():]
        if new_mime:
            tag = re.sub(r'(\bmedia-type\s*=\s*["\'])([^"\']+)(["\'])', rf'\g<1>{new_mime}\g<3>', tag)
        return tag

    return re.sub(r'<(?:\w+:)?item\b[^>]*/?>', replace_item, xml_text), id_to_old


def _update_hwpx_aux_xml(xml_text: str, member_map: dict[str, str]) -> str:
    for old_m, new_m in member_map.items():
        if old_m != new_m:
            xml_text = xml_text.replace(old_m, new_m).replace(old_m.replace('/', '\\'), new_m)
    return xml_text


def _update_hwpx_section_xml(
    xml_text: str,
    id_to_old_member: dict[str, str],
    size_map: dict[str, tuple[tuple[int, int] | None, tuple[int, int] | None]],
) -> str:
    def replace_pic(match: re.Match) -> str:
        pic_xml = match.group(0)
        ref_m = re.search(r'\bbinaryItemIDRef\s*=\s*(["\'])([^"\']+)\1', pic_xml)
        if not ref_m:
            return pic_xml
        ref_id = ref_m.group(2)
        old_member = id_to_old_member.get(ref_id) or id_to_old_member.get(ref_id.lower())
        if not old_member or old_member not in size_map:
            return pic_xml
        orig_sz, new_sz = size_map[old_member]
        if not orig_sz or not new_sz or orig_sz == new_sz or orig_sz[0] <= 0 or orig_sz[1] <= 0:
            return pic_xml
        sx, sy = new_sz[0] / orig_sz[0], new_sz[1] / orig_sz[1]

        def scale_clip(cm: re.Match) -> str:
            t = cm.group(0)
            for attr, sc in (('left', sx), ('right', sx), ('top', sy), ('bottom', sy)):
                t = re.sub(rf'(\b{attr}\s*=\s*["\'])(-?\d+)(["\'])', lambda m, s=sc: f"{m.group(1)}{int(round(int(m.group(2)) * s))}{m.group(3)}", t)
            return t

        def scale_dim(dm: re.Match) -> str:
            t = dm.group(0)
            for attr, sc in (('dimwidth', sx), ('dimheight', sy)):
                t = re.sub(rf'(\b{attr}\s*=\s*["\'])(-?\d+)(["\'])', lambda m, s=sc: f"{m.group(1)}{int(round(int(m.group(2)) * s))}{m.group(3)}", t)
            return t

        pic_xml = re.sub(r'<(?:\w+:)?imgClip\b[^>]*/?>', scale_clip, pic_xml)
        return re.sub(r'<(?:\w+:)?imgDim\b[^>]*/?>', scale_dim, pic_xml)

    return re.sub(r'<(?:\w+:)?pic\b(?:(?!</(?:\w+:)?pic>).)*</(?:\w+:)?pic>|<(?:\w+:)?pic\b[^>]*/\s*>', replace_pic, xml_text, flags=re.DOTALL)


def _verify_document(path, reader, cancel):
    checkpoint(cancel)
    if hasattr(reader, 'doc'):
        # The caller owns the PDF lock; do not create another PdfReader here.
        with reader.fitz.open(path) as verified:
            if verified.needs_pass or verified.page_count != reader.doc.page_count:
                raise ValueError('생성된 PDF 문서 검증에 실패했습니다.')
    else:
        with zipfile.ZipFile(path) as verified:
            for info in verified.infolist():
                checkpoint(cancel)
                with verified.open(info) as stream:
                    while stream.read(1024 * 1024):
                        checkpoint(cancel)
                if info.filename.lower().endswith(('.xml', '.rels', '.hpf', '.rdf')):
                    safe_xml(verified, info.filename)


def optimize_document(
    source: Path,
    destination: Path,
    settings: Settings | None = None,
    notify: Callable = lambda event: None,
    cancel=None,
    selected_keys=None,
    catalog=None,
    *,
    workers=None,
) -> dict:
    source = Path(source)
    ext = source.suffix.lower()
    if ext == '.hwp':
        raise ValueError('구형 한글(.hwp)은 지원하지 않습니다. 한글에서 개방형 한글(.hwpx)로 저장한 뒤 사용하세요.')
    if ext not in OPTIMIZABLE:
        raise ValueError('문서 내 이미지 직접 변환은 HWPX, PDF, XLSX, DOCX, PPTX 문서만 지원합니다.')

    s = settings or Settings()
    eff_base = replace(s, apply_document_crop=False)
    if eff_base.format == 'ORIGINAL':
        eff_base = replace(eff_base, format='JPEG')
    eff_base.validate()
    checkpoint(cancel)

    started = time.perf_counter()
    if workers is not None and (not isinstance(workers, int) or not 1 <= workers <= 4):
        raise ValueError('동시 변환 수는 1~4 범위로 지정하세요.')

    saved = failed = warned = processed = 0
    stopped = False
    records = []
    source_doc_bytes = source.stat().st_size
    want_body = s.apply_document_crop or (selected_keys is not None and any(str(k).startswith('occ:') for k in selected_keys))

    with tempfile.TemporaryDirectory(prefix="sunrise_image_") as staging, open_document(source, want_body, cancel) as reader:
        if catalog and Path(catalog.source).resolve() != source.resolve():
            raise ValueError('선택 목록의 원본문서가 일치하지 않습니다. 목록을 새로고침하세요.')
        current = catalog or reader.catalog()
        if catalog and getattr(catalog, 'fingerprint', None):
            stat = source.stat()
            if catalog.fingerprint != (stat.st_size, stat.st_mtime_ns):
                raise ValueError('목록을 만든 뒤 문서가 변경되었습니다. 목록을 새로고침하세요.')
        raw_items = current.items
        if selected_keys is not None:
            keys = set(selected_keys)
            if keys - {i.key for i in raw_items}:
                if ext != '.hwpx':
                    raise ValueError('선택 목록이 현재 문서와 일치하지 않습니다. 새로고침하세요.')
                with open_document(source, not want_body, cancel) as alt_reader:
                    alt_cat = alt_reader.catalog()
                if not (keys - {i.key for i in alt_cat.items}):
                    raw_items = [i for i in alt_cat.items if i.key in keys]
                else:
                    raise ValueError('선택 목록이 현재 문서와 일치하지 않습니다. 새로고침하세요.')
            else:
                raw_items = [i for i in raw_items if i.key in keys]

        seen_members = set()
        items = [replace(i, crop=None) for i in raw_items if not (i.member in seen_members or seen_members.add(i.member))]

        short_stem = safe_name(source.stem)[:50]
        folder = fresh_folder(Path(destination), f'{short_stem}_{eff_base.format}_문서경량화')
        output_doc = folder / f'{short_stem}_경량화{source.suffix}'
        notify({'type': 'begin', 'total': len(items), 'folder': str(folder)})
        for warning in current.warnings:
            notify({'type': 'warning', 'message': warning})

        raster_items = [i for i in items if PurePosixPath(i.member.replace('\\', '/')).suffix.lower() not in VECTOR_EXTS]
        vector_items = [i for i in items if PurePosixPath(i.member.replace('\\', '/')).suffix.lower() in VECTOR_EXTS]

        count = workers if workers is not None else min(4, max(1, (os.cpu_count() or 2) - 1))
        if workers is None and (len(raster_items) < 4 or all(i.size and i.size[0] * i.size[1] < 65_536 for i in raster_items)):
            count = 1

        existing_names = set(reader.z.namelist()) if hasattr(reader, 'z') else set()
        used_lower_names = {n.replace('\\', '/').lower() for n in existing_names}
        member_map: dict[str, str] = {}
        payload_map: dict[str, Path] = {}
        size_map: dict[str, tuple[tuple[int, int] | None, tuple[int, int] | None]] = {}

        notify_start = lambda item, idx: notify({'type': 'item_start', 'index': len(vector_items) + idx, 'total': len(items), 'member': item.member, 'key': item.key})
        def convert_for_document(data, item):
            if ext == '.pdf' and not item.meta.get('xref'):
                raise ValueError('PDF 인라인 이미지는 문서 내 교체를 지원하지 않아 원본을 유지합니다.')
            effective = eff_base
            protected = eff_base.format == 'JPEG' and eff_base.alpha == 'keep' and _has_transparency(data)
            if protected:
                effective = replace(eff_base, format='PNG', png_compression=9)
            result = convert_image(data, effective, item.member, cancel)
            if protected:
                result.notes.append('투명 배경(직인·로고) 유지를 위해 PNG 압축 적용')
            result.source_data = data
            return result

        conversions = None
        try:
            for v_item in vector_items:
                checkpoint(cancel)
                processed += 1
                saved += 1
                row = {
                    '내부 파일': v_item.member, '목록 ID': v_item.key, '본문 위치': v_item.location,
                    '저장 파일': v_item.member, '상태': '성공', '원본 바이트': v_item.stored_bytes,
                    '출력 바이트': v_item.stored_bytes, '목표 KB': eff_base.target_kb or '',
                    '목표 달성': '미적용', '비고': '벡터 이미지 원본 유지',
                }
                records.append(row)
                notify({'type': 'item', 'index': processed, 'total': len(items), 'row': row, 'folder': str(folder)})

            conversions = _conversion_results(reader, raster_items, eff_base, cancel, count, notify_start, converter=convert_for_document)
            for item, source_bytes, result, error in conversions:
                checkpoint(cancel)
                idx_now = processed + 1
                old_member = item.member
                row = {'내부 파일': old_member, '목록 ID': item.key, '본문 위치': item.location, '저장 파일': old_member, '상태': '', '원본 바이트': source_bytes if source_bytes is not None else item.stored_bytes}
                try:
                    if error is not None:
                        raise error
                    if ext == ".pdf" and not item.meta.get("xref"):
                        raise ValueError("PDF 인라인 이미지는 문서 내 교체를 지원하지 않아 원본을 유지합니다.")
                    checkpoint(cancel)
                    old_ext = PurePosixPath(old_member.replace('\\', '/')).suffix.lower()
                    raw_data = result.source_data
                    result.source_data = None
                    notes = list(result.notes)
                    out_data, out_ext, out_size = result.data, result.extension, result.size

                    if _same_format_ext(old_ext, out_ext) and eff_base.resize == 'original' and eff_base.rotate == 0 and not eff_base.grayscale and eff_base.alpha == 'keep' and eff_base.dpi is None and len(out_data) >= len(raw_data):
                        out_data, out_size = raw_data, result.source_size
                        notes.append('원본 용량이 이미 더 작아 원본 바이트 유지')

                    if _same_format_ext(old_ext, out_ext):
                        new_member = old_member
                    else:
                        p_obj = PurePosixPath(old_member.replace('\\', '/'))
                        candidate = str(p_obj.with_suffix(out_ext))
                        s_idx = 2
                        while candidate.lower() in used_lower_names:
                            candidate = str(p_obj.with_name(f'{p_obj.stem}_opt{s_idx}{out_ext}'))
                            s_idx += 1
                        new_member = candidate
                        used_lower_names.add(new_member.lower())

                    payload = Path(staging) / str(len(payload_map))
                    payload.write_bytes(out_data)
                    # Publish replacement metadata only after staging succeeds.
                    member_map[old_member] = new_member
                    payload_map[old_member] = payload
                    size_map[old_member] = (result.source_size, out_size)

                    status = '주의' if any(any(t in n for t in ('미달성', '미반영', '미제공', '원본 밖')) for n in notes) else '성공'
                    saved += 1
                    warned += status == '주의'
                    row.update({
                        '저장 파일': new_member, '상태': status,
                        '원본 가로': (result.source_size or ('', ''))[0], '원본 세로': (result.source_size or ('', ''))[1],
                        '출력 가로': (out_size or ('', ''))[0], '출력 세로': (out_size or ('', ''))[1],
                        '출력 바이트': len(out_data), 'DPI 가로': (result.dpi or ('', ''))[0], 'DPI 세로': (result.dpi or ('', ''))[1],
                        '실제 품질': result.quality or '', '목표 KB': eff_base.target_kb or '',
                        '목표 달성': '예' if result.target_met else ('아니오' if result.target_met is False else '미적용'),
                        '자르기 픽셀': '', '비고': '; '.join(notes),
                    })
                except Cancelled:
                    raise
                except Exception as exc:
                    failed += 1
                    row.update({'상태': '실패', '비고': str(exc)})
                records.append(row)
                processed = idx_now
                notify({'type': 'item', 'index': processed, 'total': len(items), 'row': row, 'folder': str(folder)})

            checkpoint(cancel)
            notify({'type': 'phase', 'message': '문서 생성 및 저장 중…'})
            handle, name = tempfile.mkstemp(prefix='.document_', suffix=source.suffix, dir=folder)
            os.close(handle)
            temp_doc = Path(name)
            if ext == '.pdf':
                try:
                    for item in raster_items:
                        old_m = item.member
                        xref = item.meta.get('xref') if getattr(item, 'meta', None) else None
                        if xref and old_m in payload_map:
                            pages = item.meta.get('pages', [1])
                            page = reader.doc[max(0, (pages[0] - 1) if pages else 0)]
                            if not hasattr(page, 'replace_image'):
                                raise RuntimeError('PDF 이미지 교체 기능이 없는 실행 환경입니다.')
                            checkpoint(cancel)
                            page.replace_image(xref, stream=payload_map[old_m].read_bytes())
                    reader.doc.save(temp_doc, garbage=4, deflate=True)
                    checkpoint(cancel)
                    _verify_document(temp_doc, reader, cancel)
                    temp_doc.replace(output_doc)
                finally:
                    temp_doc.unlink(missing_ok=True)
            else:
                id_to_old_member = {k: m for m in member_map for k in (PurePosixPath(m.replace('\\', '/')).stem, PurePosixPath(m.replace('\\', '/')).stem.lower())}
                hpf_texts: dict[str, bytes] = {}
                if ext == '.hwpx':
                    for fname in existing_names:
                        if fname.replace('\\', '/').lower().endswith('.hpf'):
                            raw_hpf, enc = _decode_xml_bytes(read_xml_bytes(reader.z, fname))
                            updated_hpf, parsed_map = _update_hwpx_hpf(raw_hpf, member_map)
                            id_to_old_member.update(parsed_map)
                            hpf_texts[fname] = updated_hpf.encode(enc)
                try:
                    with zipfile.ZipFile(temp_doc, 'w', compression=zipfile.ZIP_DEFLATED) as zout:
                        all_infos = [i for i in reader.z.infolist() if not i.is_dir()]
                        for info in [i for i in all_infos if i.filename == 'mimetype']:
                            zinfo = zipfile.ZipInfo('mimetype')
                            zinfo.compress_type = zipfile.ZIP_STORED
                            zinfo.extra = b''
                            zout.writestr(zinfo, reader.z.read(info.filename))
                        for info in [i for i in all_infos if i.filename != 'mimetype']:
                            checkpoint(cancel)
                            fname, norm_fname = info.filename, validate_archive_member(info.filename)
                            if fname in payload_map:
                                zout.write(payload_map[fname], member_map[fname], compress_type=zipfile.ZIP_DEFLATED)
                            elif fname in hpf_texts:
                                zout.writestr(fname, hpf_texts[fname], compress_type=zipfile.ZIP_DEFLATED)
                            elif ext == '.hwpx' and re.fullmatch(r'Contents/section\d+\.xml', norm_fname, re.I) and (size_map or member_map):
                                sec_xml, enc = _decode_xml_bytes(read_xml_bytes(reader.z, fname))
                                if size_map:
                                    sec_xml = _update_hwpx_section_xml(sec_xml, id_to_old_member, size_map)
                                if member_map:
                                    sec_xml = _update_hwpx_aux_xml(sec_xml, member_map)
                                zout.writestr(fname, sec_xml.encode(enc), compress_type=zipfile.ZIP_DEFLATED)
                            elif ext == '.hwpx' and norm_fname.lower().endswith(('.xml', '.rdf')) and member_map:
                                aux_xml, enc = _decode_xml_bytes(read_xml_bytes(reader.z, fname))
                                zout.writestr(fname, _update_hwpx_aux_xml(aux_xml, member_map).encode(enc), compress_type=zipfile.ZIP_DEFLATED)
                            elif ext in {'.xlsx', '.docx', '.pptx'} and norm_fname.lower().endswith('.rels') and member_map:
                                rels_xml, enc = _decode_xml_bytes(read_xml_bytes(reader.z, fname))
                                zout.writestr(fname, _update_openxml_rels(rels_xml, norm_fname, member_map).encode(enc), compress_type=zipfile.ZIP_DEFLATED)
                            elif ext in {'.xlsx', '.docx', '.pptx'} and norm_fname == '[Content_Types].xml' and member_map:
                                ct_xml, enc = _decode_xml_bytes(read_xml_bytes(reader.z, fname))
                                zout.writestr(fname, _update_content_types(ct_xml, member_map).encode(enc), compress_type=zipfile.ZIP_DEFLATED)
                            else:
                                with reader.z.open(info) as src, zout.open(fname, 'w') as dst:
                                    while True:
                                        checkpoint(cancel)
                                        block = src.read(1024 * 1024)
                                        if not block:
                                            break
                                        dst.write(block)
                    checkpoint(cancel)
                    _verify_document(temp_doc, reader, cancel)
                    temp_doc.replace(output_doc)
                finally:
                    temp_doc.unlink(missing_ok=True)

            if output_doc.is_file():
                direct_doc = Path(destination) / f'{short_stem}_경량화{source.suffix}'
                suffix = 2
                while True:
                    try:
                        with direct_doc.open('xb'):
                            pass
                        break
                    except FileExistsError:
                        direct_doc = Path(destination) / f'{short_stem}_{suffix}_경량화{source.suffix}'
                        suffix += 1
                temp_direct = None
                try:
                    fd, temp_name = tempfile.mkstemp(prefix='.copy_', suffix=source.suffix, dir=destination)
                    os.close(fd)
                    temp_direct = Path(temp_name)
                    if direct_doc.resolve() != source.resolve():
                        shutil.copy2(output_doc, temp_direct)
                        temp_direct.replace(direct_doc)
                except OSError as exc:
                    direct_doc.unlink(missing_ok=True)
                    notify({'type': 'warning', 'message': f'루트 경량화 사본 저장 생략 ({direct_doc.name}): {exc}'})
                finally:
                    if temp_direct is not None:
                        temp_direct.unlink(missing_ok=True)
        except Cancelled:
            stopped = True
        finally:
            if conversions is not None:
                conversions.close()
            if not output_doc.is_file():
                for row in records:
                    if row['상태'] != '실패':
                        row['상태'] = '미저장'
                        row['비고'] += '; 문서 저장 전 중지 또는 실패'
            fields = [
                '내부 파일', '목록 ID', '본문 위치', '저장 파일', '상태',
                '원본 바이트', '출력 바이트', '원본 가로', '원본 세로',
                '출력 가로', '출력 세로', 'DPI 가로', 'DPI 세로',
                '실제 품질', '목표 KB', '목표 달성', '자르기 픽셀', '비고',
            ]
            with (folder / '추출결과.csv').open('w', encoding='utf-8-sig', newline='') as handle:
                writer = csv.DictWriter(handle, fieldnames=fields, extrasaction='ignore')
                writer.writeheader()
                writer.writerows(csv_record(row) for row in records)

    output_doc_bytes = output_doc.stat().st_size if output_doc.is_file() else source_doc_bytes
    return {
        'mode': 'optimize', 'folder': str(folder),
        'output_file': str(output_doc) if output_doc.is_file() else '',
        'source_doc_bytes': source_doc_bytes, 'output_doc_bytes': output_doc_bytes,
        'saved': saved if output_doc.is_file() else 0, 'converted': saved, 'failed': failed, 'warned': warned,
        'processed': processed, 'total': len(items), 'cancelled': stopped,
        'elapsed_seconds': time.perf_counter() - started,
    }
