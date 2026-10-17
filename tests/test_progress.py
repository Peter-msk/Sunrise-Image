import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import sys,tempfile,threading,time,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from progress_state import BatchProgress
from hwpx_image_extractor import QApplication,Window,Qt
import hwpx_image_extractor as gui
from PySide6.QtCore import QEvent
from shiboken6 import isValid
from fixtures import image_bytes
app=QApplication.instance() or QApplication([])

def wait(predicate):
    until=time.monotonic()+12
    while time.monotonic()<until:
        app.processEvents()
        if predicate():return
        time.sleep(.005)
    raise AssertionError('진행률 UI 시간 초과')

def documents(root,counts=(2,8)):
    paths=[]
    for i,count in enumerate(counts):
        p=root/f'보고서_{i+1}_국가하천_수리수문_본문이미지_선택추출.docx'
        with zipfile.ZipFile(p,'w') as z:
            for n in range(count):z.writestr(f'word/media/image{n:03d}.png',image_bytes())
        paths.append(p)
    return paths

class ProgressModelTests(unittest.TestCase):
    def test_unequal_documents_are_weighted_by_selected_images(self):
        b=BatchProgress([('a',2),('b',8)]);b.start(0)
        for i in range(1,3):b.item_done(0,i,'성공')
        b.end(0,{'total':2,'processed':2,'saved':2,'failed':0,'cancelled':False})
        self.assertEqual(b.percent,20);self.assertEqual(b.remaining,8);self.assertEqual(b.documents_done,1)
        b.start(1);b.item_done(1,1,'실패')
        self.assertEqual(b.percent,30);self.assertEqual(b.saved,2);self.assertEqual(b.failed,1)
        self.assertEqual(b.remaining,7)

    def test_cancellation_keeps_remaining_and_actual_completion(self):
        b=BatchProgress([('a',10),('b',20)]);b.start(0)
        b.item_start(0,4,'image4.png');b.item_done(0,3,'성공');b.finish(True)
        self.assertEqual(b.percent,10);self.assertEqual(b.remaining,27)
        self.assertEqual(b.current.state,'중지됨');self.assertEqual(b.documents[1].state,'미처리')
        self.assertEqual(b.documents_done,0)
        done=BatchProgress([('finished',1)]);done.start(0)
        done.end(0,{'total':1,'processed':1,'saved':1,'failed':0,'cancelled':False});done.finish(True)
        self.assertEqual(done.percent,100)  # A late stop cannot undo already completed work.

    def test_failed_document_is_separate_from_failed_images(self):
        b=BatchProgress([('a',8)]);b.start(0);b.item_done(0,1,'성공');b.end(0,error=True)
        self.assertEqual((b.saved,b.failed,b.blocked,b.remaining),(1,0,7,0))
        self.assertEqual(b.percent,100);self.assertEqual(b.documents_failed,1)

    def test_unknown_document_never_invents_image_count(self):
        b=BatchProgress([('a',2),('bad',None)]);b.start(0)
        b.end(0,{'total':2,'processed':2,'saved':2,'failed':0,'cancelled':False})
        self.assertLess(b.percent,100);self.assertEqual(b.unknown_documents,1)
        b.start(1);b.end(1,error=True)
        self.assertEqual(b.percent,100);self.assertEqual(b.total,2);self.assertEqual(b.blocked,0)
        self.assertEqual(b.documents_done,2)

