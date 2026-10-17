import csv,io,re,sys,tempfile,threading,time,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image
import image_engine as engine
from image_engine import Settings,extract_images,convert_item,convert_image
from document_reader import ZipReader,PdfReader,ImageItem,Crop,scan_document
from fixtures import image_bytes,hwpx


def outputs(result):
    files={}
    for p in Path(result['folder']).iterdir():
        # Pillow includes a transient BytesIO address in corrupt-input errors.
        files[p.name]=re.sub(r'0x[0-9a-fA-F]+','0xADDRESS',p.read_text(encoding='utf-8-sig')) if p.suffix=='.csv' else p.read_bytes()
    return files


def source(root,count=8,broken=False):
    p=root/'parallel.docx'
    with zipfile.ZipFile(p,'w') as z:
        for i in range(count):
            im=Image.new('RGBA' if i%2 else 'RGB',(120,80),(i*20,80,140,110) if i%2 else (i*20,80,140))
            b=io.BytesIO();im.save(b,'PNG',dpi=(144,144))
            z.writestr(f'word/media/image{i:02d}.png',b'broken' if broken and i==2 else b.getvalue())
    return p


class SpeedTests(unittest.TestCase):
    def test_parallel_bytes_and_csv_equal_serial_for_all_formats(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);p=source(root,broken=True);cat=scan_document(p)
            for fmt in [*engine.FORMATS,'ORIGINAL']:
                with self.subTest(format=fmt):
                    s=Settings(format=fmt,dpi=300,resize='percent',percent=75,target_kb=5,shrink_for_target=True)
                    a=extract_images(p,root,s,catalog=cat,workers=1)
                    b=extract_images(p,root,s,catalog=cat,workers=4)
                    self.assertEqual(outputs(a),outputs(b));self.assertEqual(b['failed'],1)
                    self.assertEqual(b['saved'],7);self.assertGreater(b['elapsed_seconds'],0)

    def test_crop_single_decode_and_padding_pixels(self):
        data=image_bytes();item=ImageItem('key','image.png','image.png',crop=Crop((-750,0,3750,4500),(7500,4500)))
        with patch.object(engine,'open_raster',wraps=engine.open_raster) as opened:
            out=convert_item(data,item,Settings(format='PNG',apply_document_crop=True))
            self.assertEqual(opened.call_count,1)
        with Image.open(io.BytesIO(out.data)) as im:
            self.assertEqual(im.size,(60,60));self.assertEqual(im.getpixel((0,20))[3],0)
            self.assertEqual(im.getpixel((20,20))[:3],(255,0,0))

    def test_target_does_not_repeat_ceiling_encoding(self):
        import random
        im=Image.frombytes('RGB',(256,128),random.Random(7).randbytes(256*128*3))
        b=io.BytesIO();im.save(b,'PNG')
        for fmt,quality in [('PNG',95),('JPEG',95),('JPEG',1)]:
            with self.subTest(format=fmt,quality=quality):
                with patch.object(engine,'encode',wraps=engine.encode) as encoded:
                    convert_image(b.getvalue(),Settings(format=fmt,quality=quality,target_kb=1))
                    ceilings=[call for call in encoded.call_args_list if call.args[2]==quality]
                    self.assertEqual(len(ceilings),1)

    def test_parallel_cancel_keeps_only_committed_output(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);p=source(root);cancel=threading.Event();events=[]
            def notify(event):
                if event['type']=='item':events.append(event);cancel.set()
            result=extract_images(p,root,Settings(format='PNG'),notify,cancel,workers=4)
            self.assertTrue(result['cancelled']);self.assertEqual(result['saved'],1)
            self.assertEqual(len(list(Path(result['folder']).glob('*.png'))),1)
            with (Path(result['folder'])/'추출결과.csv').open(encoding='utf-8-sig') as h:self.assertEqual(len(list(csv.DictReader(h))),1)
            self.assertEqual(len(events),1)

    def test_readers_stay_on_coordinator_and_conversion_is_parallel(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);p=source(root,4);cat=scan_document(p)
            owner=threading.get_ident();barrier=threading.Barrier(4);read_threads=[];convert_threads=set();events=[]
            original_read=ZipReader.read;original_convert=engine.convert_item
            def read(reader,item):
                read_threads.append(threading.get_ident());return original_read(reader,item)
            def convert(*args):
                convert_threads.add(threading.get_ident());barrier.wait(timeout=5);return original_convert(*args)
            with patch.object(ZipReader,'read',read),patch.object(engine,'convert_item',convert):
                result=extract_images(p,root,Settings(format='PNG'),events.append,catalog=cat,workers=4)
            self.assertEqual(result['failed'],0);self.assertEqual(set(read_threads),{owner})
            self.assertEqual(len(convert_threads),4);self.assertNotIn(owner,convert_threads)
            self.assertEqual([e['index'] for e in events if e['type']=='item'],[1,2,3,4])

    def test_memory_budget_forces_one_large_conversion_at_a_time(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);p=source(root,4);original=engine.convert_item;active=peak=0;lock=threading.Lock()
            def convert(*args):
                nonlocal active,peak
                with lock:active+=1;peak=max(peak,active)
                try:time.sleep(.005);return original(*args)
                finally:
                    with lock:active-=1
            with patch.object(engine,'_working_bytes',return_value=engine.CONVERSION_MEMORY_BUDGET),patch.object(engine,'convert_item',convert):
                result=extract_images(p,root,Settings(format='PNG'),workers=4)
            self.assertEqual(result['saved'],4);self.assertEqual(peak,1)

    def test_pdf_parallel_matches_serial_without_threaded_pdf_calls(self):
        import pymupdf
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);p=root/'images.pdf';doc=pymupdf.open()
            for i in range(6):
                image=Image.new('RGBA',(30,20),(i*30,80,140,110));b=io.BytesIO();image.save(b,'PNG')
                page=doc.new_page();page.insert_image(pymupdf.Rect(0,0,90,60),stream=b.getvalue())
            doc.save(p);doc.close();cat=scan_document(p);self.assertEqual(len(cat.items),6)
            owner=threading.get_ident();read=PdfReader.read
            def checked(reader,item):
                self.assertEqual(threading.get_ident(),owner);return read(reader,item)
            with patch.object(PdfReader,'read',checked):
                a=extract_images(p,root,Settings(format='PNG'),catalog=cat,workers=1)
                b=extract_images(p,root,Settings(format='PNG'),catalog=cat,workers=4)
            self.assertEqual(outputs(a),outputs(b));self.assertEqual(b['saved'],6)

if __name__=='__main__':unittest.main(verbosity=2)
