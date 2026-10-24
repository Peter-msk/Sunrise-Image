"""Sunrise Image — Main window controller (KISS, SRP, Layout-Grouped Modularity, and Single Source of Truth)."""
from __future__ import annotations
import html
import logging
import os
import io
import sys
import threading
from dataclasses import replace
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QSize, QThreadPool, QTimer, QUrl, Qt, Slot
from PySide6.QtGui import QColor, QDesktopServices, QFont, QPixmap
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QFrame, QHBoxLayout, QMessageBox,
    QSplitter, QTabWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from document_optimizer import optimize_document
from document_reader import HANCOM_NOTICE, OPTIMIZABLE, SUPPORTED, open_document, scan_document
from image_engine import Cancelled, DPI_FORMATS, Settings, checkpoint, convert_item, extract_images, human_location, open_raster
from product_info import APP_NAME
from progress_state import BatchProgress
from ui_layout_groups import (
    attach_progress_footer_group, apply_layout_styles,
    build_capacity_settings_group,
    build_collection_shared_group,
    build_document_list_group,
    build_format_settings_group,
    build_header_group,
    build_resolution_settings_group,
)
from ui_preview_dialog import PreviewDialog
from ui_theme import BLUE, CORAL, INDIGO, INK, RED, TEAL, application_icon, build_stylesheet
from ui_widgets import (
    Task, format_compact_size, format_size, make_btn, relayout_widget_tree,
)


PRESETS = [
    ('보고서·사진 JPG', 'report_jpg', 'JPG(품질 95%) · 원본 해상도 · 일반 보고서 및 사진 추출'),
    ('문서 용량 줄이기', 'doc_diet', 'JPG(품질 85%) · 한 장당 300 KB 목표 · 초과 시 픽셀 축소 · 한글(HWPX)·PDF·엑셀(XLSX) 경량화 추천'),
    ('한글 본문 자르기 PNG', 'hwpx_crop', 'PNG 무손실 · 투명 유지 · 한글(HWPX) 본문 자르기 반영'),
    ('인쇄용 300 DPI', 'print_300', 'PNG 무손실 · 300 DPI 인쇄 밀도 지정 · 원본 픽셀 유지'),
    ('원본 그대로 추출', 'original', '재변환 없이 문서 내장 원본 파일 형식으로 즉시 추출'),
]

PRESET_CONFIGS = {
    'report_jpg': (0, 95, 0, False, False, 500, False, False),
    'doc_diet':   (0, 85, 0, False, True,  300, True,  False),
    'hwpx_crop':  (1, 95, 0, False, False, 500, False, True),
    'print_300':  (1, 95, 0, True,  False, 500, False, False),
}

FORMAT_NOTES = {
    'JPEG': 'JPG는 손실 압축 · 투명 배경은 흰색 또는 검정으로 처리합니다. (문서 경량화 시 투명 직인은 PNG 자동 유지)',
    'PNG': 'PNG는 무손실 압축 · 투명 배경과 DPI 저장을 지원합니다.',
    'WEBP': 'WebP는 손실 / 무손실 선택 · DPI는 EXIF에 저장하며 뷰어 지원이 다를 수 있습니다.',
    'TIFF': 'TIFF는 LZW 무손실 압축 · 투명 배경과 인쇄용 DPI를 저장합니다.',
    'ORIGINAL': '내장 원본 형식으로 추출합니다. PDF 투명 마스크는 PNG로 복원하며 조정 설정은 적용하지 않습니다.',
}

SCOPE_LABELS = {
    'all': '전체 이미지',
    'lossless_only': 'PNG·BMP 무손실 이미지',
    'over_1mb': '1MB 이상 대용량 이미지',
    'over_500kb': '500KB 이상 이미지',
    'over_100kb': '100KB 이상 이미지',
    'custom': '직접 선택한 이미지',
}


