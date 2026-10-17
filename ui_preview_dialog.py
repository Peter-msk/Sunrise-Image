"""Sunrise Image — Integrated LIST & Preview Popup Window (Modular Layout-Group Controller)."""
from __future__ import annotations
from PySide6.QtCore import QSize, QTimer, Qt
from PySide6.QtGui import QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import QDialog, QSplitter, QVBoxLayout
from ui_layout_groups import (
    build_preview_list_group,
    build_preview_top_bar_group,
    build_preview_view_group,
)
from ui_theme import application_icon
from ui_widgets import ElidedLabel, format_size, hbox, make_btn, relayout_widget_tree


class PreviewDialog(QDialog):
    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window
        self.setObjectName("previewDialog")
        self.setWindowTitle("Sunrise Image — 문서별 이미지 목록(LIST) 및 미리보기")
        self.setWindowIcon(application_icon())
        self.setMinimumSize(1020, 640)
        self.preview_pixmap = None
        self.zoom_factor = 0.0
        self._syncing_doc = False
        self._syncing_quick = False
        self.build()
        self.resize(1200, 740)

    def build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 10, 12, 10)
        outer.setSpacing(8)

        # Group 8A: Top Document Selector & Quick Settings Bar (#previewTopCard)
        outer.addWidget(build_preview_top_bar_group(self))

        # Center Horizontal Splitter: Group 8B (LIST) | Group 8C (VIEW)
        split = QSplitter(Qt.Orientation.Horizontal)
        split.setHandleWidth(8)
        split.setChildrenCollapsible(False)
        outer.addWidget(split, 1)

        split.addWidget(build_preview_list_group(self))
        split.addWidget(build_preview_view_group(self))
        split.setSizes([580, 580])

        self.single_status = ElidedLabel("단축키: ← / → 이전·다음 이미지 · 이미지 클릭(또는 Space) 원본⇄결과 비교 · 휠 확대/축소 · Esc 닫기")
        self.single_status.setObjectName("muted")
        self.close_button = make_btn("창 닫기 (Esc)", self.close_to_list)
        outer.addLayout(hbox((self.single_status, 1), self.close_button, spacing=8))

        for key_str, cb in [
            ("Esc", self.close_to_list),
            ("Left", lambda: self.main_window.step_preview_item(-1)),
            ("Right", lambda: self.main_window.step_preview_item(1)),
            ("Space", self.toggle_compare_mode),
        ]:
            sc = QShortcut(QKeySequence(key_str), self)
            sc.activated.connect(cb)
            setattr(self, f"_{key_str.lower()}_sc", sc)

    def showEvent(self, event):
        super().showEvent(event)
        relayout_widget_tree(self)
        QTimer.singleShot(0, lambda: relayout_widget_tree(self))

    def _apply_quick_filter(self, scope: str, label_name: str):
        mw = self.main_window
        mw.change_scope_checks(True, scope)
        path = mw.current_path()
        if path is not None:
            cnt = len(mw.checked_keys.get(mw.mode_key(path), set()))
            if cnt > 0:
                self.single_status.setText(
                    f"✓ {label_name} 이미지 {cnt:,}개가 선택되었습니다. [선택 이미지만 변환] 또는 [선택 변환 추출]로 선택된 항목만 변환하세요."
                )
            else:
                self.single_status.setText(f"현재 문서에 해당하는 {label_name} 이미지가 없습니다.")

    def _on_doc_combo_changed(self, index):
        if not self._syncing_doc and 0 <= index < len(self.main_window.files):
            self.main_window.select_document_row(index)

    def _on_popup_format_changed(self, index):
        if not self._syncing_quick and 0 <= index < self.main_window.format.count():
            self.main_window.format.setCurrentIndex(index)

    def _on_popup_crop_toggled(self, checked):
        if not self._syncing_quick:
            self.main_window.crop.setChecked(checked)

    def _on_popup_target_toggled(self, checked):
        if not self._syncing_quick:
            self.main_window.use_target.setChecked(checked)

    def toggle_compare_mode(self):
        if not self.main_window.busy:
            self.mode_combo.setCurrentIndex(1 if self.mode_combo.currentIndex() == 0 else 0)

    def step_zoom(self, direction: int):
        base = self.zoom_factor if self.zoom_factor > 0 else 1.0
        self.zoom_factor = max(0.25, min(4.0, round(base + (0.25 * direction), 2)))
        self.zoom_reset_btn.setText(f"{int(round(self.zoom_factor * 100))}%")
        self.refresh_pixmap()

    def toggle_zoom_fit(self):
        self.zoom_factor = 1.0 if self.zoom_factor == 0.0 else 0.0
        self.zoom_reset_btn.setText("100%" if self.zoom_factor == 1.0 else "창 맞춤")
        self.refresh_pixmap()

    def sync_from_main(self):
        mw = self.main_window
        self._syncing_doc = True
        try:
            self.doc_combo.blockSignals(True)
            self.doc_combo.clear()
            for idx, path in enumerate(mw.files):
                key = mw.mode_key(path)
                cat = mw.catalogs.get(key)
                fsize = f" · {format_size(path.stat().st_size)}" if path.is_file() else ""
                if cat:
                    chk = len(mw.checked_keys.get(key, set()))
                    txt = f"{idx + 1:02d}. {path.name}  (선택 {chk:,} / {len(cat.items):,}개{fsize})"
                else:
                    txt = f"{idx + 1:02d}. {path.name}  ({'읽기 실패' if key in mw.catalog_errors else '분석 중…'})"
                self.doc_combo.addItem(txt, str(path))
            cur_row = mw.file_list.currentRow()
            if 0 <= cur_row < self.doc_combo.count():
                self.doc_combo.setCurrentIndex(cur_row)
            self.doc_combo.blockSignals(False)
        finally:
            self._syncing_doc = False

        self._syncing_quick = True
        try:
            self.popup_format_combo.blockSignals(True)
            if self.popup_format_combo.count() != mw.format.count():
                self.popup_format_combo.clear()
                for i in range(mw.format.count()):
                    self.popup_format_combo.addItem(mw.format.itemText(i))
            self.popup_format_combo.setCurrentIndex(mw.format.currentIndex())
            self.popup_format_combo.blockSignals(False)

            for w_pop, w_main in [(self.popup_crop_check, mw.crop), (self.popup_target_check, mw.use_target)]:
                w_pop.blockSignals(True)
                w_pop.setChecked(w_main.isChecked())
                w_pop.setEnabled(w_main.isEnabled())
                w_pop.blockSignals(False)
            self.popup_summary_label.setText(mw.summary.text())
        finally:
            self._syncing_quick = False

        row, path, busy = mw.tree.currentItem(), mw.current_path(), mw.busy
        has_row = row is not None and path is not None
        has_items = mw.tree.topLevelItemCount() > 0
        can_opt_cur = (
            not busy
            and path is not None
            and path.suffix.lower() in {".hwpx", ".pdf", ".xlsx", ".docx", ".pptx"}
            and has_items
        )
        self.item_title.setText(f"{row.text(0)} · {row.text(4)}" if has_row else "선택된 이미지 미리보기")
        self.doc_combo.setEnabled(not busy and bool(mw.files))
        self.popup_format_combo.setEnabled(not busy)
        self.extract_single_button.setEnabled(not busy and has_row)
        self.extract_checked_button.setEnabled(not busy and (has_items or mw.start.isEnabled()))
        self.optimize_doc_button.setEnabled(can_opt_cur or (not busy and mw.optimize_btn.isEnabled()))
        self.convert_selected_btn.setEnabled(can_opt_cur)
        self.extract_selected_inline_btn.setEnabled(not busy and has_items)
        self.prev_button.setEnabled(not busy and has_items)
        self.next_button.setEnabled(not busy and has_items)
        self.toggle_compare_btn.setEnabled(not busy and has_row)
        self.refresh_button.setEnabled(not busy and has_row)
        self.open_folder_button.setEnabled(not busy and bool(mw.result_folders))
        for b in (self.zoom_in_btn, self.zoom_out_btn, self.zoom_reset_btn):
            b.setEnabled(has_row)
        for b in (self.filter_1mb_btn, self.filter_500kb_btn, self.filter_lossless_btn):
            b.setEnabled(not busy and has_items)

    def update_preview_content(self, pixmap: QPixmap | None, info_text: str, error_text: str = ""):
        self.sync_from_main()
        self.preview_info.setText(info_text)
        if error_text or pixmap is None or pixmap.isNull():
            self.preview_pixmap = None
            self.image.clear()
            self.image.setText(error_text or "미리보기 불가")
            return
        self.preview_pixmap = pixmap
        self.refresh_pixmap()

    def refresh_pixmap(self):
        if self.preview_pixmap and not self.preview_pixmap.isNull():
            if self.zoom_factor > 0.0:
                sz = self.preview_pixmap.size()
                target_size = QSize(max(40, int(sz.width() * self.zoom_factor)), max(40, int(sz.height() * self.zoom_factor)))
            else:
                target_size = self.image.size()
            self.image.setPixmap(self.preview_pixmap.scaled(target_size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    def extract_current(self):
        self.main_window.extract_current_image()

    def extract_checked_all(self):
        self.main_window.extract_selected_in_current_document()

    def optimize_current_doc(self):
        self.main_window.optimize_selected_in_current_document()

    def close_to_list(self):
        self.hide()
        self.main_window.return_to_list()