import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import sys,tempfile,time,unittest,zipfile,threading
from unittest.mock import patch
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtTest import QTest
from PySide6.QtCore import QPoint,QEvent
from shiboken6 import isValid
from hwpx_image_extractor import QApplication,Window,Qt
from fixtures import hwpx,image_bytes
app=QApplication.instance() or QApplication([])

def wait(predicate):
    until=time.monotonic()+12
    while time.monotonic()<until:
        app.processEvents()
        if predicate():return
        time.sleep(.01)
    raise AssertionError('UI 작업 시간 초과')

class WorkflowTests(unittest.TestCase):
    def tearDown(self):
        app.sendPostedEvents(None,QEvent.Type.DeferredDelete)

    def test_double_click_return_preserves_list_state(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'test.hwpx';hwpx(p);w=Window();w.resize(1200,860);w.show();w.add_files([str(p)])
            wait(lambda:not w.pending_scans and w.tree.topLevelItemCount()==2)
            w.search.setText('image1');w.change_checks(False,visible_only=False)
            chosen=w.tree.topLevelItem(0);chosen.setCheckState(0,Qt.CheckState.Checked)
            w.tree.setCurrentItem(chosen);w.open_preview(chosen,0)
            self.assertEqual(w.collection_tabs.currentIndex(),1)
            QTest.mouseClick(w.back_to_list,Qt.MouseButton.LeftButton);app.processEvents()
            self.assertEqual(w.collection_tabs.currentIndex(),0)
            self.assertEqual(w.search.text(),'image1');self.assertIs(w.tree.currentItem(),chosen)
            self.assertEqual(len(w.checked_keys[w.mode_key(p.resolve())]),1)
            w.open_preview(chosen,0);w.activateWindow();app.processEvents();QTest.keyClick(w,Qt.Key.Key_Escape);app.processEvents()
            self.assertEqual(w.collection_tabs.currentIndex(),0)
            w.close();wait(lambda:not isValid(w) or not w.isVisible())

    def test_300_items_full_clear_and_200_row_cancel(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'many.docx'
            with zipfile.ZipFile(p,'w') as z:
                for i in range(300):z.writestr(f'word/media/image{i:03d}.png',image_bytes((10,6)))
            w=Window();w.resize(1200,860);w.show();w.add_files([str(p)])
            wait(lambda:not w.pending_scans and w.tree.topLevelItemCount()==300)
            key=w.mode_key(p.resolve());self.assertEqual(len(w.checked_keys[key]),300)
            w.search.setText('image000');QTest.mouseClick(w.check_none,Qt.MouseButton.LeftButton)
            self.assertEqual(len(w.checked_keys[key]),0)  # Hidden 299 rows must be cleared too.
            QTest.mouseClick(w.check_all,Qt.MouseButton.LeftButton);self.assertEqual(len(w.checked_keys[key]),300)
            w.search.clear();w.tree.clearSelection()
            first,last=w.tree.topLevelItem(0),w.tree.topLevelItem(199)
            w.tree.scrollToItem(first);app.processEvents();r=w.tree.visualItemRect(first)
            QTest.mouseClick(w.tree.viewport(),Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,QPoint(85,r.center().y()))
            w.tree.scrollToItem(last);app.processEvents();r=w.tree.visualItemRect(last)
            QTest.mouseClick(w.tree.viewport(),Qt.MouseButton.LeftButton,Qt.KeyboardModifier.ShiftModifier,QPoint(85,r.center().y()))
            self.assertEqual(len(w.tree.selectedItems()),200)
            w.change_scope_checks(False,'rows');self.assertEqual(len(w.checked_keys[key]),100)
            self.assertTrue(all(w.tree.topLevelItem(i).checkState(0)==Qt.CheckState.Unchecked for i in range(200)))
            w.destination.setText(str(Path(t)/'out'));w.format.setCurrentIndex(1);w.start_work();wait(lambda:not w.busy)
            self.assertEqual(len(list((Path(t)/'out').glob('*/*.png'))),100)
            w.close();wait(lambda:not isValid(w) or not w.isVisible())

    def test_all_documents_and_single_line_badge(self):
        with tempfile.TemporaryDirectory() as t:
            paths=[]
            for name in ['one','two']:
                p=Path(t)/(name+'.hwpx');hwpx(p);paths.append(str(p))
            w=Window();w.resize(840,620);w.show();w.add_files(paths);wait(lambda:not w.pending_scans)
            w.change_scope_checks(False,'documents')
            self.assertTrue(all(not w.checked_keys[w.mode_key(p)] for p in w.files))
            w.change_scope_checks(True,'documents');self.assertTrue(all(len(w.checked_keys[w.mode_key(p)])==2 for p in w.files))
            self.assertEqual(w.windowTitle(),'Sunrise Image');self.assertEqual(w.badge.text(),'Document / Image');self.assertFalse(w.badge.wordWrap())
            self.assertGreaterEqual(w.badge.width(),w.badge.fontMetrics().horizontalAdvance(w.badge.text())+20)
            self.assertTrue(w.start.isVisible());w.close();wait(lambda:not isValid(w) or not w.isVisible())

    def test_close_stops_pending_preview_timer(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'test.hwpx';hwpx(p);w=Window();w.show();w.add_files([str(p)])
            wait(lambda:not w.pending_scans and w.pool.activeThreadCount()==0)
            w.collection_tabs.setCurrentIndex(1);w.request_preview();self.assertTrue(w.timer.isActive())
            w.close()
            self.assertFalse(w.timer.isActive());self.assertEqual(w.pool.activeThreadCount(),0)
            wait(lambda:not isValid(w) or not w.isVisible())

    def test_close_waits_for_active_task_then_deletes_window(self):
        w=Window();w.show();started=threading.Event();release=threading.Event()
        def work(emit):
            started.set();release.wait(5)
        w.launch(work,'scan_done');wait(started.is_set)
        w.close()
        self.assertTrue(w.closing);self.assertTrue(w.isVisible());self.assertFalse(w.isEnabled())
        release.set();wait(lambda:not isValid(w))

    def test_hidden_preview_is_idle_and_double_click_launches_once(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'test.hwpx';hwpx(p);w=Window();w.show();w.add_files([str(p)])
            wait(lambda:not w.pending_scans and w.pool.activeThreadCount()==0)
            w.request_preview();w.percent.setValue(75)
            self.assertFalse(w.timer.isActive())
            with patch.object(w,'launch',wraps=w.launch) as launched:
                w.open_preview()
                self.assertEqual(launched.call_count,1);self.assertFalse(w.timer.isActive())
            wait(lambda:'결과' in w.preview_info.text() and w.pool.activeThreadCount()==0)
            w.return_to_list();self.assertTrue(w.preview_cancel.is_set());self.assertFalse(w.timer.isActive())
            w.close();wait(lambda:not isValid(w) or not w.isVisible())

    def test_quick_presets_invert_clear_and_preview_stepping(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'test.hwpx';hwpx(p);w=Window();w.resize(1200,860);w.show();w.add_files([str(p)])
            wait(lambda:not w.pending_scans and w.tree.topLevelItemCount()==2)
            self.assertEqual(w.doc_count_badge.text(),'문서 1개')
            self.assertFalse(w.dark_mode);w.toggle_theme();self.assertTrue(w.dark_mode);w.toggle_theme();self.assertFalse(w.dark_mode)
            self.assertEqual(w.selection_badge.text(),'체크 2 / 2개')
            self.assertTrue(w.size_card.isVisible());self.assertTrue(w.capacity_card.isVisible())
            w.tree.topLevelItem(0).setCheckState(0,Qt.CheckState.Unchecked)
            self.assertEqual(w.selection_badge.text(),'체크 1 / 2개')
            w.invert_checks()
            self.assertEqual(w.tree.topLevelItem(0).checkState(0),Qt.CheckState.Checked)
            self.assertEqual(w.tree.topLevelItem(1).checkState(0),Qt.CheckState.Unchecked)
            w.apply_preset('hwpx_crop')
            wait(lambda:not w.pending_scans and w.tree.topLevelItemCount()==3)
            self.assertEqual(w.format.currentData(),'PNG');self.assertTrue(w.crop.isChecked())
            w.apply_preset('print_300')
            self.assertTrue(w.change_dpi.isChecked());self.assertEqual(w.dpi.value(),300)
            wait(lambda:not w.pending_scans and w.tree.topLevelItemCount() > 0)
            w.open_preview()
            wait(lambda:'결과' in w.preview_info.text() and w.pool.activeThreadCount()==0)
            first_item=w.tree.currentItem()
            w.step_preview_item(1)
            self.assertIsNot(w.tree.currentItem(),first_item)
            wait(lambda:'결과' in w.preview_info.text() and w.pool.activeThreadCount()==0)
            w.step_preview_item(-1)
            self.assertIs(w.tree.currentItem(),first_item)
            wait(lambda:w.pool.activeThreadCount()==0)
            w.return_to_list()
            w.apply_preset('original')
            wait(lambda:not w.pending_scans and w.tree.topLevelItemCount()==2)
            self.assertEqual(w.format.currentData(),'ORIGINAL');self.assertFalse(w.crop.isChecked())
            w.apply_preset('report_jpg')
            self.assertEqual(w.format.currentData(),'JPEG');self.assertEqual(w.quality.value(),95)
            w.clear_files()
            self.assertEqual(len(w.files),0);self.assertEqual(w.file_list.count(),0)
            self.assertEqual(w.doc_count_badge.text(),'문서 0개')
            w.close();wait(lambda:not isValid(w) or not w.isVisible())

    def test_popup_preview_dialog_and_single_image_extract(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'popup.hwpx';hwpx(p);w=Window();w.resize(1200,860);w.show();w.add_files([str(p)])
            wait(lambda:not w.pending_scans and w.tree.topLevelItemCount()==2)
            # Uncheck all items to verify popup single-image extract works even when unchecked!
            w.change_checks(False,visible_only=False)
            self.assertEqual(len(w.checked_keys[w.mode_key(p.resolve())]),0)
            second=w.tree.topLevelItem(1);w.tree.setCurrentItem(second)
            w.format.setCurrentIndex(1)
            w.open_preview()
            self.assertTrue(w.preview_dialog.isVisible())
            wait(lambda:'결과 20 × 10' in w.preview_dialog.preview_info.text() and w.pool.activeThreadCount()==0)
            w.destination.setText(str(Path(t)/'single_out'))
            QTest.mouseClick(w.preview_dialog.extract_single_button,Qt.MouseButton.LeftButton)
            wait(lambda:not w.busy and w.pool.activeThreadCount()==0)
            outputs=list((Path(t)/'single_out').glob('*/*.png'))
            self.assertEqual(len(outputs),1)
            self.assertIn('단일 추출 완료',w.preview_dialog.single_status.full_text)
            self.assertTrue(w.preview_dialog.open_folder_button.isEnabled())
            QTest.mouseClick(w.preview_dialog.close_button,Qt.MouseButton.LeftButton);app.processEvents()
            self.assertFalse(w.preview_dialog.isVisible())
            self.assertEqual(w.collection_tabs.currentIndex(),0)
            w.close();wait(lambda:not isValid(w) or not w.isVisible())


    def test_in_place_document_optimize_button_and_legacy_hwp_rejection(self):
        with tempfile.TemporaryDirectory() as t:
            hwp_path=Path(t)/'legacy.hwp';hwp_path.write_bytes(b'HWP Document File')
            hwpx_path=Path(t)/'doc.hwpx';hwpx(hwpx_path)
            xlsx_path=Path(t)/'table.xlsx'
            with zipfile.ZipFile(xlsx_path,'w') as z:
                z.writestr('[Content_Types].xml','<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="png" ContentType="image/png"/></Types>')
                z.writestr('xl/drawings/_rels/drawing1.xml.rels','<Relationships><Relationship Id="rId1" Target="../media/image1.png"/></Relationships>')
                z.writestr('xl/media/image1.png',image_bytes((120,80)))
            w=Window();w.resize(1200,860);w.show()
            w.add_files([str(hwp_path)])
            self.assertEqual(len(w.files),0)
            self.assertIn('구형 한글(.hwp)은 지원 대상에서 제외',w.status.full_text)
            w.add_files([str(hwpx_path),str(xlsx_path)])
            wait(lambda:not w.pending_scans and len(w.files)==2)
            w.apply_preset('doc_diet')
            self.assertEqual(w.format.currentData(),'JPEG')
            self.assertTrue(w.use_target.isChecked())
            self.assertEqual(w.target.value(),300)
            self.assertTrue(w.shrink.isChecked())
            w.destination.setText(str(Path(t)/'opt_out'))
            QTest.mouseClick(w.optimize_btn,Qt.MouseButton.LeftButton)
            wait(lambda:not w.busy and w.pool.activeThreadCount()==0)
            self.assertIn('문서 경량화 완료',w.status.full_text)
            opt_hwpx=list((Path(t)/'opt_out').glob('*/*_경량화.hwpx'))
            opt_xlsx=list((Path(t)/'opt_out').glob('*/*_경량화.xlsx'))
            self.assertEqual(len(opt_hwpx),1)
            self.assertEqual(len(opt_xlsx),1)
            w.close();wait(lambda:not isValid(w) or not w.isVisible())

    def test_doc_table_preview_button_popup_list_and_dropdown_switch(self):
        with tempfile.TemporaryDirectory() as t:
            doc_a=Path(t)/'보고서A.hwpx';hwpx(doc_a)
            doc_b=Path(t)/'보고서B.xlsx'
            with zipfile.ZipFile(doc_b,'w') as z:
                z.writestr('[Content_Types].xml','<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="png" ContentType="image/png"/></Types>')
                z.writestr('xl/drawings/_rels/drawing1.xml.rels','<Relationships><Relationship Id="rId1" Target="../media/image1.png"/></Relationships>')
                z.writestr('xl/media/image1.png',image_bytes((100,60)))
            w=Window();w.show()
            self.assertEqual((w.rect().width(),w.rect().height()),(1200,760));w.show_log(True);self.assertEqual((w.rect().width(),w.rect().height()),(1200,860));w.show_log(False);self.assertEqual((w.rect().width(),w.rect().height()),(1200,760))
            w.add_files([str(doc_a),str(doc_b)])
            wait(lambda:not w.pending_scans and w.doc_table.topLevelItemCount()==2)
            # Verify 3-column doc_table rows and preview buttons
            item_a=w.doc_table.topLevelItem(0)
            item_b=w.doc_table.topLevelItem(1)
            self.assertEqual(item_a.text(0),'보고서A.hwpx')
            self.assertIn('2개',item_a.text(1))
            self.assertEqual(item_b.text(0),'보고서B.xlsx')
            self.assertIn('1개',item_b.text(1))
            btn_a=w.doc_table.itemWidget(item_a,2)
            btn_b=w.doc_table.itemWidget(item_b,2)
            self.assertIsNotNone(btn_a)
            self.assertEqual(btn_a.text(),'미리보기')
            self.assertIsNotNone(btn_b)
            # Click preview button on row 0 (보고서A.hwpx) -> opens popup dialog with LIST + Preview
            QTest.mouseClick(btn_a,Qt.MouseButton.LeftButton)
            wait(lambda:w.preview_dialog.isVisible() and w.preview_pixmap is not None)
            self.assertEqual(w.current_path(),doc_a.resolve())
            self.assertEqual(w.tree.topLevelItemCount(),2)
            self.assertEqual(w.preview_dialog.doc_combo.count(),2)
            self.assertEqual(w.preview_dialog.doc_combo.currentIndex(),0)
            self.assertIn('보고서A.hwpx',w.preview_dialog.doc_combo.itemText(0))
            self.assertIn('보고서B.xlsx',w.preview_dialog.doc_combo.itemText(1))
            # Switch active file via the top dropdown inside the LIST popup dialog
            w.preview_dialog.doc_combo.setCurrentIndex(1)
            wait(lambda:w.current_path()==doc_b.resolve() and w.tree.topLevelItemCount()==1)
            self.assertEqual(w.file_list.currentRow(),1)
            w.close();wait(lambda:not isValid(w) or not w.isVisible())

    def test_folder_add_naming_rules_pdf_optimize_and_popup_controls(self):
        import pymupdf
        with tempfile.TemporaryDirectory() as t:
            in_dir = Path(t) / 'batch_folder'
            sub_dir = in_dir / 'sub'
            sub_dir.mkdir(parents=True)
            hwpx_p = in_dir / '생태보고서.hwpx'
            hwpx(hwpx_p)
            # Legacy .hwp and existing _경량화 file should be auto-excluded when adding folder
            (in_dir / '구형문서.hwp').write_bytes(b'HWP Document File')
            hwpx(in_dir / '이전결과_경량화.hwpx')
            # Create a PDF document with an embedded PNG image
            pdf_p = sub_dir / '현장도면.pdf'
            doc = pymupdf.open()
            pg = doc.new_page()
            pg.insert_image(pymupdf.Rect(0, 0, 200, 120), stream=image_bytes((320, 240), 'PNG'))
            doc.save(pdf_p)
            doc.close()

            w = Window()
            w.show()
            # 1. Verify streamlined 5 formats in UI combo (BMP/GIF/ICO removed)
            fmt_keys = [w.format.itemData(i) for i in range(w.format.count())]
            self.assertEqual(fmt_keys, ['JPEG', 'PNG', 'WEBP', 'TIFF', 'ORIGINAL'])

            # 2. Add entire folder (recursively adds 생태보고서.hwpx and 현장도면.pdf, skips .hwp and _경량화)
            w.add_files([str(in_dir)])
            wait(lambda: not w.pending_scans and len(w.files) == 2)
            self.assertEqual({f.name for f in w.files}, {'생태보고서.hwpx', '현장도면.pdf'})

            # 3. Verify popup quick settings sync, 1-click diet filter, compare toggle, and zoom
            w.open_document_preview(0)
            wait(lambda: w.preview_dialog.isVisible() and w.preview_pixmap is not None)
            w.preview_dialog.popup_crop_check.setChecked(True)
            self.assertTrue(w.crop.isChecked())
            w.preview_dialog.popup_target_check.setChecked(True)
            self.assertTrue(w.use_target.isChecked())
            w.preview_dialog.toggle_compare_mode()
            self.assertEqual(w.preview_mode.currentIndex(), 1)
            w.preview_dialog.toggle_compare_mode()
            self.assertEqual(w.preview_mode.currentIndex(), 0)
            w.preview_dialog.step_zoom(1)
            self.assertGreater(w.preview_dialog.zoom_factor, 1.0)
            w.preview_dialog.toggle_zoom_fit()
            self.assertEqual(w.preview_dialog.zoom_factor, 0.0)

            # 4. Test filename naming rule: doc_ordinal (문서명_순번)
            out_extract = Path(t) / 'extract_out'
            w.destination.setText(str(out_extract))
            w.naming_mode.setCurrentIndex(1)  # doc_ordinal
            self.assertEqual(w.settings().naming, 'doc_ordinal')
            wait(lambda: not w.pending_scans)
            w.start_work()
            wait(lambda: not w.busy and w.pool.activeThreadCount() == 0)
            extracted_files = list(out_extract.glob('*/*.jpg'))
            self.assertTrue(any(f.name.startswith('생태보고서_0001_') for f in extracted_files))

            # 5. Test in-place optimization including PDF + direct root _경량화 output + doc_table reduction %
            out_opt = Path(t) / 'opt_root'
            w.destination.setText(str(out_opt))
            w.apply_preset('doc_diet')
            w.start_optimize_work()
            wait(lambda: not w.busy and w.pool.activeThreadCount() == 0)
            self.assertTrue((out_opt / '생태보고서_경량화.hwpx').is_file())
            self.assertTrue((out_opt / '현장도면_경량화.pdf').is_file())
            self.assertIn('%', w.doc_table.topLevelItem(0).text(1))
            w.close();wait(lambda:not isValid(w) or not w.isVisible())



    def test_preview_selected_lossless_only_convert_and_no_button_overlap(self):
        with tempfile.TemporaryDirectory() as t:
            mixed = Path(t) / 'mixed_report.docx'
            with zipfile.ZipFile(mixed, 'w') as z:
                z.writestr('[Content_Types].xml', '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="png" ContentType="image/png"/><Default Extension="jpeg" ContentType="image/jpeg"/></Types>')
                z.writestr('word/_rels/document.xml.rels', '<Relationships><Relationship Id="rId1" Target="media/a.png"/><Relationship Id="rId2" Target="media/b.jpeg"/></Relationships>')
                z.writestr('word/media/a.png', image_bytes((120, 80), 'PNG'))
                z.writestr('word/media/b.jpeg', image_bytes((100, 60), 'JPEG'))
            w = Window()
            w.show()
            app.processEvents()
            # Verify no overlap between optimize_btn and start on initial launch
            self.assertLessEqual(w.optimize_btn.geometry().right(), w.start.geometry().left())
            w.add_files([str(mixed)])
            wait(lambda: not w.pending_scans and w.tree.topLevelItemCount() == 2)
            w.open_document_preview(0)
            wait(lambda: w.preview_dialog.isVisible() and w.preview_pixmap is not None)
            # Verify no overlap in VIEW toolbar and mode_combo is wide enough for full text
            self.assertLessEqual(w.preview_dialog.toggle_compare_btn.geometry().right(), w.preview_dialog.zoom_out_btn.geometry().left())
            self.assertGreaterEqual(w.preview_dialog.mode_combo.width(), 100)
            # Click PNG·BMP filter -> selects only a.png (1 item)
            QTest.mouseClick(w.preview_dialog.filter_lossless_btn, Qt.MouseButton.LeftButton)
            app.processEvents()
            self.assertEqual(len(w.checked_keys[w.mode_key(mixed.resolve())]), 1)
            out_dir = Path(t) / 'sel_opt_out'
            w.destination.setText(str(out_dir))
            QTest.mouseClick(w.preview_dialog.convert_selected_btn, Qt.MouseButton.LeftButton)
            wait(lambda: not w.busy and w.pool.activeThreadCount() == 0)
            self.assertIn('선택 이미지 1개 문서 내 변환 완료', w.preview_dialog.single_status.full_text)
            self.assertTrue((out_dir / 'mixed_report_경량화.docx').is_file())
            w.close(); wait(lambda: not isValid(w) or not w.isVisible())

if __name__=='__main__':unittest.main(verbosity=2)