class Window(QWidget):
    def __init__(self):
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(1180, 720)
        self.files: list[Path] = []
        self.catalogs = {}
        self.catalog_errors = {}
        self.checked_keys = {}
        self.optimized_results = {}
        self.pending_scans = set()
        self.scan_generation = 0
        self.scan_cancel = threading.Event()
        self.jobs = {}
        self.progress_timer = QTimer(self)
        self.progress_timer.setInterval(33)
        self.progress_timer.timeout.connect(self._flush_job_progress)
        self.progress_timer.start()
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(2)
        self.cancel = threading.Event()
        self.busy = False
        self.closing = False
        self.dark_mode = False
        self.work_mode = 'extract'
        self.active_image_filter = 'all'
        self._syncing_filter_ui = False
        self.preview_job = None
        self.preview_cancel = threading.Event()
        self.preview_pixmap = None
        self.result_folders: list[str] = []
        self.batch_progress = None
        self.preview_dialog = None
        self._syncing_doc_selection = False

        # Apply stylesheet before constructing child widgets so initial sizeHints match QSS metrics
        self._apply_qss_only()
        self.build()
        self.badge.setToolTip(APP_NAME)
        self.log.document().setMaximumBlockCount(2000)
        self.preview_dialog = PreviewDialog(self)
        self.apply_theme()
        self.resize(1200, 760)
        self.setAcceptDrops(True)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(350)
        self.timer.timeout.connect(self.preview)
        self.collection_tabs.currentChanged.connect(self.collection_page_changed)
        self.connect_settings()
        self.sync()
        relayout_widget_tree(self)

    def _apply_qss_only(self):
        asset_dir = (Path(__file__).resolve().parent / 'assets').as_posix().replace("'", "\\'")
        qss = build_stylesheet(self.dark_mode, asset_dir)
        self.setStyleSheet(qss)
        return qss

    def showEvent(self, event):
        super().showEvent(event)
        relayout_widget_tree(self)
        QTimer.singleShot(0, lambda: not self.closing and relayout_widget_tree(self))

    def build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 8, 12, 8)
        outer.setSpacing(6)
        outer.addWidget(self._build_header())

        workspace = QHBoxLayout()
        workspace.setContentsMargins(0, 0, 0, 0)
        workspace.setSpacing(10)
        outer.addLayout(workspace, 1)

        workspace.addWidget(self._build_left_doc_panel())
        self._build_collection_widgets()
        workspace.addWidget(self._build_right_settings_panel(), 1)
        self.setWindowIcon(application_icon())

    def _build_header(self) -> QFrame:
        return build_header_group(self, PRESETS)

    def _build_left_doc_panel(self) -> QSplitter:
        return build_document_list_group(self)

    def _build_collection_widgets(self):
        build_collection_shared_group(self)

    def _build_right_settings_panel(self) -> QWidget:
        right = QWidget()
        right.setObjectName('workspacePanel')
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(6)

        self.adjust_tabs = QTabWidget()
        self.adjust_tabs.hide()

        rl.addWidget(build_format_settings_group(self))
        rl.addWidget(build_resolution_settings_group(self))
        rl.addWidget(build_capacity_settings_group(self))
        attach_progress_footer_group(self, rl, HANCOM_NOTICE)
        return right

    def _filter_keys_for_catalog(self, catalog, scope: str) -> set[str]:
        if catalog is None:
            return set()
        if scope == 'lossless_only':
            return {i.key for i in catalog.items if i.format.upper() in {'PNG', 'BMP', 'TIFF'}}
        if scope == 'over_1mb':
            return {i.key for i in catalog.items if i.stored_bytes >= 1024 * 1024}
        if scope == 'over_500kb':
            return {i.key for i in catalog.items if i.stored_bytes >= 500 * 1024}
        if scope == 'over_100kb':
            return {i.key for i in catalog.items if i.stored_bytes >= 100 * 1024}
        return {i.key for i in catalog.items}

    def _sync_filter_ui(self):
        self._syncing_filter_ui = True
        try:
            if hasattr(self, 'main_filter_buttons'):
                for k, btn in self.main_filter_buttons.items():
                    btn.setProperty('activeFilter', k == self.active_image_filter)
                    if hasattr(btn, 'style') and btn.style() is not None:
                        btn.style().unpolish(btn)
                        btn.style().polish(btn)
            if hasattr(self, 'target_scope_combo'):
                self.target_scope_combo.blockSignals(True)
                idx = self.target_scope_combo.findData(self.active_image_filter)
                if idx >= 0:
                    self.target_scope_combo.setCurrentIndex(idx)
                self.target_scope_combo.blockSignals(False)
        finally:
            self._syncing_filter_ui = False

    def _on_target_scope_combo_changed(self, *_):
        if self._syncing_filter_ui or self.busy:
            return
        scope = self.target_scope_combo.currentData()
        if scope == 'custom':
            self.active_image_filter = 'custom'
            self._sync_filter_ui()
            if self.files:
                self.open_document_preview()
            return
        if scope:
            self.apply_global_image_filter(scope)

    def apply_global_image_filter(self, scope: str):
        if self.busy:
            return
        self.active_image_filter = scope
        self._sync_filter_ui()
        for doc in self.files:
            key = self.mode_key(doc)
            cat = self.catalogs.get(key)
            if cat is not None:
                self.checked_keys[key] = self._filter_keys_for_catalog(cat, scope)
        path = self.current_path()
        if path is not None and self.mode_key(path) in self.catalogs:
            rows = [self.tree.topLevelItem(i) for i in range(self.tree.topLevelItemCount())]
            target_keys = set(self.checked_keys.get(self.mode_key(path), set()))
            self._commit_checks(path, target_keys, rows)
            matched_rows = [r for r in rows if r.data(0, Qt.ItemDataRole.UserRole).key in target_keys]
            if matched_rows:
                self.tree.setCurrentItem(matched_rows[0])
                self.tree.scrollToItem(matched_rows[0])
                self.request_preview()
        else:
            self.refresh_selection_status()
        self.sync()
        if self.files and not self.pending_scans:
            total = sum(len(self.catalogs[self.mode_key(p)].items) for p in self.files if self.mode_key(p) in self.catalogs)
            selected = sum(len(self.checked_keys.get(self.mode_key(p), set())) for p in self.files if self.mode_key(p) in self.catalogs)
            scope_title = SCOPE_LABELS.get(scope, '선택한 이미지')
            self.status.setText(f'✓ 변환 대상 [{scope_title}]: 선택 {selected:,} / 전체 {total:,}개')

    def apply_theme(self):
        qss = self._apply_qss_only()
        if hasattr(self, 'theme_button'):
            self.theme_button.setText('라이트 테마' if self.dark_mode else '다크 테마')
        if self.preview_dialog is not None:
            self.preview_dialog.setStyleSheet(qss)
            relayout_widget_tree(self.preview_dialog)
        apply_layout_styles(self, self.dark_mode)
        if hasattr(self, 'doc_table'):
            self.update_document_rows()
        relayout_widget_tree(self)

    def toggle_theme(self):
        self.dark_mode = not self.dark_mode
        self.apply_theme()

    def connect_settings(self):
        for w in (self.format, self.alpha, self.rotate, self.naming_mode, self.resize_mode):
            w.currentIndexChanged.connect(self.setting_changed)
        for w in (self.percent, self.width, self.height, self.dpi, self.quality, self.png, self.target):
            w.valueChanged.connect(self.setting_changed)
        for w in (self.gray, self.upscale, self.change_dpi, self.lossless, self.use_target, self.shrink):
            w.toggled.connect(self.setting_changed)

    def apply_preset(self, preset_key):
        if self.busy:
            return
        if preset_key == 'original':
            self.format.setCurrentIndex(self.format.count() - 1)
        elif preset_key in PRESET_CONFIGS:
            fmt_idx, qual, res_idx, dpi_on, tgt_on, tgt_val, shrink_on, crop_on = PRESET_CONFIGS[preset_key]
            self.format.setCurrentIndex(fmt_idx)
            self.quality.setValue(qual)
            self.resize_mode.setCurrentIndex(res_idx)
            self.change_dpi.setChecked(dpi_on)
            if dpi_on:
                self.dpi.setValue(300)
            if preset_key == 'hwpx_crop':
                self.alpha.setCurrentIndex(0)
            if tgt_on:
                self.target_unit.setCurrentIndex(0)
            self.use_target.setChecked(tgt_on)
            if tgt_on:
                self.target.setValue(tgt_val)
                self.shrink.setChecked(shrink_on)
            self.crop.setChecked(crop_on)

        for k, b in self.preset_map.items():
            b.setProperty('activePreset', k == preset_key)
            if hasattr(b, 'style') and b.style() is not None:
                b.style().unpolish(b)
                b.style().polish(b)
        self.sync()
        self.request_preview()

    def focus_search(self):
        if not self.busy:
            if self.preview_dialog is not None and not self.preview_dialog.isVisible() and self.files:
                self.open_preview()
            self.search.setFocus(Qt.FocusReason.ShortcutFocusReason)
            self.search.selectAll()

    def step_preview_item(self, delta):
        if self.busy or self.tree.topLevelItemCount() == 0:
            return
        visible = [self.tree.topLevelItem(i) for i in range(self.tree.topLevelItemCount()) if not self.tree.topLevelItem(i).isHidden()]
        if not visible:
            return
        cur = self.tree.currentItem()
        idx = visible.index(cur) if cur in visible else 0
        self.tree.setCurrentItem(visible[(idx + delta) % len(visible)])
        self.preview()

    def _on_use_target_toggled(self, checked):
        if checked and not self.shrink.isChecked():
            self.shrink.setChecked(True)

    def _on_target_unit_changed(self, *_):
        if self.target_unit.currentData() == 'MB' and self.target.value() >= 100:
            self.target.setValue(max(1, round(self.target.value() / 1024)))
        elif self.target_unit.currentData() != 'MB' and self.target.value() <= 10:
            self.target.setValue(self.target.value() * 500)
        self.setting_changed()

    def _target_kb_value(self) -> int:
        if not self.use_target.isChecked():
            return 0
        return self.target.value() * (1024 if self.target_unit.currentData() == 'MB' else 1)

    def settings(self):
        return Settings(
            format=self.format.currentData(),
            dpi=self.dpi.value() if self.change_dpi.isChecked() else None,
            resize=self.resize_mode.currentData(),
            percent=self.percent.value(),
            width=self.width.value(),
            height=self.height.value(),
            allow_upscale=self.upscale.isChecked(),
            quality=self.quality.value(),
            png_compression=self.png.value(),
            webp_lossless=self.lossless.isChecked(),
            target_kb=self._target_kb_value(),
            shrink_for_target=self.shrink.isChecked(),
            alpha=self.alpha.currentData(),
            grayscale=self.gray.isChecked(),
            rotate=self.rotate.currentData(),
            apply_document_crop=self.crop.isChecked(),
            naming=self.naming_mode.currentData(),
        )

    def setting_changed(self, *_):
        if self.format.currentData() == 'ORIGINAL' and self.crop.isChecked():
            self.crop.setChecked(False)
        self.sync()
        self.request_preview()

    def crop_changed(self, *_):
        self.refresh_catalogs()
        self.sync()
        self.request_preview()

    def show_log(self, visible):
        self.tabs.setVisible(visible)
        self.toggle_log.setText('처리 기록 닫기' if visible else '처리 기록 보기')
        if visible:
            self.resize(self.rect().width(), max(860, self.rect().height() + 100))
        else:
            self.resize(self.rect().width(), max(720, self.rect().height() - 100))
        relayout_widget_tree(self)

    def sync(self):
        fmt = self.format.currentData()
        original = fmt == 'ORIGINAL'
        resize = self.resize_mode.currentData()
        for w in (self.crop, self.size_card, self.capacity_card, self.alpha, self.rotate, self.gray):
            w.setEnabled(not original and not self.busy)
        self.naming_mode.setEnabled(not self.busy)
        if hasattr(self, 'target_scope_combo'):
            self.target_scope_combo.setEnabled(not self.busy)
            self.open_list_select_btn.setEnabled(not self.busy and bool(self.files))
        if hasattr(self, 'main_filter_buttons'):
            for b in (*self.main_filter_buttons.values(), self.main_open_select_btn):
                b.setEnabled(not self.busy)
        self.percent.setEnabled(resize == 'percent')
        self.width.setEnabled(resize in {'long_edge', 'fit'})
        self.height.setEnabled(resize == 'fit')
        self.upscale.setEnabled(resize != 'original')
        self.change_dpi.setEnabled(fmt in DPI_FORMATS)
        self.dpi.setEnabled(fmt in DPI_FORMATS and self.change_dpi.isChecked())
        self.quality.setEnabled(fmt == 'JPEG' or (fmt == 'WEBP' and not self.lossless.isChecked()))
        self.png.setEnabled(fmt == 'PNG' and not self.use_target.isChecked())
        self.lossless.setEnabled(fmt == 'WEBP')
        for w in (self.target, self.target_unit, self.shrink):
            w.setEnabled(self.use_target.isChecked())

        self.format_note.setText(FORMAT_NOTES.get(fmt, FORMAT_NOTES['JPEG']))
        size_text = {
            'original': '원본 픽셀 유지',
            'percent': f'{self.percent.value()}% / 비율 유지',
            'long_edge': f'긴 변 {self.width.value()}px',
            'fit': f'{self.width.value()} × {self.height.value()}px 이내',
        }[resize]
        dpi_text = (f'{self.dpi.value()} DPI' if self.change_dpi.isChecked() else '원본 DPI(가능 시)') if fmt in DPI_FORMATS else 'DPI 미적용'
        target_text = f' / 한 장당 {format_size(self._target_kb_value() * 1024)} 이하 목표' if self.use_target.isChecked() else ''
        scope_tag = f' / 대상: {SCOPE_LABELS.get(self.active_image_filter, "전체 이미지")}' if self.active_image_filter != 'all' else ''
        self.summary.setText(
            f'원본 형식 / 재변환 없이 추출{scope_tag}'
            if original
            else f'{fmt}  /  {size_text}  /  {dpi_text}{target_text}' + (' / 한글 본문 자르기' if self.crop.isChecked() else '') + scope_tag
        )
        self._sync_filter_ui()
        if self.preview_dialog is not None:
            self.preview_dialog.sync_from_main()

    def launch(self, function, kind):
        task = Task(function, kind)
        self.jobs[task.id] = task
        task.signals.event.connect(self.on_event, Qt.ConnectionType.QueuedConnection)
        self.pool.start(task)
        return task.id

    def _flush_job_progress(self):
        for task in list(self.jobs.values()):
            task.flush_progress()

    def mode_key(self, path):
        return (str(path), self.crop.isChecked())

    def current_path(self):
        row = self.file_list.currentRow()
        return self.files[row] if 0 <= row < len(self.files) else None

    def select_document_row(self, index: int):
        if 0 <= index < len(self.files):
            self.file_list.setCurrentRow(index)

    def _on_file_list_row_changed(self, row: int):
        if not self._syncing_doc_selection:
            self._syncing_doc_selection = True
            try:
                if 0 <= row < self.doc_table.topLevelItemCount():
                    self.doc_table.setCurrentItem(self.doc_table.topLevelItem(row))
            finally:
                self._syncing_doc_selection = False
        self.scan(row)
        if self.preview_dialog is not None:
            self.preview_dialog.sync_from_main()

    def _on_doc_table_current_changed(self, current, previous):
        if not self._syncing_doc_selection and current is not None:
            idx = self.doc_table.indexOfTopLevelItem(current)
            if 0 <= idx < self.file_list.count():
                self._syncing_doc_selection = True
                try:
                    self.file_list.setCurrentRow(idx)
                finally:
                    self._syncing_doc_selection = False

    def _on_doc_table_clicked(self, item, column):
        idx = self.doc_table.indexOfTopLevelItem(item)
        if idx >= 0 and column == 2:
            self.open_document_preview(idx)

    def _on_doc_table_double_clicked(self, item, column):
        idx = self.doc_table.indexOfTopLevelItem(item)
        if idx >= 0:
            self.open_document_preview(idx)

    def open_document_preview(self, row_index: int | None = None):
        if row_index is not None and 0 <= row_index < len(self.files):
            self.select_document_row(row_index)
        if self.tree.currentItem() is None and self.tree.topLevelItemCount() > 0:
            self.tree.setCurrentItem(self.tree.topLevelItem(0))
        self.open_preview()

    def choose_files(self):
        patterns = ' '.join('*' + e for e in SUPPORTED)
        paths, _ = QFileDialog.getOpenFileNames(
            self, '이미지를 추출할 문서 선택', '',
            f'지원 문서 ({patterns});;한글 HWPX (*.hwpx);;PDF (*.pdf);;Office (*.docx *.xlsx *.pptx)',
        )
        self.add_files(paths)

    def choose_input_folder(self):
        folder = QFileDialog.getExistingDirectory(self, '문서가 들어있는 폴더 선택', self.destination.text())
        if folder:
            self.add_files([folder])

    def _make_doc_preview_button(self, path_obj: Path):
        return make_btn(
            '미리보기',
            lambda _=False, p=path_obj: self.open_document_preview(self.files.index(p)) if p in self.files else None,
            obj='docPreviewButton',
            tip=f"'{path_obj.name}' 문서의 이미지 목록(LIST) 및 미리보기 팝업창을 엽니다.",
        )

    def _expand_input_paths(self, raw_paths, cancel=None) -> tuple[list[Path], bool]:
        expanded: list[Path] = []
        rejected_hwp = False
        def walk(folder):
            for directory, subdirs, names in os.walk(folder, followlinks=False):
                checkpoint(cancel)
                subdirs.sort()
                for name in sorted(names):
                    yield Path(directory) / name
        for raw in raw_paths:
            p = Path(raw).resolve()
            targets = walk(p) if p.is_dir() else [p]
            for item in targets:
                checkpoint(cancel)
                if not item.is_file():
                    continue
                ext = item.suffix.lower()
                if ext == '.hwp':
                    rejected_hwp = True
                elif ext in SUPPORTED and (not p.is_dir() or not item.stem.endswith('_경량화')):
                    expanded.append(item.resolve())
        return list(dict.fromkeys(expanded)), rejected_hwp

    def add_files(self, paths):
        if self.busy:
            return
        if any(Path(raw).is_dir() for raw in paths):
            self.set_busy(True)
            self.status.setText('폴더에서 문서를 찾고 있습니다…')
            self.cancel.clear()
            captured, cancel = list(paths), self.cancel
            self.launch(lambda emit: self._expand_input_paths(captured, cancel), 'inputs')
            return
        candidates, rejected_hwp = self._expand_input_paths(paths)
        self._add_candidates(candidates, rejected_hwp)

    def _add_candidates(self, candidates, rejected_hwp):
        for p in candidates:
            if p not in self.files:
                self.files.append(p)
                self.file_list.addItem(p.name)
                self.file_list.item(self.file_list.count() - 1).setToolTip(str(p))
                doc_item = QTreeWidgetItem([p.name, '분석 중…', ''])
                doc_item.setSizeHint(0, QSize(0, 30))
                if hasattr(doc_item, 'setTextAlignment'):
                    doc_item.setTextAlignment(0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                    doc_item.setTextAlignment(1, Qt.AlignmentFlag.AlignCenter)
                    doc_item.setTextAlignment(2, Qt.AlignmentFlag.AlignCenter)
                doc_item.setToolTip(0, str(p))
                self.doc_table.addTopLevelItem(doc_item)
                self.doc_table.setItemWidget(doc_item, 2, self._make_doc_preview_button(p))
        if self.files:
            if not self.destination.text():
                self.destination.setText(str(self.files[0].parent))
            self.file_list.setCurrentRow(len(self.files) - 1)
            self.queue_scan()
        self.refresh_selection_status()
        if rejected_hwp:
            self.status.setText('구형 한글(.hwp)은 지원 대상에서 제외되었습니다. 개방형 한글(.hwpx)을 사용하세요.')

    def remove_files(self):
        if self.busy:
            return
        table_rows = {self.doc_table.indexOfTopLevelItem(i) for i in self.doc_table.selectedItems()}
        list_rows = {self.file_list.row(i) for i in self.file_list.selectedItems()}
        rows = sorted((table_rows | list_rows) - {-1}, reverse=True)
        if not rows:
            return
        self.file_list.blockSignals(True)
        self.doc_table.blockSignals(True)
        for row in rows:
            self.file_list.takeItem(row)
            self.doc_table.takeTopLevelItem(row)
            removed = self.files.pop(row)
            self.optimized_results.pop(str(removed), None)
            for store in (self.catalogs, self.catalog_errors, self.checked_keys):
                for key in list(store):
                    if key[0] == str(removed):
                        store.pop(key, None)
        self.doc_table.blockSignals(False)
        self.file_list.blockSignals(False)
        if self.files and self.file_list.currentRow() < 0:
            self.file_list.setCurrentRow(min(rows[-1], len(self.files) - 1))
        self.scan_generation += 1
        self.scan_cancel.set()
        self.scan_cancel = threading.Event()
        self.pending_scans.clear()
        self.scan(self.file_list.currentRow())
        self.queue_scan()
        self.refresh_selection_status()

    def clear_files(self):
        if self.busy or not self.files:
            return
        self.scan_generation += 1
        self.scan_cancel.set()
        self.scan_cancel = threading.Event()
        self.pending_scans.clear()
        self.catalogs.clear()
        self.catalog_errors.clear()
        self.checked_keys.clear()
        self.optimized_results.clear()
        for w in (self.file_list, self.doc_table):
            w.blockSignals(True)
            w.clear()
            w.blockSignals(False)
        self.files.clear()
        self.scan(-1)
        self.refresh_selection_status()

    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, '저장 폴더 선택', self.destination.text())
        if folder:
            self.destination.setText(folder)

    def open_destination_folder(self):
        target = self.destination.text().strip()
        if target and Path(target).expanduser().exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(target).expanduser().resolve())))

    def dragEnterEvent(self, event):
        if not self.busy and event.mimeData().hasUrls():
            if any(Path(u.toLocalFile()).is_dir() or Path(u.toLocalFile()).suffix.lower() in {*SUPPORTED, '.hwp'} for u in event.mimeData().urls()):
                event.acceptProposedAction()

    def dropEvent(self, event):
        self.add_files([u.toLocalFile() for u in event.mimeData().urls()])
        event.acceptProposedAction()

    def refresh_catalogs(self, *_):
        if self.busy:
            return
        self.scan_generation += 1
        self.scan_cancel.set()
        self.scan_cancel = threading.Event()
        self.pending_scans.clear()
        for path in self.files:
            key = self.mode_key(path)
            self.catalogs.pop(key, None)
            self.catalog_errors.pop(key, None)
        self.scan(self.file_list.currentRow())
        self.queue_scan()

    def queue_scan(self):
        if self.busy or self.closing:
            return
        mode = self.crop.isChecked()
        generation = self.scan_generation
        cancel = self.scan_cancel
        paths = [
            p for p in self.files
            if self.mode_key(p) not in self.catalogs
            and self.mode_key(p) not in self.catalog_errors
            and self.mode_key(p) not in self.pending_scans
        ]
        if not paths:
            return
        for path in paths:
            self.pending_scans.add((str(path), mode))
        self.start.setEnabled(False)
        self.optimize_btn.setEnabled(False)
        self.status.setText('이미지 목록을 읽고 있습니다…')

        def work(emit):
            for path in paths:
                if cancel.is_set():
                    break
                try:
                    cat, error = scan_document(path, mode, cancel), ''
                except Exception as exc:
                    cat, error = None, str(exc)
                emit({'type': 'catalog', 'source': str(path), 'mode': mode, 'generation': generation, 'catalog': cat, 'error': error})
            return None

        self.launch(work, 'scan_done')

    def scan(self, row):
        self.preview_cancel.set()
        self.preview_job = None
        self.preview_pixmap = None
        self.tree.blockSignals(True)
        self.tree.clear()
        self.tree.blockSignals(False)
        self.image.clear()
        self.image.setText('목록에서 이미지를 선택하세요.')
        path = self.current_path()
        if path is None:
            self.selection_info.setText('문서를 추가하면 내장 이미지 전체 목록을 표시합니다.')
            self.refresh_selection_status()
            return
        key = self.mode_key(path)
        if key in self.catalogs:
            self.show_catalog(self.catalogs[key])
        elif key in self.catalog_errors:
            self.image.setText('문서를 읽을 수 없습니다.')
            self.preview_info.setText(self.catalog_errors[key])
            self.selection_info.setText(self.catalog_errors[key])
        else:
            self.selection_info.setText('이미지 목록을 읽고 있습니다…')
            self.queue_scan()
        self.refresh_selection_status()

    def show_catalog(self, catalog):
        path = self.current_path()
        if path is None:
            return
        key = self.mode_key(path)
        valid = {i.key for i in catalog.items}
        default_keys = self._filter_keys_for_catalog(catalog, self.active_image_filter if self.active_image_filter != 'custom' else 'all')
        self.checked_keys[key] = (self.checked_keys[key] & valid) if key in self.checked_keys else set(default_keys)
        selected = self.checked_keys[key]
        self.tree.blockSignals(True)
        self.tree.clear()
        for ordinal, item in enumerate(catalog.items, 1):
            size = ' × '.join(map(str, item.size)) if item.size else '—'
            location = human_location(item.location)
            crop = '자르기 · ' + location if item.crop else location
            crop_note = ''
            if item.crop and item.size:
                try:
                    box, _ = item.crop.pixels(item.size)
                    size = f'{box[2] - box[0]} × {box[3] - box[1]}'
                    crop_note = f'원본 {item.size[0]} × {item.size[1]} px / 본문 자르기 {size} px\n영역: {box}'
                except ValueError as exc:
                    crop_note, size = str(exc), '좌표 오류'
            vol_text = format_size(item.stored_bytes) if item.stored_bytes else '—'
            row = QTreeWidgetItem([f'{ordinal:03d} · ' + item.name, item.format, vol_text, size, crop])
            row.setSizeHint(0, QSize(0, 28))
            if hasattr(row, 'setTextAlignment'):
                row.setTextAlignment(0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                row.setTextAlignment(1, Qt.AlignmentFlag.AlignCenter)
                row.setTextAlignment(2, Qt.AlignmentFlag.AlignCenter)
                row.setTextAlignment(3, Qt.AlignmentFlag.AlignCenter)
                row.setTextAlignment(4, Qt.AlignmentFlag.AlignCenter)
            row.setData(0, Qt.ItemDataRole.UserRole, item)
            row.setFlags(row.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            row.setCheckState(0, Qt.CheckState.Checked if item.key in selected else Qt.CheckState.Unchecked)
            row.setToolTip(0, item.member + f' ({vol_text})' + ('\n' + item.error if item.error else ''))
            row.setToolTip(2, f'{item.stored_bytes:,} 바이트 ({vol_text})')
            row.setToolTip(3, crop_note or ('원본 ' + size + ' px'))
            row.setToolTip(4, location + ('\n' + '; '.join(item.notes) if item.notes else ''))
            self.tree.addTopLevelItem(row)
        self.tree.blockSignals(False)
        self.filter_items()
        if self.tree.topLevelItemCount():
            self.tree.setCurrentItem(self.tree.topLevelItem(0))
            self.request_preview()
        else:
            self.image.setText('추출 가능한 내장 이미지가 없습니다.')
        self.refresh_selection_status()

    def filter_items(self, *_):
        term = self.search.text().strip().casefold()
        for i in range(self.tree.topLevelItemCount()):
            row = self.tree.topLevelItem(i)
            row.setHidden(bool(term) and term not in ' '.join(row.text(c) for c in range(5)).casefold())

    def open_preview(self, *_):
        if self.tree.currentItem() is None and self.tree.topLevelItemCount() > 0:
            self.tree.setCurrentItem(self.tree.topLevelItem(0))
        if self.tree.currentItem() is None and not self.files:
            return
        self.collection_tabs.setCurrentIndex(1)
        if self.preview_dialog is not None:
            self.preview_dialog.sync_from_main()
            self.preview_dialog.show()
            if hasattr(self.preview_dialog, 'raise_'):
                self.preview_dialog.raise_()
        if self.tree.currentItem() is not None:
            self.preview()

    def return_to_list(self):
        if self.preview_dialog is not None and self.preview_dialog.isVisible():
            self.preview_dialog.hide()
        self.collection_tabs.setCurrentIndex(0)
        item = self.tree.currentItem()
        if item is not None and not item.isHidden():
            self.tree.scrollToItem(item)
        self.tree.setFocus(Qt.FocusReason.OtherFocusReason)

    def collection_page_changed(self, index):
        if index == 1:
            self.request_preview()
        elif self.preview_dialog is None or not self.preview_dialog.isVisible():
            self.timer.stop()
            self.preview_cancel.set()
            self.preview_job = None

    def _commit_checks(self, path, keys, rows):
        if self.busy:
            return
        self.checked_keys[self.mode_key(path)] = keys
        self.tree.blockSignals(True)
        self.tree.setUpdatesEnabled(False)
        try:
            for row in rows:
                item = row.data(0, Qt.ItemDataRole.UserRole)
                row.setCheckState(0, Qt.CheckState.Checked if item.key in keys else Qt.CheckState.Unchecked)
        finally:
            self.tree.setUpdatesEnabled(True)
            self.tree.blockSignals(False)
        self.refresh_selection_status()

    def change_checks(self, checked, visible_only=True):
        path = self.current_path()
        if self.busy or path is None:
            return
        rows = [self.tree.topLevelItem(i) for i in range(self.tree.topLevelItemCount())]
        targets = [r for r in rows if not visible_only or not r.isHidden()]
        keys = set(self.checked_keys.get(self.mode_key(path), set()))
        t_keys = {r.data(0, Qt.ItemDataRole.UserRole).key for r in targets}
        self.active_image_filter = 'all' if (checked and not visible_only) else 'custom'
        self._sync_filter_ui()
        self._commit_checks(path, keys | t_keys if checked else keys - t_keys, targets)

    def invert_checks(self):
        path = self.current_path()
        if self.busy or path is None:
            return
        targets = [self.tree.topLevelItem(i) for i in range(self.tree.topLevelItemCount()) if not self.tree.topLevelItem(i).isHidden()]
        keys = set(self.checked_keys.get(self.mode_key(path), set()))
        t_keys = {r.data(0, Qt.ItemDataRole.UserRole).key for r in targets}
        self.active_image_filter = 'custom'
        self._sync_filter_ui()
        self._commit_checks(path, (keys - t_keys) | (t_keys - keys), targets)

    def change_scope_checks(self, checked, scope):
        if self.busy:
            return
        path = self.current_path()
        if scope == 'visible':
            self.change_checks(checked)
        elif scope == 'documents':
            if self.pending_scans:
                self.status.setText('모든 문서의 목록을 읽은 뒤 전체 선택·취소할 수 있습니다.')
                return
            self.active_image_filter = 'all' if checked else 'custom'
            self._sync_filter_ui()
            for doc in self.files:
                cat = self.catalogs.get(self.mode_key(doc))
                if cat:
                    self.checked_keys[self.mode_key(doc)] = {i.key for i in cat.items} if checked else set()
            if path:
                rows = [self.tree.topLevelItem(i) for i in range(self.tree.topLevelItemCount())]
                self._commit_checks(path, set(self.checked_keys.get(self.mode_key(path), set())), rows)
        elif scope in {'all_docs_lossless', 'all_docs_over_1mb'}:
            if self.pending_scans:
                self.status.setText('모든 문서의 목록을 읽은 뒤 필터 선택할 수 있습니다.')
                return
            mapped = 'lossless_only' if scope == 'all_docs_lossless' else 'over_1mb'
            self.apply_global_image_filter(mapped)
        elif scope in {'over_100kb', 'over_500kb', 'over_1mb', 'lossless_only'} and path is not None:
            self.active_image_filter = scope
            self._sync_filter_ui()
            rows = [self.tree.topLevelItem(i) for i in range(self.tree.topLevelItemCount())]
            limits = {'over_100kb': 100 * 1024, 'over_500kb': 500 * 1024, 'over_1mb': 1024 * 1024}
            matched_rows = [
                r for r in rows
                if (scope in limits and r.data(0, Qt.ItemDataRole.UserRole).stored_bytes >= limits[scope])
                or (scope == 'lossless_only' and r.data(0, Qt.ItemDataRole.UserRole).format.upper() in {'PNG', 'BMP', 'TIFF'})
            ]
            matched = {r.data(0, Qt.ItemDataRole.UserRole).key for r in matched_rows}
            self._commit_checks(path, matched, rows)
            if matched_rows:
                first_row = matched_rows[0]
                self.tree.setCurrentItem(first_row)
                self.tree.scrollToItem(first_row)
                self.request_preview()
        elif scope == 'rows' and path is not None:
            self.active_image_filter = 'custom'
            self._sync_filter_ui()
            rows = self.tree.selectedItems()
            keys = set(self.checked_keys.get(self.mode_key(path), set()))
            affected = {r.data(0, Qt.ItemDataRole.UserRole).key for r in rows}
            self._commit_checks(path, keys | affected if checked else keys - affected, rows)

    def item_checked(self, row, column):
        path, item = self.current_path(), row.data(0, Qt.ItemDataRole.UserRole)
        if path is not None and item is not None:
            keys = self.checked_keys.setdefault(self.mode_key(path), set())
            (keys.add if row.checkState(0) == Qt.CheckState.Checked else keys.discard)(item.key)
            cat = self.catalogs.get(self.mode_key(path))
            if cat and len(keys) == len(cat.items):
                self.active_image_filter = 'all'
            else:
                self.active_image_filter = 'custom'
            self._sync_filter_ui()
            self.refresh_selection_status()

    def refresh_selection_status(self):
        total = selected = 0
        missing = False
        for path in self.files:
            key = self.mode_key(path)
            if key not in self.catalogs and key not in self.catalog_errors:
                missing = True
            elif key in self.catalogs:
                total += len(self.catalogs[key].items)
                selected += len(self.checked_keys.get(key, {i.key for i in self.catalogs[key].items}))
        path = self.current_path()
        cat = self.catalogs.get(self.mode_key(path)) if path else None
        self.doc_count_badge.setText(f'문서 {len(self.files):,}개')
        if cat:
            cur_keys = self.checked_keys.get(self.mode_key(path), set())
            checked_bytes = sum(i.stored_bytes for i in cat.items if i.key in cur_keys)
            self.selection_info.setText(f'이 문서 {len(cat.items)}개 / 체크 {len(cur_keys)}개 ({format_size(checked_bytes)}) · 전체 문서 체크 {selected}개')
            self.selection_badge.setText(f'체크 {len(cur_keys):,} / {len(cat.items):,}개')
        else:
            self.selection_badge.setText(f'전체 체크 {selected:,}개')

        has_current = self.tree.currentItem() is not None and path is not None
        has_optimizable = any(p.suffix.lower() in OPTIMIZABLE for p in self.files)
        self.start.setEnabled(not self.busy and not missing and bool(self.files))
        self.optimize_btn.setEnabled(not self.busy and not missing and has_optimizable)
        self.clear_files_btn.setEnabled(not self.busy and bool(self.files))
        self.popup_preview_btn.setEnabled(not self.busy and has_current)
        self.extract_single_btn.setEnabled(not self.busy and has_current)
        self.update_document_rows()
        if self.preview_dialog is not None:
            self.preview_dialog.sync_from_main()
        if not self.busy:
            self.status.setText('목록 읽는 중…' if missing else f'문서 {len(self.files)}개 / 전체 {total}개 / 선택 {selected}개')
        if self.batch_progress is None:
            self.document_counts.setText(f'문서 {len(self.files):,}개 · 선택 이미지 {selected:,}개')

    def update_document_rows(self):
        runs = {d.path: d for d in self.batch_progress.documents} if self.batch_progress else {}
        fg_def, bg_def = ('#E4E4E7', '#12151E') if self.dark_mode else (INK, '#FFFFFF')
        fg_act, bg_act = ('#A5B4FC', '#1E1B4B') if self.dark_mode else (INDIGO, '#EEF2FF')
        fg_err = '#FDA4AF' if self.dark_mode else RED

        for index, path in enumerate(self.files):
            row, t_item = self.file_list.item(index), self.doc_table.topLevelItem(index)
            key = self.mode_key(path)
            cat, run, opt_pair = self.catalogs.get(key), runs.get(str(path)), self.optimized_results.get(str(path))
            if cat:
                sel = len(self.checked_keys.get(key, set()))
                raw_b = path.stat().st_size if path.is_file() else 0
                sz_str = f' · {format_size(raw_b)}' if raw_b else ''
                detail = f'선택 {sel:,} / 이미지 {len(cat.items):,}개{sz_str}'
                if opt_pair:
                    src_b, out_b = opt_pair
                    pct = ((out_b - src_b) / src_b * 100) if src_b > 0 else 0.0
                    col_text = f'{sel:,}/{len(cat.items):,}개 ({pct:+.0f}%)'
                    detail += f' · 경량화 {format_size(src_b)}→{format_size(out_b)} ({pct:+.1f}%)'
                else:
                    col_text = f'{sel:,}/{len(cat.items):,}개 ({format_compact_size(raw_b)})'
            else:
                detail = col_text = '읽기 실패' if key in self.catalog_errors else '분석 중…'

            if run:
                detail += f' · {run.state}' + (f' {run.processed:,}/{run.total:,}' if run.total is not None else '')
                if run.failed:
                    detail += f' · 이미지 실패 {run.failed:,}'
                if run.blocked:
                    detail += f' · 처리 불가 {run.blocked:,}'
            elif cat:
                detail += ' · 추출 대기' if sel else ' · 선택 없음'

            if row is not None:
                text = f'{path.name}\n{detail}'
                if row.text() != text:
                    row.setText(text)
                row.setToolTip(f'{path}\n{detail}')
                row.setSizeHint(QSize(0, 42))
                active = run is not None and run.state == '처리 중'
                font = row.font()
                font.setBold(active)
                row.setFont(font)
                row.setForeground(QColor(fg_act if active else fg_err if run and run.state == '실패' else fg_def))
                row.setBackground(QColor(bg_act if active else bg_def))
            if t_item is not None:
                t_item.setText(0, path.name)
                t_item.setText(1, col_text)
                if hasattr(t_item, 'setTextAlignment'):
                    t_item.setTextAlignment(0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                    t_item.setTextAlignment(1, Qt.AlignmentFlag.AlignCenter)
                    t_item.setTextAlignment(2, Qt.AlignmentFlag.AlignCenter)
                t_item.setToolTip(0, f'{path}\n{detail}')
                t_item.setToolTip(1, detail)
                btn = self.doc_table.itemWidget(t_item, 2)
                if btn is not None:
                    btn.setEnabled(not self.busy and cat is not None)

    def render_batch_progress(self):
        batch = self.batch_progress
        if batch is None:
            return
        self.progress.setRange(0, 1000)
        self.progress.setValue(round(batch.percent * 10))
        overall = f'전체 {batch.percent:.1f}% · 처리 {batch.processed:,}/{batch.total:,}개 · 남음 {batch.remaining:,}개'
        if batch.blocked:
            overall += f' · 처리 불가 {batch.blocked:,}개'
        if batch.unknown_documents:
            overall += f' · 이미지 수 미확인 문서 {batch.unknown_documents:,}개'
        self.progress.setFormat(overall)
        self.progress.setToolTip(overall)
        self.document_counts.setText(f'문서 처리 {batch.documents_done:,}/{len(batch.documents):,} · 남음 {len(batch.documents) - batch.documents_done:,} · 실패 {batch.documents_failed:,}')
        action = '변환' if getattr(self, 'work_mode', '') == 'optimize' and self.busy else '저장'
        self.status.setText(f'{action} {batch.saved:,}개 · 이미지 실패 {batch.failed:,}개')

        current = batch.current
        if current is not None:
            self.current_document.setText(f'현재 문서 {batch.current_index + 1}/{len(batch.documents)}: {Path(current.path).name} · {current.state}')
            self.current_document.setToolTip(f'{current.path}\n{current.state}')
            if current.member:
                prefix = '진행 이미지' if current.state == '처리 중' else '중지 시 이미지' if current.state == '중지됨' else '최근 이미지'
                self.current_image.setText(f'{prefix} {current.ordinal:,}: {current.member}')
            else:
                msg = '문서 오류로 시작하지 못함' if current.state == '실패' else '시작 전 중지됨' if current.state == '중지됨' else '문서 처리 완료' if current.terminal else '목록 확인 및 변환 준비 중…'
                self.current_image.setText('현재 이미지: ' + msg)
            if current.total is None:
                if current.state == '실패':
                    self.document_progress.setRange(0, 1000)
                    self.document_progress.setValue(0)
                    self.document_progress.setFormat('현재 문서 · 읽기 실패 / 이미지 수 미확인')
                else:
                    self.document_progress.setRange(0, 0)
                    self.document_progress.setFormat('현재 문서 · 이미지 수 확인 중')
            else:
                resolved = current.processed + current.blocked
                pct = 100 * resolved / current.total if current.total else (100 if current.terminal else 0)
                self.document_progress.setRange(0, 1000)
                self.document_progress.setValue(round(pct * 10))
                txt = f'현재 문서 {pct:.1f}% · 처리 {current.processed:,}/{current.total:,}개 · 남음 {current.remaining:,}개'
                if current.blocked:
                    txt += f' · 처리 불가 {current.blocked:,}개'
                self.document_progress.setFormat(txt)
        else:
            self.current_document.setText('현재 문서: 작업 중지됨' if batch.cancelled else '현재 문서: 추출 준비 중…')
            self.current_image.setText('현재 이미지: —')
            self.document_progress.setRange(0, 1000)
            self.document_progress.setValue(0)
            self.document_progress.setFormat('현재 문서 · 추출 대기')
        self.update_document_rows()

    def request_preview(self, *_):
        self.preview_cancel.set()
        self.preview_job = None
        if self.preview_dialog is not None:
            self.preview_dialog.sync_from_main()
        active = self.collection_tabs.currentIndex() == 1 or (self.preview_dialog is not None and self.preview_dialog.isVisible())
        if not self.busy and not self.closing and hasattr(self, 'timer') and active:
            self.timer.start()

    def preview(self):
        row, path = self.tree.currentItem(), self.current_path()
        if self.busy or self.closing or row is None or path is None:
            return
        if any(task.kind == 'preview' for task in self.jobs.values()):
            self.preview_cancel.set()
            self.timer.start()
            return
        self.timer.stop()
        self.preview_cancel.set()
        self.preview_cancel = cancel = threading.Event()
        item, settings, source_view = row.data(0, Qt.ItemDataRole.UserRole), self.settings(), self.preview_mode.currentIndex() == 1
        self.preview_info.setText('현재 이미지 처리 중…')
        if self.preview_dialog is not None:
            self.preview_dialog.sync_from_main()
            self.preview_dialog.preview_info.setText('현재 이미지 처리 중…')

        def work(emit):
            checkpoint(cancel)
            with open_document(path, settings.apply_document_crop, cancel) as reader:
                data = reader.read(item)
            checkpoint(cancel)
            if source_view:
                result = convert_item(data, replace(item, crop=None), Settings(format='PNG'), cancel)
                result.notes = ['원본 비교: 자르기·사용자 설정 미적용']
            else:
                result = convert_item(data, item, settings, cancel)
            checkpoint(cancel)
            with open_raster(result.data) as im:
                thumb = im.convert('RGBA')
                thumb.thumbnail((900, 700), Image.Resampling.LANCZOS)
                buf = io.BytesIO()
                thumb.save(buf, 'PNG')
            return {
                'image': buf.getvalue(), 'size': result.size, 'source_size': result.source_size,
                'bytes': len(result.data), 'source_bytes': len(data), 'notes': result.notes, 'dpi': result.dpi,
            }

        self.preview_job = self.launch(work, 'preview')

    def _begin_batch_ui(self, batch_items, status_msg: str):
        self.batch_progress = BatchProgress(batch_items)
        self.timer.stop()
        self.preview_cancel.set()
        self.preview_job = None
        self.cancel.clear()
        self.result_folders = []
        self.log.clear()
        self.progress.setValue(0)
        self.set_busy(True)
        self.status.setText(status_msg)
        self.current_image.setText('현재 이미지: 준비 중…')
        self.render_batch_progress()

    def _resolve_current_doc_selected_keys(self, path: Path) -> set[str]:
        """Resolve target image keys in the current document (checked items, or highlighted rows if none checked)."""
        key = self.mode_key(path)
        checked = set(self.checked_keys.get(key, set()))
        if checked:
            return checked
        sel_rows = self.tree.selectedItems()
        if sel_rows:
            return {r.data(0, Qt.ItemDataRole.UserRole).key for r in sel_rows if r.data(0, Qt.ItemDataRole.UserRole) is not None}
        cur = self.tree.currentItem()
        if cur is not None and cur.data(0, Qt.ItemDataRole.UserRole) is not None:
            return {cur.data(0, Qt.ItemDataRole.UserRole).key}
        return set()

    def extract_current_image(self):
        if self.busy:
            return
        row, path = self.tree.currentItem(), self.current_path()
        if row is None or path is None:
            QMessageBox.information(self, '이미지 선택', '미리보기에서 추출할 이미지를 먼저 선택하세요.')
            return
        if not self.destination.text().strip():
            self.destination.setText(str(path.parent))
        settings = self.settings()
        try:
            settings.validate()
        except ValueError as exc:
            QMessageBox.warning(self, '설정 확인', str(exc))
            return
        item, cat = row.data(0, Qt.ItemDataRole.UserRole), self.catalogs.get(self.mode_key(path))
        destination = Path(self.destination.text().strip()).expanduser()
        self.work_mode = 'extract'
        self._begin_batch_ui([(path, 1)], '현재 미리보기 이미지 1개 추출 중…')
        if self.preview_dialog is not None:
            self.preview_dialog.single_status.setText('현재 이미지를 추출하고 있습니다…')

        def work(emit):
            emit({'type': 'document', 'name': path.name, 'index': 0, 'count': 1})
            notify = lambda ev: (ev.update({'document': 0, 'documents': 1}), emit(ev))
            try:
                result = extract_images(path, destination, settings, notify, self.cancel, {item.key}, cat)
                emit({'type': 'document_end', 'document': 0, 'result': result})
                emit({'type': 'folder', 'folder': result['folder']})
                return {'results': [result], 'broken': 0, 'cancelled': self.cancel.is_set(), 'single_item': item.name}
            except Cancelled:
                return {'results': [], 'broken': 0, 'cancelled': True}
            except Exception as exc:
                emit({'type': 'document_end', 'document': 0, 'error': f'{path.name}: {exc}'})
                return {'results': [], 'broken': 1, 'cancelled': False}

        self.launch(work, 'done')

    def extract_selected_in_current_document(self):
        """Convert & extract ONLY the selected/checked images of the currently previewed document."""
        if self.busy:
            return
        path = self.current_path()
        if path is None:
            self.start_work()
            return
        if not self.destination.text().strip():
            self.destination.setText(str(path.parent))
        settings = self.settings()
        try:
            settings.validate()
        except ValueError as exc:
            QMessageBox.warning(self, '설정 확인', str(exc))
            return
        if self.pending_scans:
            self.status.setText('이미지 목록이 완성된 뒤 추출하세요.')
            return
        cat = self.catalogs.get(self.mode_key(path))
        target_keys = self._resolve_current_doc_selected_keys(path)
        if not target_keys:
            QMessageBox.information(self, '이미지 선택', '현재 문서에서 변환·추출할 이미지를 체크하거나 선택하세요.')
            return
        destination = Path(self.destination.text().strip()).expanduser()
        self.work_mode = 'extract'
        self._begin_batch_ui([(path, len(target_keys))], f"현재 문서의 선택 이미지 {len(target_keys):,}개 변환 추출 중…")
        if self.preview_dialog is not None:
            self.preview_dialog.single_status.setText(f"현재 문서에서 선택된 이미지 {len(target_keys):,}개를 변환 추출하고 있습니다…")

        def work(emit):
            emit({'type': 'document', 'name': path.name, 'index': 0, 'count': 1})
            notify = lambda ev: (ev.update({'document': 0, 'documents': 1}), emit(ev))
            try:
                result = extract_images(path, destination, settings, notify, self.cancel, target_keys, cat)
                emit({'type': 'document_end', 'document': 0, 'result': result})
                emit({'type': 'folder', 'folder': result['folder']})
                return {
                    'results': [result],
                    'broken': 0,
                    'cancelled': self.cancel.is_set(),
                    'selected_doc_name': path.name,
                    'selected_count': len(target_keys),
                }
            except Cancelled:
                return {'results': [], 'broken': 0, 'cancelled': True}
            except Exception as exc:
                emit({'type': 'document_end', 'document': 0, 'error': f'{path.name}: {exc}'})
                return {'results': [], 'broken': 1, 'cancelled': False}

        self.launch(work, 'done')

    def optimize_selected_in_current_document(self):
        """Convert ONLY the selected/checked images inside the previewed document."""
        if self.busy:
            return
        if self.pending_scans:
            self.status.setText('이미지 목록이 완성된 뒤 변환하세요.')
            return
        path = self.current_path()
        if path is None:
            self.start_optimize_work()
            return
        if path.suffix.lower() not in OPTIMIZABLE:
            QMessageBox.information(self, '문서 내 변환 안내', '문서 내 직접 이미지 변환은 HWPX, PDF, XLSX, DOCX, PPTX 문서에서 지원합니다.')
            return
        if not self.destination.text().strip():
            self.destination.setText(str(path.parent))
        settings = replace(self.settings(), apply_document_crop=False)
        if settings.format == 'ORIGINAL':
            settings = replace(settings, format='JPEG')
        try:
            settings.validate()
        except ValueError as exc:
            QMessageBox.warning(self, '설정 확인', str(exc))
            return
        if self.pending_scans:
            self.status.setText('이미지 목록이 완성된 뒤 변환하세요.')
            return
        cat = self.catalogs.get(self.mode_key(path))
        target_keys = self._resolve_current_doc_selected_keys(path)
        if not target_keys:
            QMessageBox.information(self, '선택 이미지 변환', '미리보기 목록(LIST)에서 변환할 이미지(예: PNG·BMP)를 먼저 체크하거나 선택하세요.')
            return
        dedup = len({i.member for i in cat.items if i.key in target_keys}) if cat else len(target_keys)
        destination = Path(self.destination.text().strip()).expanduser()
        self.work_mode = 'optimize'
        self._begin_batch_ui([(path, dedup)], f"현재 문서의 선택 이미지 {dedup:,}개 문서 내 변환 중…")
        if self.preview_dialog is not None:
            self.preview_dialog.single_status.setText(f"현재 문서에서 선택된 이미지 {dedup:,}개만 {settings.format} 형식으로 문서 내 변환하고 있습니다…")

        def work(emit):
            emit({'type': 'document', 'name': path.name, 'index': 0, 'count': 1})
            notify = lambda ev: (ev.update({'document': 0, 'documents': 1}), emit(ev))
            try:
                res = optimize_document(path, destination, settings, notify, self.cancel, target_keys, cat)
                emit({'type': 'document_end', 'document': 0, 'source': str(path), 'result': res})
                emit({'type': 'folder', 'folder': res['folder']})
                return {
                    'mode': 'optimize',
                    'results': [res],
                    'broken': 0,
                    'cancelled': self.cancel.is_set(),
                    'selected_doc_name': path.name,
                    'selected_count': dedup,
                }
            except Cancelled:
                return {'mode': 'optimize', 'results': [], 'broken': 0, 'cancelled': True}
            except Exception as exc:
                emit({'type': 'document_end', 'document': 0, 'source': str(path), 'error': f'{path.name}: {exc}'})
                return {'mode': 'optimize', 'results': [], 'broken': 1, 'cancelled': False}

        self.launch(work, 'done')

    def start_work(self):
        if self.busy:
            return
        if not self.files or not self.destination.text().strip():
            QMessageBox.information(self, '파일과 폴더 선택', '문서와 저장 폴더를 선택하세요.')
            return
        settings = self.settings()
        try:
            settings.validate()
        except ValueError as exc:
            QMessageBox.warning(self, '설정 확인', str(exc))
            return
        if self.pending_scans:
            self.status.setText('이미지 목록이 완성된 뒤 추출하세요.')
            return
        snapshots = [
            (p, self.catalogs.get(self.mode_key(p)), set(self.checked_keys.get(self.mode_key(p), set())))
            for p in self.files
            if self.checked_keys.get(self.mode_key(p)) or self.mode_key(p) in self.catalog_errors
        ]
        if not snapshots:
            QMessageBox.information(self, '이미지 선택', '변환·추출할 이미지를 선택하세요. (좌측 [이미지 선택] 필터 또는 [미리보기] 창에서 선택)')
            return
        destination = Path(self.destination.text().strip()).expanduser()
        self.work_mode = 'extract'
        self._begin_batch_ui([(p, len(keys) if cat else None) for p, cat, keys in snapshots], '선택된 이미지 변환 추출 준비 중…')

        def work(emit):
            results, broken = [], 0
            for index, (path, cat, keys) in enumerate(snapshots):
                if self.cancel.is_set():
                    break
                emit({'type': 'document', 'name': path.name, 'index': index, 'count': len(snapshots)})
                notify = lambda ev, idx=index: (ev.update({'document': idx, 'documents': len(snapshots)}), emit(ev))
                try:
                    res = extract_images(path, destination, settings, notify, self.cancel, keys if cat else None, cat)
                    results.append(res)
                    emit({'type': 'document_end', 'document': index, 'result': res})
                    emit({'type': 'folder', 'folder': res['folder']})
                except Cancelled:
                    break
                except Exception as exc:
                    logging.getLogger('sunrise_image.workflow').exception('Document workflow failed')
                    broken += 1
                    emit({'type': 'document_end', 'document': index, 'error': f'{path.name}: {exc}'})
            return {'results': results, 'broken': broken, 'cancelled': self.cancel.is_set()}

        self.launch(work, 'done')

    def start_optimize_work(self):
        if self.busy:
            return
        if self.pending_scans:
            self.status.setText('이미지 목록이 완성된 뒤 변환하세요.')
            return
        if not self.files or not self.destination.text().strip():
            QMessageBox.information(self, '파일과 폴더 선택', '문서와 저장 폴더를 선택하세요.')
            return
        settings = replace(self.settings(), apply_document_crop=False)
        if settings.format == 'ORIGINAL':
            settings = replace(settings, format='JPEG')
        try:
            settings.validate()
        except ValueError as exc:
            QMessageBox.warning(self, '설정 확인', str(exc))
            return
        snapshots = []
        for path in self.files:
            if path.suffix.lower() not in OPTIMIZABLE:
                continue
            key = self.mode_key(path)
            cat = self.catalogs.get(key)
            if cat is None and key not in self.catalog_errors:
                self.queue_scan()
                self.status.setText('이미지 목록이 완성된 뒤 변환하세요.')
                return
            else:
                keys = set(self.checked_keys.get(key, set()))
                if keys or key in self.catalog_errors:
                    dedup = len({i.member for i in cat.items if i.key in keys}) if cat else None
                    snapshots.append((path, cat, keys, dedup))
        if not snapshots:
            QMessageBox.information(self, '선택 이미지 문서 내 변환', '변환할 이미지가 선택된 한글(HWPX), PDF, 또는 Office(XLSX, DOCX, PPTX) 문서를 선택하세요.')
            return
        destination = Path(self.destination.text().strip()).expanduser()
        self.work_mode = 'optimize'
        self._begin_batch_ui([(p, dedup) for p, _, _, dedup in snapshots], '선택된 이미지 문서 내 변환·경량화 준비 중…')

        def work(emit):
            results, broken = [], 0
            for index, (path, cat, keys, _) in enumerate(snapshots):
                if self.cancel.is_set():
                    break
                emit({'type': 'document', 'name': path.name, 'index': index, 'count': len(snapshots)})
                notify = lambda ev, idx=index: (ev.update({'document': idx, 'documents': len(snapshots)}), emit(ev))
                try:
                    res = optimize_document(path, destination, settings, notify, self.cancel, keys if cat else None, cat)
                    results.append(res)
                    emit({'type': 'document_end', 'document': index, 'source': str(path), 'result': res})
                    emit({'type': 'folder', 'folder': res['folder']})
                except Cancelled:
                    break
                except Exception as exc:
                    logging.getLogger('sunrise_image.workflow').exception('Document workflow failed')
                    broken += 1
                    emit({'type': 'document_end', 'document': index, 'source': str(path), 'error': f'{path.name}: {exc}'})
            return {'mode': 'optimize', 'results': results, 'broken': broken, 'cancelled': self.cancel.is_set()}

        self.launch(work, 'done')

    def cancel_work(self):
        self.cancel.set()
        self.stop.setEnabled(False)
        self.status.setText('현재 처리 단계가 끝나면 중지합니다…')

    def open_folder(self):
        if self.result_folders:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.result_folders[-1]))

    @Slot(object)
    def on_event(self, packet):
        job, kind = packet['job'], packet['kind']
        if kind != 'progress':
            self.jobs.pop(job, None)
        if kind == 'inputs':
            self.set_busy(False)
            if self.closing:
                return
            if 'error' in packet:
                if not self.cancel.is_set():
                    QMessageBox.warning(self, '폴더 읽기 실패', packet['error'])
                else:
                    self.status.setText('폴더 검색을 중지했습니다.')
            else:
                self._add_candidates(*packet['value'])
            return
        if kind == 'scan_done':
            return
        if kind == 'preview':
            if job != self.preview_job:
                return
            if 'error' in packet:
                self.preview_pixmap = None
                self.image.clear()
                self.image.setText('미리보기 불가')
                self.preview_info.setText(packet['error'])
                if self.preview_dialog is not None:
                    self.preview_dialog.update_preview_content(None, packet['error'], error_text='미리보기 불가')
                return
            res = packet['value']
            self.preview_pixmap = QPixmap()
            self.preview_pixmap.loadFromData(res['image'])
            self.refresh_pixmap()
            size, dpi, src_b, out_b = res['size'], res['dpi'], res['source_bytes'], res['bytes']
            diff_tag = f" ({((out_b - src_b) / src_b * 100):+.1f}%)" if src_b > 0 else ""
            info_text = (
                f"원본 {res['source_size'][0]} × {res['source_size'][1]} px / {format_size(src_b)}\n"
                f"결과 {size[0]} × {size[1]} px / {format_size(out_b)}{diff_tag}"
                + (f" / {dpi[0]:g} DPI" if dpi else '')
                + ('\n' + '; '.join(res['notes']) if res['notes'] else '')
            )
            self.preview_info.setText(info_text)
            if self.preview_dialog is not None:
                self.preview_dialog.update_preview_content(self.preview_pixmap, info_text)
            return

        if kind == 'progress':
            val = packet['value']
            typ = val['type']
            if typ == 'catalog':
                if val['generation'] != self.scan_generation or Path(val['source']) not in self.files:
                    return
                key = (val['source'], val['mode'])
                self.pending_scans.discard(key)
                if val['error']:
                    self.catalog_errors[key] = val['error']
                else:
                    self.catalogs[key] = val['catalog']
                    default_keys = self._filter_keys_for_catalog(
                        val['catalog'],
                        self.active_image_filter if self.active_image_filter != 'custom' else 'all',
                    )
                    if key in self.checked_keys:
                        self.checked_keys[key].intersection_update(i.key for i in val['catalog'].items)
                    else:
                        self.checked_keys[key] = default_keys
                if self.current_path() and key == self.mode_key(self.current_path()):
                    self.scan(self.file_list.currentRow())
                self.refresh_selection_status()
            elif typ == 'document':
                self.log.append(f"<b>{html.escape(val['name'])}</b>")
                self.batch_progress.start(val['index'])
                self.render_batch_progress()
                path = Path(self.batch_progress.current.path)
                if path in self.files:
                    self.file_list.setCurrentRow(self.files.index(path))
                    self.file_list.scrollToItem(self.file_list.currentItem())
            elif typ == 'begin':
                self.batch_progress.begin(val['document'], val['total'])
                self.render_batch_progress()
                if val['total'] == 0:
                    self.log.append('추출 대상으로 선택한 이미지가 없습니다.')
            elif typ == 'item_start':
                self.batch_progress.item_start(val['document'], val['index'], val['member'])
                self.render_batch_progress()
            elif typ == 'item':
                row = val['row']
                self.log.append(html.escape(f"[{row['상태']}] {row['저장 파일'] or row['내부 파일']} · {row.get('비고', '')}"))
                self.batch_progress.item_done(val['document'], val['index'], row['상태'], val.get('_counts'))
                self.render_batch_progress()
            elif typ == 'document_end':
                res = val.get('result')
                self.batch_progress.end(val['document'], res, error='error' in val)
                if 'error' in val:
                    self.log.append(html.escape(val['error']))
                elif res and res.get('mode') == 'optimize' and res.get('output_file'):
                    src_b, out_b = res.get('source_doc_bytes', 0), res.get('output_doc_bytes', 0)
                    src_key = val.get('source') or (self.batch_progress.documents[val['document']].path if val['document'] < len(self.batch_progress.documents) else '')
                    if src_key:
                        self.optimized_results[str(src_key)] = (src_b, out_b)
                    pct = ((out_b - src_b) / src_b * 100) if src_b > 0 else 0.0
                    self.log.append(html.escape(f"경량화 문서 생성: {Path(res['output_file']).name} ({format_size(src_b)} → {format_size(out_b)}, {pct:+.1f}%)"))
                self.render_batch_progress()
            elif typ == 'phase':
                self.current_image.setText(val['message'])
                self.status.setText(val['message'])
            elif typ == 'folder':
                self.result_folders.append(val['folder'])
                self.log.append(html.escape(f"결과 폴더: {val['folder']}"))
            elif typ in {'error', 'warning'}:
                self.log.append(html.escape(val['message']))
            return

        if kind == 'done':
            self.set_busy(False)
            if 'error' in packet:
                self.batch_progress.finish(cancelled=True)
                self.render_batch_progress()
                self.status.setText('처리 실패')
                QMessageBox.warning(self, '처리 실패', packet['error'])
                return
            val = packet['value']
            results = val['results']
            self.batch_progress.finish(val['cancelled'])
            self.render_batch_progress()
            saved, failed, warned = self.batch_progress.saved, self.batch_progress.failed, self.batch_progress.warned
            state = ('중지됨' if val['cancelled'] else
                     ('일부 완료' if saved else '실패') if failed or val['broken'] else '완료')
            if val.get('mode') == 'optimize':
                src_b = sum(r.get('source_doc_bytes', 0) for r in results)
                out_b = sum(r.get('output_doc_bytes', 0) for r in results)
                summary = f"문서 경량화 {state} · 변환 {saved}개 ({format_size(src_b)} → {format_size(out_b)}) / 주의 {warned}개 / 실패 {failed}개 / 문서 실패 {val['broken']}개"
            else:
                summary = f"{state} · 저장 {saved}개 / 주의 {warned}개 / 항목 실패 {failed}개 / 문서 실패 {val['broken']}개"
            self.status.setText(summary)
            self.log.append(summary)
            duration_label = "문서 경량화 소요 시간" if val.get("mode") == "optimize" else "이미지 추출 소요 시간"
            self.log.append(f"{duration_label}: {sum(r.get('elapsed_seconds', 0) for r in results):.2f}초")
            self.log.append('완성된 경량화 문서와 추출결과.csv를 확인하세요. 저장 전 중지된 문서는 생성되지 않습니다.' if val.get('mode') == 'optimize' else '저장된 이미지와 추출결과.csv를 확인하세요. 중지한 경우 이미 저장한 결과는 유지됩니다.')
            if self.preview_dialog is not None:
                self.preview_dialog.sync_from_main()
                if val.get('single_item') and saved > 0:
                    self.preview_dialog.single_status.setText(f"✓ '{val['single_item']}' 단일 추출 완료 (저장 {saved}개)")
                elif val.get('selected_doc_name') and saved > 0:
                    if val.get('mode') == 'optimize':
                        src_b = sum(r.get('source_doc_bytes', 0) for r in results)
                        out_b = sum(r.get('output_doc_bytes', 0) for r in results)
                        self.preview_dialog.single_status.setText(
                            f"✓ '{val['selected_doc_name']}' 선택 이미지 {saved:,}개 문서 내 변환 완료 ({format_size(src_b)} → {format_size(out_b)})"
                        )
                    else:
                        self.preview_dialog.single_status.setText(
                            f"✓ '{val['selected_doc_name']}' 선택 이미지 {saved:,}개 변환 추출 완료"
                        )
            self.request_preview()

    def refresh_pixmap(self):
        if self.preview_pixmap and not self.preview_pixmap.isNull():
            self.image.setPixmap(self.preview_pixmap.scaled(self.image.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        if self.preview_dialog is not None:
            self.preview_dialog.refresh_pixmap()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'image'):
            self.refresh_pixmap()

    def reset_settings(self):
        if self.busy:
            return
        for cb in (self.format, self.target_unit, self.alpha, self.rotate, self.naming_mode, self.resize_mode):
            cb.setCurrentIndex(0)
        for sp, val in [(self.percent, 100), (self.width, 1920), (self.height, 1080), (self.dpi, 300), (self.quality, 95), (self.png, 6), (self.target, 500)]:
            sp.setValue(val)
        for ck in (self.gray, self.upscale, self.change_dpi, self.lossless, self.use_target, self.shrink, self.crop):
            ck.setChecked(False)
        self.apply_global_image_filter('all')
        self.sync()
        self.request_preview()

    def set_busy(self, busy):
        self.busy = busy
        for w in (
            self.add, self.add_folder_btn, self.remove, self.clear_files_btn, self.destination,
            self.folder, self.open_dest_btn, self.format, self.naming_mode, self.tree, self.search,
            self.check_all, self.check_none, self.invert_btn, self.popup_preview_btn, self.selection_tools,
            self.refresh, self.preview_mode, self.prev_item_btn, self.next_item_btn, self.extract_single_btn,
            self.reset, self.preview_button, self.optimize_btn, self.start, *self.preset_buttons,
        ):
            w.setEnabled(not busy)
        if hasattr(self, 'target_scope_combo'):
            self.target_scope_combo.setEnabled(not busy)
            self.open_list_select_btn.setEnabled(not busy and bool(self.files))
        if hasattr(self, 'main_filter_buttons'):
            for b in (*self.main_filter_buttons.values(), self.main_open_select_btn):
                b.setEnabled(not busy)
        self.open_result.setEnabled(not busy and bool(self.result_folders))
        self.stop.setEnabled(busy)
        self.sync()

    def closeEvent(self, event):
        self.closing = True
        self.timer.stop()
        self.scan_cancel.set()
        self.preview_cancel.set()
        if self.preview_dialog is not None:
            self.preview_dialog.hide()
        if self.busy or self.pool.activeThreadCount():
            self.cancel.set()
            self.setEnabled(False)
            self.status.setText('현재 작업을 마친 뒤 창을 닫습니다…')
            event.ignore()
            QTimer.singleShot(50, self._finish_close)
            return
        event.accept()

    def _finish_close(self):
        if self.busy or self.pool.activeThreadCount():
            QTimer.singleShot(50, self._finish_close)
            return
        self.close()


def main():
    if '--startup-smoke' in sys.argv:
        import argparse
        from runtime_check import run_startup
        parser = argparse.ArgumentParser()
        parser.add_argument('--startup-smoke', action='store_true')
        parser.add_argument('--report', required=True)
        args = parser.parse_args()
        sys.exit(run_startup(args.report))
    if '--smoke-test' in sys.argv:
        import argparse
        from runtime_check import run
        parser = argparse.ArgumentParser()
        parser.add_argument('--smoke-test', action='store_true')
        parser.add_argument('--report')
        args = parser.parse_args()
        sys.exit(run(args.report))
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    app.setFont(QFont('Malgun Gothic', 10))
    window = Window()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()