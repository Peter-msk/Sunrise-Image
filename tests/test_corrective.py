import io,tempfile,threading,unittest,zipfile,sys,hashlib
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image
from document_optimizer import optimize_document
from document_reader import scan_document,ZipReader
from image_engine import Settings,convert_image
from fixtures import hwpx,image_bytes
import build_windows

class CorrectiveTests(unittest.TestCase):
    def test_quality_resolution_and_single_document_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'a.hwpx';hwpx(p);counts={};original=ZipReader.read
            def read(reader,item):
                counts[item.member]=counts.get(item.member,0)+1
                return original(reader,item)
            with patch.object(ZipReader,'read',read):
                r=optimize_document(p,Path(tmp)/'out',Settings(format='JPEG',quality=97),workers=2)
            with zipfile.ZipFile(r['output_file']) as z:
                self.assertEqual(z.read('BinData/image1.jpg'),convert_image(image_bytes(),Settings(format='JPEG',quality=97)).data)
            self.assertTrue(all(v==1 for v in counts.values()))
            r=optimize_document(p,Path(tmp)/'out2',Settings(format='JPEG',target_kb=1,shrink_for_target=False))
            with zipfile.ZipFile(r['output_file']) as z:
                with Image.open(io.BytesIO(z.read('BinData/image1.jpg'))) as im:self.assertEqual(im.size,(100,60))

    def test_partial_transparency_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'a.docx';im=Image.new('RGBA',(200,100),(50,60,70,254));b=io.BytesIO();im.save(b,'PNG',compress_level=9)
            with zipfile.ZipFile(p,'w') as z:z.writestr('word/media/a.png',b.getvalue())
            r=optimize_document(p,Path(tmp)/'out',Settings(format='JPEG',alpha='keep'))
            with zipfile.ZipFile(r['output_file']) as z:
                with Image.open(io.BytesIO(z.read('word/media/a.png'))) as out:self.assertEqual(out.getpixel((0,0))[3],254)

    def test_repeated_output_preserves_previous_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'a.hwpx';hwpx(p);dest=Path(tmp)/'out'
            optimize_document(p,dest);copy=dest/'a_경량화.hwpx';digest=hashlib.sha256(copy.read_bytes()).hexdigest()
            optimize_document(p,dest,Settings(format='PNG'))
            self.assertEqual(hashlib.sha256(copy.read_bytes()).hexdigest(),digest)
            self.assertTrue((dest/'a_2_경량화.hwpx').exists())

    def test_cancel_reports_no_unwritten_document_as_saved(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'a.hwpx';hwpx(p);cancel=threading.Event()
            def notify(ev):
                if ev['type']=='phase':cancel.set()
            r=optimize_document(p,Path(tmp)/'out',notify=notify,cancel=cancel)
            self.assertTrue(r['cancelled']);self.assertEqual(r['saved'],0);self.assertFalse(r['output_file']);self.assertGreater(r['converted'],0)
            self.assertFalse(list((Path(tmp)/'out').rglob('*.tmp')))

    def test_vector_raster_progress_ordinals(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'a.docx'
            with zipfile.ZipFile(p,'w') as z:
                z.writestr('word/media/a.svg',b'<svg/>');z.writestr('word/media/b.png',image_bytes())
            events=[];r=optimize_document(p,Path(tmp)/'out',notify=events.append)
            self.assertEqual([e['index'] for e in events if e['type']=='item_start'],[2]);self.assertEqual(r['saved'],2)

    def test_pdf_inline_failure_preserves_image(self):
        import pymupdf
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'inline.pdf';doc=pymupdf.open();page=doc.new_page();content=b'q 100 0 0 100 0 0 cm BI /W 1 /H 1 /CS /RGB /BPC 8 ID '+bytes([255,0,0])+b' EI Q';xref=doc.get_new_xref();doc.update_object(xref,'<<>>');doc.update_stream(xref,content);page.set_contents(xref);doc.save(p);doc.close()
            self.assertTrue(scan_document(p).items[0].meta['inline'])
            r=optimize_document(p,Path(tmp)/'out');self.assertEqual(r['saved'],0);self.assertEqual(r['failed'],1)
            self.assertEqual(len(scan_document(Path(r['output_file'])).items),1)

    def test_wrong_dependency_version_is_not_reused(self):
        with patch.object(build_windows.importlib.metadata,'version',return_value='0.0'):
            self.assertFalse(build_windows._dependencies_ready())

    def test_staged_payloads_are_files_and_are_cleaned(self):
        import document_optimizer
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'a.hwpx';hwpx(p);seen=[];original=document_optimizer.tempfile.TemporaryDirectory
            def staging(*args,**kwargs):
                obj=original(*args,**kwargs);seen.append(Path(obj.name));return obj
            def notify(ev):
                if ev['type']=='phase':
                    self.assertEqual(len(list(seen[0].iterdir())),2)
                    self.assertTrue(all(x.is_file() for x in seen[0].iterdir()))
            with patch.object(document_optimizer.tempfile,'TemporaryDirectory',staging):
                optimize_document(p,Path(tmp)/'out',notify=notify)
            self.assertFalse(seen[0].exists())

    def test_pdf_xref_replacement_is_written_and_source_is_unchanged(self):
        import pymupdf
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'a.pdf';doc=pymupdf.open();page=doc.new_page();page.insert_image(pymupdf.Rect(0,0,100,60),stream=image_bytes());doc.save(p);doc.close()
            digest=hashlib.sha256(p.read_bytes()).hexdigest()
            r=optimize_document(p,Path(tmp)/'out',Settings(format='JPEG',resize='percent',percent=50))
            self.assertEqual(r['saved'],1);self.assertEqual(scan_document(Path(r['output_file'])).items[0].size,(50,30))
            self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(),digest)

    def test_cancel_during_vector_items_reports_zero_saved_and_writes_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'vec.docx'
            with zipfile.ZipFile(p,'w') as z:
                z.writestr('word/media/a.svg',b'<svg/>')
                z.writestr('word/media/b.wmf',b'wmfdata')
            cancel=threading.Event()
            def notify(ev):
                if ev['type']=='item' and ev['index']==1:
                    cancel.set()
            r=optimize_document(p,Path(tmp)/'out',notify=notify,cancel=cancel)
            self.assertTrue(r['cancelled'])
            self.assertEqual(r['saved'],0)
            self.assertEqual(r['converted'],1)
            self.assertFalse(r['output_file'])
            self.assertTrue((Path(r['folder'])/'추출결과.csv').is_file())

    def test_selected_lossless_only_conversion_keeps_unselected_images_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'mixed.docx'
            png_data = image_bytes((120, 80), 'PNG')
            jpg_data = image_bytes((100, 60), 'JPEG')
            with zipfile.ZipFile(p, 'w') as z:
                z.writestr('[Content_Types].xml', '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="png" ContentType="image/png"/><Default Extension="jpeg" ContentType="image/jpeg"/></Types>')
                z.writestr('word/_rels/document.xml.rels', '<Relationships><Relationship Id="rId1" Target="media/a.png"/><Relationship Id="rId2" Target="media/b.jpeg"/></Relationships>')
                z.writestr('word/media/a.png', png_data)
                z.writestr('word/media/b.jpeg', jpg_data)
            cat = scan_document(p)
            lossless_keys = {i.key for i in cat.items if i.format.upper() in {'PNG', 'BMP', 'TIFF'}}
            self.assertEqual(len(lossless_keys), 1)
            r = optimize_document(p, Path(tmp) / 'out', Settings(format='JPEG', quality=85), selected_keys=lossless_keys, catalog=cat)
            self.assertEqual(r['saved'], 1)
            with zipfile.ZipFile(r['output_file']) as zout:
                names = set(zout.namelist())
                self.assertIn('word/media/a.jpg', names)
                self.assertNotIn('word/media/a.png', names)
                self.assertIn('word/media/b.jpeg', names)
                self.assertEqual(zout.read('word/media/b.jpeg'), jpg_data)

