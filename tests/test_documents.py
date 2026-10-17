import io
import tempfile
import unittest
import zipfile
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from document_reader import *
from document_optimizer import optimize_document
from image_engine import Settings, extract_images, convert_item
from fixtures import hwpx, hwp, image_bytes
from PIL import Image


class DocumentTests(unittest.TestCase):
    def test_hwpx_occurrences_selection_and_color(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / 'test.hwpx'
            hwpx(p)
            asset = scan_document(p)
            body = scan_document(p, True)
            self.assertEqual(len(asset.items), 2)
            self.assertEqual(len(body.items), 3)
            self.assertEqual(body.items[0].member, body.items[1].member)
            self.assertNotEqual(body.items[0].key, body.items[1].key)
            out = extract_images(p, Path(t), Settings(format='PNG', apply_document_crop=True), selected_keys=[body.items[1].key], catalog=body)
            self.assertEqual(out['saved'], 1)
            with Image.open(next(Path(out['folder']).glob('*.png'))) as im:
                self.assertEqual(im.size, (50, 60))
                self.assertEqual(im.convert('RGB').getpixel((25, 20)), (0, 0, 255))

    def test_crop_fallback_error_padding_and_original_conflict(self):
        self.assertEqual(Crop((0, 0, 3750, 4500)).pixels((100, 60))[0], (0, 0, 50, 60))
        box, notes = Crop((-750, 0, 3750, 4500), (7500, 4500)).pixels((100, 60))
        self.assertEqual(box, (-10, 0, 50, 60))
        self.assertTrue(notes)
        with self.assertRaises(ValueError):
            Crop((0, 0, 0, 0)).pixels((100, 60))
        with self.assertRaises(ValueError):
            Settings(format='ORIGINAL', apply_document_crop=True).validate()
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / 'test.hwpx'
            hwpx(p, malformed=True)
            cat = scan_document(p, True)
            result = extract_images(p, Path(t), Settings(format='PNG', apply_document_crop=True), catalog=cat)
            self.assertEqual((result['saved'], result['failed']), (2, 1))

    def test_office_three_formats_and_no_ole(self):
        with tempfile.TemporaryDirectory() as t:
            for ext, prefix in [('.docx', 'word/media'), ('.xlsx', 'xl/media'), ('.pptx', 'ppt/media')]:
                with self.subTest(ext=ext):
                    path = Path(t) / ('office' + ext)
                    with zipfile.ZipFile(path, 'w') as z:
                        z.writestr(prefix + '/image1.png', image_bytes())
                        z.writestr(prefix + '/image2.jpg', image_bytes(fmt='JPEG'))
                        z.writestr('docProps/thumbnail.jpeg', image_bytes(fmt='JPEG'))
                        z.writestr(prefix + '/movie.mp4', b'movie')
                    cat = scan_document(path)
                    self.assertEqual(len(cat.items), 2)
                    result = extract_images(path, Path(t), Settings(format='ORIGINAL'), selected_keys=[cat.items[0].key], catalog=cat)
                    self.assertEqual(result['saved'], 1)
                    self.assertEqual(next(Path(result['folder']).glob('*.png')).read_bytes(), image_bytes())

    def test_pdf_pages_duplicate_alpha_and_output(self):
        import pymupdf
        with tempfile.TemporaryDirectory() as t:
            path = Path(t) / 'test.pdf'
            doc = pymupdf.open()
            im = Image.new('RGBA', (30, 20), (30, 80, 140, 110))
            b = io.BytesIO()
            im.save(b, 'PNG')
            for _ in range(2):
                page = doc.new_page()
                page.insert_image(pymupdf.Rect(0, 0, 100, 80), stream=b.getvalue())
            doc.save(path)
            doc.close()
            cat = scan_document(path)
            self.assertEqual(len(cat.items), 1)
            self.assertEqual(cat.items[0].meta['pages'], [1, 2])
            result = extract_images(path, Path(t), Settings(format='PNG'))
            with Image.open(next(Path(result['folder']).glob('*.png'))) as image:
                self.assertEqual(image.size, (30, 20))
                self.assertIn('A', image.getbands())
                self.assertAlmostEqual(image.getpixel((1, 1))[3], 110, delta=1)

    def test_pdf_vector_only_and_encrypted(self):
        import pymupdf
        with tempfile.TemporaryDirectory() as t:
            path = Path(t) / 'vector.pdf'
            doc = pymupdf.open()
            page = doc.new_page()
            page.insert_text((20, 20), 'Text only')
            doc.save(path)
            doc.close()
            self.assertEqual(len(scan_document(path).items), 0)
            doc = pymupdf.open(path)
            locked = Path(t) / 'locked.pdf'
            doc.save(locked, encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw='a', user_pw='b')
            doc.close()
            with self.assertRaisesRegex(ValueError, '암호'):
                scan_document(locked)

    def test_archive_member_path_traversal_rejected(self):
        from image_engine import validate_archive_member
        for bad in ['../evil.png', 'BinData/../../evil.png', '/etc/passwd', 'C:/evil.png', '']:
            with self.assertRaisesRegex(ValueError, '안전하지 않은 문서 내부 경로'):
                validate_archive_member(bad)
        self.assertEqual(validate_archive_member('BinData\image1.png'), 'BinData/image1.png')

    def test_legacy_hwp_and_binary_office_excluded_across_all_features(self):
        self.assertNotIn('.hwp', SUPPORTED)
        self.assertNotIn('.hwp', OPTIMIZABLE)
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / 'legacy.hwp'
            hwp(p)
            with self.assertRaisesRegex(ValueError, '구형 한글'):
                scan_document(p)
            with self.assertRaisesRegex(ValueError, '구형 한글'):
                open_document(p)
            with self.assertRaisesRegex(ValueError, '구형 한글'):
                extract_images(p, Path(t))
            with self.assertRaisesRegex(ValueError, '구형 한글'):
                optimize_document(p, Path(t))
            for ext in ['.doc', '.xls', '.ppt']:
                with self.assertRaisesRegex(ValueError, '지원하지'):
                    open_document(Path(t) / ('test' + ext))

    def test_optimize_hwpx_in_place_jpg_and_resize_updates_manifest_and_clip(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / 'sample.hwpx'
            hwpx(p)
            cat = scan_document(p)
            # Convert only the first image (BinData/image1.png) to JPEG at 50% size in-place
            res = optimize_document(
                p,
                Path(t) / 'opt',
                Settings(format='JPEG', quality=85, resize='percent', percent=50),
                selected_keys=[cat.items[0].key],
                catalog=cat,
            )
            self.assertEqual(res['saved'], 1)
            opt_path = Path(res['output_file'])
            self.assertTrue(opt_path.is_file())
            with zipfile.ZipFile(opt_path) as z:
                names = z.namelist()
                self.assertIn('BinData/image1.jpg', names)
                self.assertNotIn('BinData/image1.png', names)
                # Second image was not selected so it remains PNG
                self.assertIn('BinData/unused.png', names)
                hpf = z.read('Contents/content.hpf').decode('utf-8')
                self.assertIn('BinData/image1.jpg', hpf)
                sec = z.read('Contents/section0.xml').decode('utf-8')
                # 100x60 -> 50x30 => dimwidth=3750, dimheight=2250, clip right=1875
                self.assertIn('dimwidth="3750"', sec)
                self.assertIn('dimheight="2250"', sec)
                self.assertIn('right="1875"', sec)
            # Re-scan the optimized HWPX with body crop enabled to verify valid coordinates
            opt_body = scan_document(opt_path, True)
            self.assertEqual(len(opt_body.items), 3)
            self.assertEqual(opt_body.items[0].format, 'JPEG')
            self.assertEqual(opt_body.items[0].size, (50, 30))
            box, _ = opt_body.items[0].crop.pixels(opt_body.items[0].size)
            self.assertEqual(box, (0, 0, 25, 30))

    def test_optimize_excel_xlsx_in_place_jpg_and_target_kb(self):
        with tempfile.TemporaryDirectory() as t:
            xlsx = Path(t) / 'sheet.xlsx'
            # Create a noisy PNG that is larger than 15 KiB so target_kb=8 KiB JPG shrinks it significantly
            im = Image.effect_noise((400, 300), 80).convert('RGB')
            buf = io.BytesIO()
            im.save(buf, 'PNG')
            large_png = buf.getvalue()
            with zipfile.ZipFile(xlsx, 'w') as z:
                z.writestr(
                    '[Content_Types].xml',
                    '<?xml version="1.0" encoding="UTF-8"?>'
                    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                    '<Default Extension="xml" ContentType="application/xml"/>'
                    '<Default Extension="png" ContentType="image/png"/>'
                    '</Types>',
                )
                z.writestr(
                    'xl/drawings/_rels/drawing1.xml.rels',
                    '<?xml version="1.0" encoding="UTF-8"?>'
                    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../media/image1.png"/>'
                    '</Relationships>',
                )
                z.writestr('xl/media/image1.png', large_png)
            res = optimize_document(
                xlsx,
                Path(t) / 'xlsx_opt',
                Settings(format='JPEG', quality=85, target_kb=8, shrink_for_target=True),
            )
            self.assertEqual(res['saved'], 1)
            opt_xlsx = Path(res['output_file'])
            self.assertTrue(opt_xlsx.is_file())
            self.assertLess(res['output_doc_bytes'], res['source_doc_bytes'])
            with zipfile.ZipFile(opt_xlsx) as z:
                self.assertIn('xl/media/image1.jpg', z.namelist())
                self.assertNotIn('xl/media/image1.png', z.namelist())
                rels = z.read('xl/drawings/_rels/drawing1.xml.rels').decode('utf-8')
                self.assertIn('Target="../media/image1.jpg"', rels)
                ct = z.read('[Content_Types].xml').decode('utf-8')
                self.assertIn('Extension="jpg"', ct)
                self.assertIn('image/jpeg', ct)
                self.assertLessEqual(len(z.read('xl/media/image1.jpg')), 8 * 1024)

    def test_empty_selection_stale_catalog_and_unknown_key(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / 'test.hwpx'
            hwpx(p)
            cat = scan_document(p)
            empty = extract_images(p, Path(t), selected_keys=[], catalog=cat)
            self.assertEqual(empty['saved'], 0)
            with self.assertRaises(ValueError):
                extract_images(p, Path(t), selected_keys=['bad'], catalog=cat)
            p.write_bytes(p.read_bytes() + b'trailer')
            with self.assertRaisesRegex(ValueError, '변경'):
                extract_images(p, Path(t), catalog=cat)



    def test_real_hancom_hwpx_paired_tags_case_mismatch_300dpi_and_vector_preserved(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / 'real_hancom.hwpx'
            im = Image.effect_noise((400, 240), 90).convert('RGB')
            buf = io.BytesIO()
            im.save(buf, 'PNG')
            big_png = buf.getvalue()
            hpf = (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>'
                '<opf:package xmlns:opf="http://www.idpf.org/2007/opf/">'
                '<opf:manifest>'
                '<opf:item id="header" href="Contents/header.xml" media-type="application/xml"></opf:item>'
                '<opf:item id="img_main" href="BinData/Photo_Main.PNG" media-type="image/png" isEmbeded="1"></opf:item>'
                '<opf:item id="vec1" href="BinData/eq1.wmf" media-type="application/x-msmetafile" isEmbeded="1"></opf:item>'
                '<opf:item id="section0" href="Contents/section0.xml" media-type="application/xml"></opf:item>'
                '</opf:manifest></opf:package>'
            )
            # 300 DPI coordinate space: 400*24=9600, 240*24=5760, with paired closing tags ></hp:imgClip> and ></hp:imgDim>
            sec = (
                '<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" '
                'xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph" '
                'xmlns:hc="http://www.hancom.co.kr/hwpml/2011/core">'
                '<hp:p><hp:run><hp:pic id="10">'
                '<hc:img binaryItemIDRef="img_main" bright="0" contrast="0" effect="REAL_PIC" alpha="0"></hc:img>'
                '<hp:imgClip left="0" right="4800" top="0" bottom="5760"></hp:imgClip>'
                '<hp:imgDim dimwidth="9600" dimheight="5760"></hp:imgDim>'
                '</hp:pic></hp:run></hp:p></hs:sec>'
            )
            manifest_xml = (
                '<odf:manifest xmlns:odf="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0">'
                '<odf:file-entry full-path="BinData/photo_main.png" media-type="image/png"/>'
                '</odf:manifest>'
            )
            with zipfile.ZipFile(p, 'w') as z:
                z.writestr('META-INF/manifest.xml', manifest_xml)
                z.writestr('Contents/content.hpf', hpf)
                z.writestr('Contents/section0.xml', sec)
                z.writestr('BinData/photo_main.png', big_png)
                z.writestr('BinData/eq1.wmf', b'\xd7\xcd\xc6\x9a\x00\x00wmfdata')
                z.writestr('mimetype', 'application/hwp+zip')

            # Keep source resolution when shrink_for_target is explicitly false.
            res = optimize_document(p, Path(t) / 'out_real', Settings(format='JPEG', target_kb=10, shrink_for_target=False))
            self.assertEqual(res['failed'], 0)
            self.assertEqual(res['saved'], 2)
            self.assertLess(res['output_doc_bytes'], res['source_doc_bytes'])
            opt_path = Path(res['output_file'])
            with zipfile.ZipFile(opt_path) as z:
                infos = z.infolist()
                # mimetype MUST be first and uncompressed (ZIP_STORED)
                self.assertEqual(infos[0].filename, 'mimetype')
                self.assertEqual(infos[0].compress_type, zipfile.ZIP_STORED)
                self.assertIn('BinData/photo_main.jpg', z.namelist())
                self.assertIn('BinData/eq1.wmf', z.namelist())
                out_hpf = z.read('Contents/content.hpf').decode('utf-8')
                self.assertIn('BinData/photo_main.jpg', out_hpf)
                self.assertIn('image/jpeg', out_hpf)
                out_manifest = z.read('META-INF/manifest.xml').decode('utf-8')
                self.assertIn('BinData/photo_main.jpg', out_manifest)
            # Re-scan optimized HWPX with body=True to verify crop ratio (left half: width/2 x height) is preserved
            body_cat = scan_document(opt_path, True)
            pic_item = next(i for i in body_cat.items if i.key.startswith('occ:'))
            box, _ = pic_item.crop.pixels(pic_item.size)
            self.assertEqual(box[2] - box[0], round(pic_item.size[0] / 2))
            self.assertEqual(box[3] - box[1], pic_item.size[1])



    def test_optimize_hwpx_preserves_transparent_stamp_as_png_while_converting_opaque_to_jpg(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / 'stamp_and_photo.hwpx'
            # Opaque photo PNG
            photo = Image.effect_noise((200, 150), 60).convert('RGB')
            b_photo = io.BytesIO(); photo.save(b_photo, 'PNG')
            # Transparent stamp PNG (alpha=0 background with red stamp circle)
            stamp = Image.new('RGBA', (100, 100), (0, 0, 0, 0))
            for x in range(20, 80):
                for y in range(20, 80):
                    stamp.putpixel((x, y), (220, 20, 20, 255))
            b_stamp = io.BytesIO(); stamp.save(b_stamp, 'PNG')
            hpf = (
                '<package><manifest>'
                '<item id="photo1" href="BinData/photo1.png" media-type="image/png"/>'
                '<item id="stamp1" href="BinData/stamp1.png" media-type="image/png"/>'
                '</manifest></package>'
            )
            with zipfile.ZipFile(p, 'w') as z:
                z.writestr('mimetype', 'application/hwp+zip')
                z.writestr('Contents/content.hpf', hpf)
                z.writestr('Contents/section0.xml', '<sec/>')
                z.writestr('BinData/photo1.png', b_photo.getvalue())
                z.writestr('BinData/stamp1.png', b_stamp.getvalue())
            res = optimize_document(p, Path(t) / 'out_stamp', Settings(format='JPEG', alpha='keep', quality=80))
            self.assertEqual(res['saved'], 2)
            self.assertEqual(res['failed'], 0)
            with zipfile.ZipFile(res['output_file']) as z:
                # Opaque photo converted to JPG, transparent stamp preserved as PNG
                self.assertIn('BinData/photo1.jpg', z.namelist())
                self.assertIn('BinData/stamp1.png', z.namelist())
                with Image.open(io.BytesIO(z.read('BinData/stamp1.png'))) as st_im:
                    self.assertIn('A', st_im.getbands())
                    self.assertEqual(st_im.getpixel((0, 0))[3], 0)



    def test_stabilization_corrupted_zip_renamed_ole_and_self_closing_pic(self):
        with tempfile.TemporaryDirectory() as t:
            # 1. OLE2 / DRM file disguised with .hwpx or .xlsx extension
            fake_hwpx = Path(t) / 'disguised.hwpx'
            fake_hwpx.write_bytes(b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1' + b'\x00' * 512)
            with self.assertRaisesRegex(ValueError, '구형 바이너리|문서보안'):
                scan_document(fake_hwpx)
            # 2. Corrupted ZIP disguised as .xlsx
            bad_xlsx = Path(t) / 'corrupt.xlsx'
            bad_xlsx.write_bytes(b'not a valid zip archive')
            with self.assertRaisesRegex(ValueError, '손상되었거나 올바르지 않은'):
                scan_document(bad_xlsx)
            # 3. HWPX with a self-closing <hp:pic id="0"/> before a real <hp:pic id="1">...</hp:pic>
            sc_hwpx = Path(t) / 'self_closing.hwpx'
            sec = (
                '<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" '
                'xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph" '
                'xmlns:hc="http://www.hancom.co.kr/hwpml/2011/core">'
                '<hp:pic id="0"/>'
                '<hp:p><hp:run><hp:pic id="1">'
                '<hp:imgClip left="0" top="0" right="7500" bottom="4500"/>'
                '<hp:imgDim dimwidth="7500" dimheight="4500"/>'
                '<hc:img binaryItemIDRef="image1"/>'
                '</hp:pic></hp:run></hp:p></hs:sec>'
            )
            with zipfile.ZipFile(sc_hwpx, 'w') as z:
                z.writestr('mimetype', 'application/hwp+zip')
                z.writestr('Contents/content.hpf', '<package><manifest><item id="image1" href="BinData/image1.png"/></manifest></package>')
                z.writestr('Contents/section0.xml', sec)
                z.writestr('BinData/image1.png', image_bytes((100, 60)))
            res = optimize_document(sc_hwpx, Path(t) / 'sc_out', Settings(format='JPEG', resize='percent', percent=50))
            self.assertEqual(res['saved'], 1)
            with zipfile.ZipFile(res['output_file']) as z:
                out_sec = z.read('Contents/section0.xml').decode('utf-8')
                self.assertIn('dimwidth="3750"', out_sec)
                self.assertIn('right="3750"', out_sec)


if __name__ == '__main__':
    unittest.main(verbosity=2)
