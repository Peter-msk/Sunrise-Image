"""Platform runtime smoke check, callable from a frozen Windows application."""
from __future__ import annotations
import io,json,os,platform,sys,tempfile,time,traceback,zipfile
from pathlib import Path


def run(report_path=None):
    from PIL import Image,ImageDraw
    import PIL,PySide6,pymupdf,defusedxml
    from hwpx_image_extractor import QApplication,Window,Qt
    from PySide6.QtCore import QEvent
    from document_reader import scan_document,open_document
    from document_optimizer import optimize_document
    from image_engine import Settings,convert_image,FORMATS
    path=Path(report_path) if report_path else Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'SunriseImage'/'Diagnostics'/'runtime_check.json'
    path.parent.mkdir(parents=True,exist_ok=True)
    report={'program':'Sunrise Image','platform':platform.system(),'windows_verified':platform.system()=='Windows',
            'python':platform.python_version(),'architecture':platform.machine(),'frozen':bool(getattr(sys,'frozen',False)),
            'libraries':{'Pillow':PIL.__version__,'PySide6':PySide6.__version__,'PyMuPDF':pymupdf.VersionBind,'defusedxml':defusedxml.__version__},'checks':{},'status':'FAILED'}
    app=QApplication.instance() or QApplication(['SunriseImage','--smoke-test']);app.setStyle('Fusion')
    window=None
    def wait_for(predicate):
        deadline=time.monotonic()+20
        while time.monotonic()<deadline:
            app.processEvents()
            if predicate():return
            time.sleep(.01)
        raise RuntimeError('GUI runtime check timed out')
    try:
        screen=app.primaryScreen();report['screen']={'logical_dpi':screen.logicalDotsPerInch(),'device_pixel_ratio':screen.devicePixelRatio(),
                  'available_width':screen.availableGeometry().width(),'available_height':screen.availableGeometry().height()}
        im=Image.new('RGB',(30,20),'red');ImageDraw.Draw(im).rectangle((15,0,30,20),fill='blue')
        buf=io.BytesIO();im.save(buf,'PNG');data=buf.getvalue()
        for fmt in FORMATS:
            output=convert_image(data,Settings(format=fmt))
            with Image.open(io.BytesIO(output.data)) as decoded:decoded.load()
        report['checks']['bundled_image_codecs']='PASS'
        with tempfile.TemporaryDirectory(prefix='sunrise_image_runtime_') as temp:
            root=Path(temp);hwpx=root/'runtime.hwpx'
            xml='''<sec xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph" xmlns:hc="http://www.hancom.co.kr/hwpml/2011/core">
            <hp:pic><hp:imgDim dimwidth="2250" dimheight="1500"/><hp:imgClip left="0" top="0" right="1125" bottom="1500"/><hc:img binaryItemIDRef="image1"/></hp:pic>
            <hp:pic><hp:imgDim dimwidth="2250" dimheight="1500"/><hp:imgClip left="1125" top="0" right="2250" bottom="1500"/><hc:img binaryItemIDRef="image1"/></hp:pic></sec>'''
            with zipfile.ZipFile(hwpx,'w') as z:
                z.writestr('Contents/content.hpf','<package><manifest><item id="image1" href="BinData/image1.png" media-type="image/png"/></manifest></package>')
                z.writestr('Contents/section0.xml',xml);z.writestr('BinData/image1.png',data)
            window=Window();window.resize(1140,850);window.show();window.add_files([str(hwpx)])
            window.format.setCurrentIndex(1);window.crop.setChecked(True)
            wait_for(lambda:not window.pending_scans and window.tree.topLevelItemCount()==2)
            window.change_checks(False);row=window.tree.topLevelItem(1);row.setCheckState(0,Qt.CheckState.Checked)
            window.tree.setCurrentItem(row);window.collection_tabs.setCurrentIndex(1);window.preview()
            wait_for(lambda:'결과 15 × 20' in window.preview_info.text())
            report['checks']['native_gui_preview']='PASS'
            app.processEvents();window.grab().save(str(path.with_suffix('.png')))
            window.destination.setText(str(root/'output'));window.start_work();wait_for(lambda:not window.busy)
            outputs=list((root/'output').glob('*/*.png'))
            if len(outputs)!=1:raise RuntimeError('Selected-image output count is not one')
            with Image.open(outputs[0]) as saved:
                if saved.size!=(15,20) or saved.getpixel((5,5))[:3]!=(0,0,255):raise RuntimeError('Selected crop pixels do not match')
            report['checks']['selected_crop_extraction']='PASS'
            opt=optimize_document(hwpx,root/'opt_out',Settings(format='JPEG',quality=85))
            if opt['saved']!=1 or not Path(opt['output_file']).is_file():raise RuntimeError('Document optimization check failed')
            report['checks']['in_place_document_optimization']='PASS'
            pdf=root/'runtime.pdf';doc=pymupdf.open();page=doc.new_page();page.insert_image(pymupdf.Rect(0,0,30,20),stream=data);doc.save(pdf);doc.close()
            cat=scan_document(pdf)
            if len(cat.items)!=1:raise RuntimeError('PDF image catalog does not match')
            with open_document(pdf) as reader:
                with Image.open(io.BytesIO(reader.read(cat.items[0]))) as decoded:decoded.load()
            report['checks']['bundled_pdf_library']='PASS'
            wait_for(lambda:window.pool.activeThreadCount()==0)
        report['status']='PASS'
    except Exception:
        report['error']=traceback.format_exc()
    finally:
        if window:
            window.closing=True;window.timer.stop()
            window.scan_cancel.set();window.cancel.set();window.pool.waitForDone(25000);app.processEvents();window.close()
            app.sendPostedEvents(None,QEvent.Type.DeferredDelete)
        path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return 0 if report['status']=='PASS' else 1
