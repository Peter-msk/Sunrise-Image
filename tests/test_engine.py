import csv
import hashlib
import io
import tempfile
import threading
import unittest
import zipfile
from dataclasses import replace
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image
from image_engine import *


def raster(fmt='PNG', size=(640,320), noise=False, **options):
    if noise:
        import random
        data=random.Random(12345).randbytes(size[0]*size[1]*3)
        im=Image.frombytes('RGB',size,data)
    else:im=Image.new('RGBA' if fmt=='PNG' else 'RGB',size,(10,80,150,0) if fmt=='PNG' else (10,80,150))
    out=io.BytesIO();im.save(out,fmt,**options);return out.getvalue()


class EngineTests(unittest.TestCase):
    def test_formats_valid_output(self):
        for fmt in FORMATS:
            with self.subTest(fmt=fmt):
                result=convert_image(raster(),Settings(format=fmt,dpi=300),'i.png')
                with Image.open(io.BytesIO(result.data)) as im:
                    im.load();self.assertEqual(im.format,fmt)
                    if fmt=='ICO':self.assertEqual(im.size,(256,256))
                    else:self.assertEqual(im.size,(640,320))
                    if fmt in DPI_FORMATS:self.assertAlmostEqual(read_dpi(im)[0],300,delta=0.1)

    def test_original_identical_and_misnamed_extension(self):
        for fmt in ['JPEG','PNG','WEBP','TIFF','GIF','BMP']:
            data=raster(fmt)
            result=convert_image(data,Settings(format='ORIGINAL',resize='fit',dpi=600),'misnamed.png')
            self.assertEqual(result.data,data);self.assertTrue(result.passthrough)
            self.assertEqual(result.format,fmt)
        svg=b'<svg xmlns="http://www.w3.org/2000/svg"/>'
        self.assertEqual(convert_image(svg,Settings(format='ORIGINAL'),'image.svg').data,svg)

    def test_resize_modes_aspect_and_upscale(self):
        data=raster()
        for opts,expected in [({'resize':'percent','percent':50},(320,160)),
                              ({'resize':'long_edge','width':200},(200,100)),
                              ({'resize':'fit','width':200,'height':50},(100,50)),
                              ({'resize':'percent','percent':200},(640,320)),
                              ({'resize':'percent','percent':200,'allow_upscale':True},(1280,640))]:
            self.assertEqual(convert_image(data,Settings(format='PNG',**opts)).size,expected)

    def test_dpi_preservation_and_override(self):
        data=raster(dpi=(144,144))
        keep=convert_image(data,Settings(format='JPEG'))
        change=convert_image(data,Settings(format='PNG',dpi=600))
        self.assertEqual(change.size,(640,320))
        self.assertAlmostEqual(keep.dpi[0],144,delta=.1)
        with Image.open(io.BytesIO(change.data)) as im:self.assertAlmostEqual(im.info['dpi'][0],600,delta=.1)

    def test_transparency_and_background(self):
        data=raster(size=(32,32))
        for fmt,alpha,expected in [('PNG','keep',0),('JPEG','keep',(255,255,255)),('PNG','black',(0,0,0))]:
            out=convert_image(data,Settings(format=fmt,alpha=alpha))
            with Image.open(io.BytesIO(out.data)) as im:
                pixel=im.getpixel((1,1))
                if alpha=='keep' and fmt=='PNG':self.assertEqual(pixel[3],expected)
                else:self.assertEqual(pixel[:3],expected)

    def test_target_quality_without_resize(self):
        data=raster('PNG',(512,256),noise=True)
        out=convert_image(data,Settings(format='JPEG',target_kb=60,quality=95))
        self.assertTrue(out.target_met);self.assertLessEqual(len(out.data),60*1024)
        self.assertEqual(out.size,(512,256));self.assertLess(out.quality,95)

    def test_lossless_target_failure_then_resize(self):
        data=raster('PNG',(512,256),noise=True)
        s=Settings(format='PNG',target_kb=30)
        failed=convert_image(data,s)
        self.assertFalse(failed.target_met);self.assertEqual(failed.size,(512,256))
        success=convert_image(data,replace(s,shrink_for_target=True))
        self.assertTrue(success.target_met);self.assertLessEqual(len(success.data),30*1024)
        self.assertLess(success.size[0],512)

    def test_tiny_target_all_formats(self):
        data=raster('PNG',(256,128),noise=True)
        for fmt in FORMATS:
            result=convert_image(data,Settings(format=fmt,target_kb=3,shrink_for_target=True))
            self.assertTrue(result.target_met,fmt)
            with Image.open(io.BytesIO(result.data)) as im:im.load()

    def test_rotation_grayscale(self):
        out=convert_image(raster(),Settings(format='PNG',rotate=90,grayscale=True))
        self.assertEqual(out.size,(320,640))
        with Image.open(io.BytesIO(out.data)) as im:
            rgb=im.convert('RGB').getpixel((0,0));self.assertEqual(rgb[0],rgb[1]);self.assertEqual(rgb[1],rgb[2])

    def test_first_frame(self):
        a=Image.new('RGB',(20,10),'red');b=Image.new('RGB',(20,10),'blue');buf=io.BytesIO()
        a.save(buf,'GIF',save_all=True,append_images=[b])
        out=convert_image(buf.getvalue(),Settings(format='PNG'))
        self.assertTrue(any('첫 프레임' in n for n in out.notes))
        with Image.open(io.BytesIO(out.data)) as im:self.assertEqual(im.convert('RGB').getpixel((0,0)),(255,0,0))

    def test_extract_failure_continuation_repeat_and_source_hash(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp);src=folder/'테스트.hwpx'
            with zipfile.ZipFile(src,'w') as arc:
                arc.writestr('BinData/image10.png',raster());arc.writestr('BinData/image2.png',b'broken')
                arc.writestr('BinData/image1.jpg',raster('JPEG'));arc.writestr('Contents/section0.xml','<section/>')
            before=hashlib.sha256(src.read_bytes()).hexdigest()
            first=extract_images(src,folder,Settings(format='PNG'));second=extract_images(src,folder,Settings(format='PNG'))
            self.assertEqual((first['saved'],first['failed']),(2,1));self.assertNotEqual(first['folder'],second['folder'])
            self.assertEqual(before,hashlib.sha256(src.read_bytes()).hexdigest())
            with (Path(first['folder'])/'추출결과.csv').open(encoding='utf-8-sig') as h:rows=list(csv.DictReader(h))
            self.assertTrue(rows[0]['내부 파일'].endswith('image1.jpg'));self.assertEqual(rows[1]['상태'],'실패');self.assertEqual(rows[2]['상태'],'성공')

    def test_cancel_keeps_saved_and_csv(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp);src=folder/'cancel.hwpx';cancel=threading.Event()
            with zipfile.ZipFile(src,'w') as arc:
                for i in range(3):arc.writestr(f'BinData/i{i}.png',raster())
            def notify(e):
                if e['type']=='item':cancel.set()
            result=extract_images(src,folder,notify=notify,cancel=cancel)
            self.assertTrue(result['cancelled']);self.assertEqual(result['saved'],1)
            self.assertTrue((Path(result['folder'])/'추출결과.csv').exists())

    def test_empty_archive_and_invalid_setting(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'empty.hwpx'
            with zipfile.ZipFile(path,'w') as arc:arc.writestr('Contents/section0.xml','x')
            self.assertEqual(extract_images(path,Path(temp))['total'],0)
        with self.assertRaises(ValueError):Settings(dpi=0).validate()
        with self.assertRaises(ValueError):resized_size((640,320),Settings(resize='fit',width=30000,height=30000,allow_upscale=True))

    def test_exif_orientation(self):
        im=Image.new('RGB',(100,50),'red');exif=Image.Exif();exif[274]=6;buf=io.BytesIO();im.save(buf,'JPEG',exif=exif)
        out=convert_image(buf.getvalue(),Settings(format='PNG'))
        self.assertEqual(out.size,(50,100))



    def test_cmyk_and_16bit_grayscale_normalization_across_formats(self):
        # CMYK JPEG
        cmyk = Image.new('CMYK', (40, 30), (10, 120, 200, 5))
        b_cmyk = io.BytesIO(); cmyk.save(b_cmyk, 'JPEG')
        for fmt in ['JPEG', 'PNG', 'WEBP', 'TIFF', 'BMP', 'ICO']:
            conv = convert_image(b_cmyk.getvalue(), Settings(format=fmt))
            with Image.open(io.BytesIO(conv.data)) as out_im:
                out_im.load()
        # 16-bit grayscale PNG (mode I;16 / I)
        im16 = Image.new('I', (40, 30), 32768)
        b_16 = io.BytesIO(); im16.save(b_16, 'PNG')
        for fmt in ['JPEG', 'PNG', 'WEBP', 'TIFF']:
            conv16 = convert_image(b_16.getvalue(), Settings(format=fmt))
            with Image.open(io.BytesIO(conv16.data)) as out16:
                rgb = out16.convert('RGB').getpixel((20, 15))
                self.assertTrue(100 <= rgb[0] <= 156, f'Expected mid-gray around 128, got {rgb}')


if __name__=='__main__':unittest.main(verbosity=2)
