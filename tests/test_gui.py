import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import sys,tempfile,time,unittest,zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image
from PySide6.QtCore import QEvent
from hwpx_image_extractor import QApplication,Window,Qt
from fixtures import hwpx,image_bytes
app=QApplication.instance() or QApplication([])

def wait_until(predicate,seconds=10):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        app.processEvents()
        if predicate():return
        time.sleep(.01)
    raise AssertionError('GUI 작업 제한 시간 초과')

class GuiTests(unittest.TestCase):
    def tearDown(self):
        app.sendPostedEvents(None,QEvent.Type.DeferredDelete)

    def test_selection_crop_preview_and_extract(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'한글.hwpx';hwpx(p);w=Window();w.resize(1240,900);w.show();w.add_files([str(p)])
            wait_until(lambda:not w.pending_scans and w.tree.topLevelItemCount()==2)
            self.assertEqual(w.tree.topLevelItemCount(),2)
            w.format.setCurrentIndex(1);w.crop.setChecked(True)
            wait_until(lambda:not w.pending_scans and w.tree.topLevelItemCount()==3)
            w.change_checks(False);chosen=w.tree.topLevelItem(1);chosen.setCheckState(0,Qt.CheckState.Checked);w.tree.setCurrentItem(chosen)
            w.collection_tabs.setCurrentIndex(1);w.preview()
            wait_until(lambda:'결과 50 × 60' in w.preview_info.text())
            w.preview_mode.setCurrentIndex(1);w.preview();wait_until(lambda:'결과 100 × 60' in w.preview_info.text())
            w.preview_mode.setCurrentIndex(0);w.destination.setText(str(Path(t)/'out'));w.start_work()
            wait_until(lambda:not w.busy)
            self.assertIn('저장 1개',w.status.text());self.assertTrue(w.open_result.isEnabled())
            output=list((Path(t)/'out').glob('*/*.png'));self.assertEqual(len(output),1)
            with Image.open(output[0]) as im:self.assertEqual(im.size,(50,60));self.assertEqual(im.getpixel((10,10))[:3],(0,0,255))
            w.format.setCurrentIndex(w.format.findData('ORIGINAL'));wait_until(lambda:not w.pending_scans)
            self.assertFalse(w.crop.isChecked());self.assertFalse(w.crop.isEnabled())
            wait_until(lambda:w.pool.activeThreadCount()==0);w.close()

    def test_filter_selection_persists_across_documents_and_modes(self):
        with tempfile.TemporaryDirectory() as t:
            one=Path(t)/'one.hwpx';two=Path(t)/'two.docx';hwpx(one)
            with zipfile.ZipFile(two,'w') as z:z.writestr('word/media/picture.png',image_bytes())
            w=Window();w.show();w.add_files([str(one),str(two)]);wait_until(lambda:not w.pending_scans)
            w.file_list.setCurrentRow(0);w.search.setText('unused');w.change_checks(False)
            w.search.clear();self.assertEqual(len(w.checked_keys[w.mode_key(one.resolve())]),1)
            w.file_list.setCurrentRow(1);w.file_list.setCurrentRow(0)
            self.assertEqual(w.tree.topLevelItem(1).checkState(0),Qt.CheckState.Unchecked)
            # Toggle rapidly while asynchronous scans are pending; obsolete mode work must not block extraction.
            w.crop.setChecked(True);w.crop.setChecked(False);wait_until(lambda:not w.pending_scans and w.start.isEnabled())
            self.assertEqual(len(w.checked_keys[w.mode_key(one.resolve())]),1)
            wait_until(lambda:w.pool.activeThreadCount()==0);w.close()

    def test_failure_recovery_and_small_window(self):
        with tempfile.TemporaryDirectory() as t:
            good=Path(t)/'good.hwpx';bad=Path(t)/'bad.pdf';hwpx(good);bad.write_bytes(b'broken')
            w=Window();w.resize(840,620);w.show();w.add_files([str(good),str(bad)]);wait_until(lambda:not w.pending_scans)
            self.assertIn('문서를 읽을 수 없습니다',w.image.text())
            w.destination.setText(str(Path(t)/'out'));w.start_work();wait_until(lambda:not w.busy)
            self.assertIn('문서 실패 1개',w.status.text());self.assertIn('저장 2개',w.status.text())
            self.assertTrue(w.start.isVisible());self.assertGreater(w.start.width(),100)
            wait_until(lambda:w.pool.activeThreadCount()==0);w.close()

if __name__=='__main__':unittest.main(verbosity=2)
