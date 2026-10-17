"""재현 가능한 추출 벤치마크: 합성 문서, 입력 생성/목록 분석은 시간에서 제외."""
from __future__ import annotations
import argparse,hashlib,io,json,os,platform,random,statistics,sys,tempfile,time,zipfile
from pathlib import Path


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--source-root',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--iterations',type=int,default=3)
    parser.add_argument('--images',type=int,default=24)
    parser.add_argument('--profile',type=Path)
    args=parser.parse_args();sys.path.insert(0,str(args.source_root.resolve()))
    from PIL import Image,ImageDraw
    from document_reader import scan_document
    from image_engine import Settings,extract_images
    width,height=1600,1000
    cases=[('JPEG',Settings(format='JPEG')),('PNG_crop',Settings(format='PNG',apply_document_crop=True)),
           ('JPEG_target',Settings(format='JPEG',target_kb=180)),('ORIGINAL',Settings(format='ORIGINAL'))]
    report={'environment':{'platform':platform.platform(),'python':platform.python_version(),'cpu_count':os.cpu_count(),
            'engine_sha256':hashlib.sha256((args.source_root/'image_engine.py').read_bytes()).hexdigest()},'images':args.images,
            'image_size':[width,height],'iterations':args.iterations,'cases':{}}
    with tempfile.TemporaryDirectory(prefix='sunrise_benchmark_') as temp:
        root=Path(temp);source=root/'report.hwpx';rng=random.Random(20261015)
        payloads=[]
        for n in range(4):
            image=Image.frombytes('RGB',(width,height),rng.randbytes(width*height*3));draw=ImageDraw.Draw(image)
            draw.rectangle((0,0,width//2,height),fill='white')
            for y in range(40,height-30,35):
                draw.line((20,y,width//2-20,y),fill='#bcc7cf',width=2)
                draw.text((30,y+4),f'Environmental report / Sample {n} / Section {y}',fill='black')
            buf=io.BytesIO();image.save(buf,'PNG',compress_level=3);payloads.append(buf.getvalue())
        namespace='http://www.hancom.co.kr/hwpml/2011/'
        pics=[]
        with zipfile.ZipFile(source,'w',zipfile.ZIP_STORED) as z:
            for i in range(args.images):
                z.writestr(f'BinData/image{i:03d}.png',payloads[i%len(payloads)])
                pics.append(f'<hp:pic><hp:imgDim dimwidth="{width*75}" dimheight="{height*75}"/><hp:imgClip left="0" top="0" right="{width*75}" bottom="{height*75}"/><hc:img binaryItemIDRef="image{i:03d}"/></hp:pic>')
            z.writestr('Contents/section0.xml',f'<sec xmlns:hp="{namespace}paragraph" xmlns:hc="{namespace}core">'+''.join(pics)+'</sec>')
        catalogs={body:scan_document(source,body) for body in (False,True)}
        profiler=None
        if args.profile:
            import cProfile
            profiler=cProfile.Profile();profiler.enable()
        for name,settings in cases:
            elapsed=[];fingerprints=[]
            for iteration in range(args.iterations):
                start=time.perf_counter();result=extract_images(source,root/'out',settings,catalog=catalogs[settings.apply_document_crop]);elapsed.append(time.perf_counter()-start)
                assert result['saved']==args.images and result['failed']==0,result
                outputs=sorted(p for p in Path(result['folder']).iterdir() if p.suffix!='.csv')
                fingerprints=[{'name':p.name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size} for p in outputs]
                import shutil
                shutil.rmtree(result['folder'])
            report['cases'][name]={'seconds':elapsed,'median_seconds':statistics.median(elapsed),'outputs':fingerprints}
            print(name,round(statistics.median(elapsed),3),'seconds',flush=True)
        if profiler:
            profiler.disable();profiler.dump_stats(str(args.profile))
    if sys.platform=='linux':
        import resource
        report['process_peak_rss_mib']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024
    args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
if __name__=='__main__':main()