class ProgressGuiTests(unittest.TestCase):
    def tearDown(self):app.sendPostedEvents(None,QEvent.Type.DeferredDelete)

    def _window(self,root,counts=(2,8)):
        paths=documents(root,counts);w=Window();w.resize(1180,920);w.show();w.add_files([str(p) for p in paths])
        wait(lambda:not w.pending_scans);w.destination.setText(str(root/'out'));w.format.setCurrentIndex(1)
        return w,paths

    def _run_paused(self,w,paths,release):
        original=gui.extract_images
        def wrapped(path,dest,settings,notify,cancel,keys,cat):
            def receive(event):
                notify(event)
                if path==paths[1] and event['type']=='item_start' and event['index']==3:release.wait(10)
            return original(path,dest,settings,receive,cancel,keys,cat)
        return patch.object(gui,'extract_images',wrapped)

    def test_live_document_and_image_counts_then_completed(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);w,paths=self._window(root);release=threading.Event()
            try:
                with self._run_paused(w,paths,release):
                    w.start_work();wait(lambda:w.batch_progress.current_index==1 and w.batch_progress.current.ordinal==3)
                    self.assertEqual(w.progress.value(),400);self.assertEqual(w.document_progress.value(),250)
                    self.assertIn('남음 6개',w.progress.format());self.assertIn(paths[1].name,w.current_document.full_text)
                    self.assertIn('image002.png',w.current_image.full_text);self.assertTrue(w.file_list.isEnabled())
                    self.assertIn('처리 중',w.file_list.item(1).text());self.assertIn('완료',w.file_list.item(0).text())
                    w.file_list.setCurrentRow(0)
                    self.assertIn(paths[1].name,w.current_document.full_text)
                    release.set();wait(lambda:not w.busy)
                self.assertEqual(w.progress.value(),1000);self.assertEqual(w.batch_progress.saved,10)
                self.assertEqual(w.batch_progress.documents_done,2);self.assertIn('남음 0개',w.progress.format())
                self.assertEqual(len(list((root/'out').glob('*/*.png'))),10)
            finally:
                release.set();w.close();wait(lambda:not isValid(w) or not w.isVisible())

    def test_cancelled_multi_document_batch_does_not_show_100(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);w,paths=self._window(root);release=threading.Event()
            try:
                with self._run_paused(w,paths,release):
                    w.start_work();wait(lambda:w.batch_progress.current_index==1 and w.batch_progress.current.ordinal==3)
                    w.cancel_work();release.set();wait(lambda:not w.busy)
                self.assertEqual(w.progress.value(),400);self.assertEqual(w.batch_progress.saved,4)
                self.assertIn('남음 6개',w.progress.format());self.assertIn('중지됨',w.file_list.item(1).text())
                self.assertEqual(w.batch_progress.documents_done,1)
                self.assertEqual(len(list((root/'out').glob('*/*.png'))),4)
            finally:
                release.set();w.close();wait(lambda:not isValid(w) or not w.isVisible())

    def test_document_failure_counts_blocked_images_explicitly(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);w,paths=self._window(root)
            paths[1].write_bytes(paths[1].read_bytes()+b'changed')
            w.start_work();wait(lambda:not w.busy)
            self.assertEqual(w.progress.value(),1000);self.assertEqual(w.batch_progress.saved,2)
            self.assertEqual(w.batch_progress.blocked,8);self.assertEqual(w.batch_progress.failed,0)
            self.assertIn('처리 불가 8개',w.progress.format());self.assertIn('실패',w.file_list.item(1).text())
            self.assertEqual(w.batch_progress.documents_failed,1)
            w.close();wait(lambda:not isValid(w) or not w.isVisible())

    def test_document_list_resizes_and_long_paths_are_available(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);w,paths=self._window(root,(1,1,1,1,1,1))
            self.assertTrue(w.doc_table.isVisible())
            self.assertGreater(w.doc_table.height(), 100)
            self.assertIn(str(paths[0]),w.file_list.item(0).toolTip());self.assertIn('선택 1',w.file_list.item(0).text())
            self.assertEqual(w.file_list.horizontalScrollBarPolicy(),Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            w.resize(840,620);app.processEvents()
            self.assertTrue(w.progress.isVisible());self.assertTrue(w.document_progress.isVisible())
            self.assertTrue(w.start.isVisible());self.assertLessEqual(w.progress.geometry().right(),w.rect().width())
            w.close();wait(lambda:not isValid(w) or not w.isVisible())

if __name__=='__main__':unittest.main(verbosity=2)
