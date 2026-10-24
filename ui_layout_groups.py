"""Sunrise Image — Layout-Grouped UI Builders (SRP, Unified Grid Alignment & Space Efficiency).

Separates UI construction by visual layout group and enforces unified column axes
across Cards 02, 03, and 04 so all dropdowns, spinboxes, and inputs align cleanly
with maximum space efficiency.
"""
from __future__ import annotations
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QListWidget, QMenu, QProgressBar, QSizePolicy, QSplitter,
    QTabWidget, QTextEdit, QToolButton, QTreeWidget, QVBoxLayout, QWidget,
)
from ui_theme import brand_logo_pixmap, _palette
from ui_widgets import (
    ElidedLabel, PreviewLabel, SmartComboBox, card, hbox, label, make_btn,
    make_combo, spin,
)

LEFT_LABEL_W = 92
RIGHT_LABEL_W = 72


# ============================================================================
# GROUP 1: Top Studio Header & Preset Bar (#headerCard)
# ============================================================================
def build_header_group(win, presets) -> QFrame:
    header_card = QFrame()
    header_card.setObjectName("headerCard")
    vbox = QVBoxLayout(header_card)
    vbox.setContentsMargins(14, 6, 14, 6)
    vbox.setSpacing(4)

    sun_dot = QLabel()
    sun_dot.setObjectName("brandMark")
    sun_dot.setPixmap(brand_logo_pixmap(24))
    sun_dot.setFixedSize(24, 24)

    win.theme_button = make_btn("다크 테마", win.toggle_theme, obj="themeButton", tip="라이트 / 다크 스튜디오 테마를 전환합니다.")
    win.badge = label("Document / Image", "badge", wrap=False)
    win.badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
    win.badge.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    win.badge.setMinimumWidth(win.badge.fontMetrics().horizontalAdvance("Document / Image") + 24)

    top_row = hbox(
        sun_dot,
        label("Sunrise Image", "title", wrap=False),
        label("  ·  문서 이미지 선별 추출 · 한글 본문 자르기 · 문서 내 직접 경량화", "headerSub", wrap=False),
        1,
        win.theme_button,
        win.badge,
        spacing=8,
    )
    vbox.addLayout(top_row)

    preset_bar = hbox(label("빠른 프리셋", "presetCaption", wrap=False), spacing=6)
    win.preset_buttons, win.preset_map = [], {}
    for text, key, tip in presets:
        btn = make_btn(text, lambda _=False, k=key: win.apply_preset(k), obj="presetButton", tip=tip)
        btn.setProperty("activePreset", key == "report_jpg")
        preset_bar.addWidget(btn)
        win.preset_buttons.append(btn)
        win.preset_map[key] = btn
    preset_bar.addStretch(1)
    vbox.addLayout(preset_bar)

    accent = QFrame()
    accent.setFixedHeight(2)
    accent.setObjectName("sunriseBar")
    vbox.addWidget(accent)
    return header_card


# ============================================================================
# GROUP 2: Left Panel — 01 Document List & Quick Image Filter (#docListCard)
# ============================================================================
def build_document_list_group(win) -> QSplitter:
    win.documents_split = QSplitter(Qt.Orientation.Vertical)
    win.documents_split.setHandleWidth(0)
    win.documents_split.setObjectName("documentsSplit")
    win.documents_split.setChildrenCollapsible(False)
    win.documents_split.setFixedWidth(420)

    win.doc_count_badge = label("문서 0개", "pillBadgeCoral", wrap=False)
    source, sl = card("01  문서 목록", win.doc_count_badge, step_ObjectName="stepCoral", card_id="docListCard")
    source.setMinimumHeight(180)
    win.documents_split.addWidget(source)

    win.add = make_btn("+ 문서 추가", win.choose_files, obj="accentSubtleButton", tip="지원 문서(HWPX, PDF, DOCX, XLSX, PPTX)를 추가합니다.")
    win.add_folder_btn = make_btn("+ 폴더 추가", win.choose_input_folder, obj="accentSubtleButton", tip="폴더(하위 폴더 포함) 안의 지원 문서를 한 번에 추가합니다.")
    win.remove = make_btn("선택 제거", win.remove_files, tip="목록에서 선택한 문서를 제거합니다 (Delete).")
    win.clear_files_btn = make_btn("전체 비우기", win.clear_files, tip="등록된 모든 문서를 비웁니다.")
    sl.addLayout(hbox((win.add, 1), (win.add_folder_btn, 1), spacing=6))
    sl.addLayout(hbox((win.remove, 1), (win.clear_files_btn, 1), spacing=6))

    win.main_filter_all_btn = make_btn(
        "전체",
        lambda: win.apply_global_image_filter("all"),
        obj="filterChipButton",
        tip="모든 문서의 전체 이미지를 변환·추출 대상으로 선택합니다.",
    )
    win.main_filter_all_btn.setProperty("activeFilter", True)
    win.main_filter_lossless_btn = make_btn(
        "PNG·BMP만",
        lambda: win.apply_global_image_filter("lossless_only"),
        obj="filterChipButton",
        tip="미리보기 창을 열지 않고 메인 창에서 바로 PNG·BMP·TIFF 무손실 이미지만 골라 변환·추출 대상으로 선택합니다.",
    )
    win.main_filter_1mb_btn = make_btn(
        "1MB↑",
        lambda: win.apply_global_image_filter("over_1mb"),
        obj="filterChipButton",
        tip="모든 문서에서 1MB 이상인 대용량 이미지만 골라 변환·추출 대상으로 선택합니다.",
    )
    win.main_filter_500kb_btn = make_btn(
        "500KB↑",
        lambda: win.apply_global_image_filter("over_500kb"),
        obj="filterChipButton",
        tip="모든 문서에서 500KB 이상인 이미지만 골라 변환·추출 대상으로 선택합니다.",
    )
    win.main_open_select_btn = make_btn(
        "개별선택",
        lambda: win.open_document_preview(),
        obj="docPreviewButton",
        tip="선택한 문서의 이미지 목록(LIST)·미리보기 창을 열어 원하는 이미지만 개별 체크합니다.",
    )
    win.main_filter_buttons = {
        "all": win.main_filter_all_btn,
        "lossless_only": win.main_filter_lossless_btn,
        "over_1mb": win.main_filter_1mb_btn,
        "over_500kb": win.main_filter_500kb_btn,
    }
    sl.addLayout(hbox(
        label("이미지 선택:", "fieldLabel", wrap=False),
        win.main_filter_all_btn,
        win.main_filter_lossless_btn,
        win.main_filter_1mb_btn,
        win.main_filter_500kb_btn,
        1,
        win.main_open_select_btn,
        spacing=4,
    ))

    win.doc_table = QTreeWidget()
    win.doc_table.setObjectName("docTable")
    win.doc_table.setRootIsDecorated(False)
    win.doc_table.setIndentation(0)
    win.doc_table.setAlternatingRowColors(True)
    win.doc_table.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
    win.doc_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    win.doc_table.setHeaderLabels(["문서명", "이미지 · 용량", "비고"])
    if win.doc_table.headerItem() is not None:
        for c in range(3):
            win.doc_table.headerItem().setTextAlignment(c, Qt.AlignmentFlag.AlignCenter)
    hdr = win.doc_table.header()
    hdr.setStretchLastSection(False)
    hdr.setMinimumSectionSize(max(win.doc_table.fontMetrics().horizontalAdvance(h) for h in ['문서명', '이미지 · 용량', '비고']) + 16)
    hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
    hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
    hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
    win.doc_table.setColumnWidth(1, 130)
    win.doc_table.setColumnWidth(2, 72)
    win.doc_table.setToolTip("문서나 폴더를 끌어 놓아 추가할 수 있습니다. 상단 [이미지 선택] 필터로 대상을 고르거나 [미리보기] 버튼으로 개별 이미지를 선택하세요.")
    win.doc_table.currentItemChanged.connect(win._on_doc_table_current_changed)
    win.doc_table.itemClicked.connect(win._on_doc_table_clicked)
    win.doc_table.itemDoubleClicked.connect(win._on_doc_table_double_clicked)
    sl.addWidget(win.doc_table, 1)

    win.file_list = QListWidget()
    win.file_list.setMinimumHeight(76)
    win.file_list.setTextElideMode(Qt.TextElideMode.ElideMiddle)
    win.file_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    win.file_list.setUniformItemSizes(True)
    win.file_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
    win.file_list.currentRowChanged.connect(win._on_file_list_row_changed)
    win.file_list.hide()
    sl.addWidget(win.file_list)
    sl.addWidget(label("상단 [PNG·BMP만 · 1MB↑] 또는 [미리보기]로 원하는 이미지만 선별 변환", "muted", wrap=False))

    win.delete_doc_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Delete), win)
    win.delete_doc_shortcut.activated.connect(win.remove_files)
    return win.documents_split


# ============================================================================
# GROUP 3: Collection Shared Widgets & 5-Column Image Check-Tree (#imageTree)
# ============================================================================
def build_collection_shared_group(win):
    win.selection_badge = label("체크 0 / 0개", "pillBadge", wrap=False)
    win.collection_tabs = QTabWidget()
    win.collection_tabs.setObjectName("collectionTabs")
    win.collection_tabs.addTab(QWidget(), "이미지 목록")
    win.collection_tabs.addTab(QWidget(), "미리보기 / 원본 비교")
    win.collection_tabs.hide()

    win.search = QLineEdit()
    win.search.setPlaceholderText("이름 · 위치 · 형식으로 찾기 (Ctrl+F)")
    win.search.setClearButtonEnabled(True)
    win.search.textChanged.connect(win.filter_items)
    win.find_shortcut = QShortcut(QKeySequence("Ctrl+F"), win)
    win.find_shortcut.activated.connect(win.focus_search)

    win.refresh = make_btn("새로고침", win.refresh_catalogs, tip="문서를 다시 읽어 이미지 목록을 갱신합니다.")
    win.check_all = make_btn("전체 선택", lambda: win.change_checks(True, visible_only=False))
    win.check_none = make_btn("전체 취소", lambda: win.change_checks(False, visible_only=False))
    win.invert_btn = make_btn("선택 반전", win.invert_checks)
    win.popup_preview_btn = make_btn("팝업 미리보기", win.open_preview, obj="accentSubtleButton")

    win.selection_tools = QToolButton()
    win.selection_tools.setText("선택 관리 ▾")
    win.selection_tools.setMinimumWidth(94)
    win.selection_tools.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
    menu = QMenu(win.selection_tools)
    for text, chk, scope in [
        ("검색 결과 선택", True, "visible"),
        ("검색 결과 취소", False, "visible"),
        ("선택한 행 체크", True, "rows"),
        ("선택한 행 체크 취소", False, "rows"),
    ]:
        menu.addAction(text).triggered.connect(lambda _=False, c=chk, sc=scope: win.change_scope_checks(c, sc))
    menu.addAction("현재 문서 선택 반전").triggered.connect(win.invert_checks)
    menu.addSeparator()
    for text, scope in [
        ("대용량 (100 KB 이상)만 선택", "over_100kb"),
        ("고용량 (500 KB 이상)만 선택", "over_500kb"),
        ("초고용량 (1 MB 이상)만 선택", "over_1mb"),
        ("PNG · BMP 무손실 형식만 선택", "lossless_only"),
    ]:
        menu.addAction(text).triggered.connect(lambda _=False, sc=scope: win.change_scope_checks(True, sc))
    menu.addSeparator()
    for text, scope in [
        ("모든 문서에서 PNG · BMP만 선택", "all_docs_lossless"),
        ("모든 문서에서 1 MB 이상만 선택", "all_docs_over_1mb"),
    ]:
        menu.addAction(text).triggered.connect(lambda _=False, sc=scope: win.change_scope_checks(True, sc))
    menu.addSeparator()
    for text, chk in [("모든 문서 전체 선택", True), ("모든 문서 전체 취소", False)]:
        menu.addAction(text).triggered.connect(lambda _=False, c=chk: win.change_scope_checks(c, "documents"))
    win.selection_tools.setMenu(menu)

    win.tree = QTreeWidget()
    win.tree.setObjectName("imageTree")
    win.tree.setRootIsDecorated(False)
    win.tree.setIndentation(0)
    win.tree.setAlternatingRowColors(True)
    win.tree.setUniformRowHeights(True)
    win.tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
    win.tree.setHeaderLabels(["선택 / 이미지", "형식", "원본 용량", "해상도 px", "자르기 / 위치"])
    if win.tree.headerItem() is not None:
        for c in range(5):
            win.tree.headerItem().setTextAlignment(c, Qt.AlignmentFlag.AlignCenter)
    win.tree.setMinimumHeight(180)
    thdr = win.tree.header()
    thdr.setStretchLastSection(False)
    thdr.setMinimumSectionSize(max(win.tree.fontMetrics().horizontalAdvance(h) for h in ['형식', '원본 용량', '해상도 px', '자르기 / 위치']) + 16)
    thdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
    for col, w in [(1, 56), (2, 82), (3, 102), (4, 106)]:
        thdr.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        win.tree.setColumnWidth(col, w)
    win.tree.itemChanged.connect(win.item_checked)
    win.tree.currentItemChanged.connect(win.request_preview)
    win.tree.itemDoubleClicked.connect(win.open_preview)

    win.selection_info = label("문서를 추가하면 내장 이미지 전체 목록을 표시합니다.", "muted")
    win.back_to_list = make_btn("← 목록", win.return_to_list, obj="backButton")
    win.prev_item_btn = make_btn("◀", lambda: win.step_preview_item(-1), tip="이전 이미지 보기")
    win.next_item_btn = make_btn("▶", lambda: win.step_preview_item(1), tip="다음 이미지 보기")
    win.preview_mode = make_combo(["변환 결과", "원본 비교"], win.request_preview, obj="previewModeCombo")
    win.preview_button = make_btn("갱신", win.preview, tip="현재 설정으로 미리보기를 다시 렌더링합니다.")
    win.extract_single_btn = make_btn("이 이미지만 추출", win.extract_current_image, obj="singleExtractButton")

    win.image = PreviewLabel("목록에서 이미지를 선택하세요.")
    win.image.setAlignment(Qt.AlignmentFlag.AlignCenter)
    win.image.setObjectName("preview")
    win.image.setMinimumSize(180, 120)
    win.image.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
    win.image.resized.connect(win.refresh_pixmap)
    win.preview_info = label("목록에서 이미지를 선택하면 해상도·용량과 변환 결과를 비교합니다.", "previewMeta")
    win.return_shortcut = QShortcut(QKeySequence("Esc"), win)
    win.return_shortcut.activated.connect(win.return_to_list)


def _configure_unified_4col_grid(grid: QGridLayout):
    """Enforce identical label & input column axes across Cards 02, 03, and 04."""
    grid.setContentsMargins(0, 0, 0, 0)
    grid.setHorizontalSpacing(8)
    grid.setVerticalSpacing(5)
    grid.setColumnMinimumWidth(0, LEFT_LABEL_W)
    grid.setColumnMinimumWidth(2, RIGHT_LABEL_W)
    grid.setColumnStretch(1, 1)
    grid.setColumnStretch(3, 1)


# ============================================================================
# GROUP 4: Right Panel — 02 Format & Target Scope Settings (#formatCard)
# ============================================================================
def build_format_settings_group(win) -> QFrame:
    scope_header = QWidget()
    scope_lay = QHBoxLayout(scope_header)
    scope_lay.setContentsMargins(0, 0, 0, 0)
    scope_lay.setSpacing(6)
    win.target_scope_combo = make_combo(
        [
            ("전체 이미지 (기본)", "all"),
            ("PNG · BMP 무손실 이미지만 변환", "lossless_only"),
            ("1 MB 이상 대용량 이미지만 변환", "over_1mb"),
            ("500 KB 이상 이미지만 변환", "over_500kb"),
            ("100 KB 이상 이미지만 변환", "over_100kb"),
            ("직접 선택한 이미지 (개별 체크)", "custom"),
        ],
        win._on_target_scope_combo_changed,
        tip="미리보기 창을 열지 않고도 메인 실행창에서 변환·추출할 대상 이미지를 바로 선택할 수 있습니다.",
        fixed_w=246,
        auto_min_width=False,
        obj="targetScopeCombo",
    )
    win.open_list_select_btn = make_btn(
        "목록에서 선택…",
        lambda: win.open_document_preview(),
        obj="docPreviewButton",
        tip="이미지 목록(LIST) 및 미리보기 창을 열어 변환할 이미지를 눈으로 보며 직접 체크합니다.",
    )
    scope_lay.addWidget(label("변환 대상", "fieldLabel", wrap=False))
    scope_lay.addWidget(win.target_scope_combo)
    scope_lay.addWidget(win.open_list_select_btn)

    format_card, fl = card("02  저장 형식과 이미지 처리", scope_header, step_ObjectName="stepIndigo", card_id="formatCard")
    fgrid = QGridLayout()
    _configure_unified_4col_grid(fgrid)

    win.format = make_combo(
        [
            ("JPG · 사진 / 보고서 (권장)", "JPEG"),
            ("PNG · 선명한 표 / 투명 배경", "PNG"),
            ("WebP · 고효율 경량 압축", "WEBP"),
            ("TIFF · 인쇄 / 출판 원본", "TIFF"),
            ("원본 형식 · 재변환 없이 추출", "ORIGINAL"),
        ],
        auto_min_width=False,
        obj="formatCombo",
    )
    win.alpha = make_combo(
        [
            ("가능한 형식에서 투명 유지", "keep"),
            ("흰색 배경으로 채우기", "white"),
            ("검정 배경으로 채우기", "black"),
        ],
        auto_min_width=False,
        obj="alphaCombo",
    )
    win.rotate = make_combo(
        [("회전 안 함" if not a else f"시계 방향 {a}°", a) for a in (0, 90, 180, 270)],
        auto_min_width=False,
        obj="rotateCombo",
    )
    win.naming_mode = make_combo(
        [
            ("순번_원본명", "ordinal_name"),
            ("문서명_순번", "doc_ordinal"),
            ("위치_순번", "location_ordinal"),
        ],
        tip="이미지 추출 시 저장될 파일명 규칙(0001_image1 / 문서명_0001 / 구역1_0001)을 선택합니다.",
        auto_min_width=False,
        obj="namingCombo",
    )

    win.gray = QCheckBox("흑백(회색조) 저장")
    win.crop = QCheckBox("한글 본문 자르기 반영 (HWPX)")
    win.crop.toggled.connect(win.crop_changed)

    win.destination = QLineEdit()
    win.destination.setPlaceholderText("저장 폴더를 선택하세요")
    win.folder = make_btn("폴더 선택", win.choose_folder)
    win.open_dest_btn = make_btn("폴더 열기", win.open_destination_folder, tip="지정된 저장 위치 폴더를 파일 탐색기에서 바로 엽니다.")

    fgrid.addWidget(label("저장 형식", "fieldLabel", min_w=LEFT_LABEL_W), 0, 0)
    fgrid.addWidget(win.format, 0, 1)
    fgrid.addWidget(label("투명 배경", "fieldLabel", min_w=RIGHT_LABEL_W), 0, 2)
    fgrid.addWidget(win.alpha, 0, 3)
    fgrid.addWidget(label("회전 / 파일명", "fieldLabel", min_w=LEFT_LABEL_W), 1, 0)
    fgrid.addLayout(hbox((win.rotate, 2), (win.naming_mode, 3), spacing=6), 1, 1)
    fgrid.addLayout(hbox(win.crop, win.gray, spacing=12, stretch_end=True), 1, 2, 1, 2)
    fgrid.addWidget(label("저장 위치", "fieldLabel", min_w=LEFT_LABEL_W), 2, 0)
    fgrid.addLayout(hbox((win.destination, 1), win.folder, win.open_dest_btn, spacing=6), 2, 1, 1, 3)
    fl.addLayout(fgrid)
    win.format_note = label("", "infoNote")
    fl.addWidget(win.format_note)
    return format_card


# ============================================================================
# GROUP 5: Right Panel — 03 Resolution & Print DPI (#sizeCard)
# ============================================================================
def build_resolution_settings_group(win) -> QFrame:
    win.size_card, zl = card("03  해상도와 인쇄 DPI", step_ObjectName="stepViolet", card_id="sizeCard")
    sgrid = QGridLayout()
    _configure_unified_4col_grid(sgrid)

    win.resize_mode = make_combo(
        [
            ("원본 픽셀 유지", "original"),
            ("비율로 조정", "percent"),
            ("긴 변 기준", "long_edge"),
            ("가로 × 세로 범위 안에 맞춤", "fit"),
        ],
        auto_min_width=False,
        obj="resizeModeCombo",
    )
    win.percent = spin(1, 400, 100, " %", obj="percentSpin")
    win.upscale = QCheckBox("원본보다 크게 확대 허용")
    win.width = spin(1, 30000, 1920, " px", obj="widthSpin")
    win.height = spin(1, 30000, 1080, " px", obj="heightSpin")
    win.change_dpi = QCheckBox("DPI 지정")
    win.dpi = spin(36, 2400, 300, " dpi", obj="dpiSpin")

    sgrid.addWidget(label("해상도", "fieldLabel", min_w=LEFT_LABEL_W), 0, 0)
    sgrid.addWidget(win.resize_mode, 0, 1)
    sgrid.addWidget(label("크기 비율", "fieldLabel", min_w=RIGHT_LABEL_W), 0, 2)
    sgrid.addLayout(hbox(win.percent, win.upscale, spacing=8, stretch_end=True), 0, 3)
    sgrid.addWidget(label("가로 / 세로", "fieldLabel", min_w=LEFT_LABEL_W), 1, 0)
    sgrid.addLayout(hbox(win.width, label("×"), win.height, spacing=6, stretch_end=True), 1, 1)
    sgrid.addWidget(label("인쇄 밀도", "fieldLabel", min_w=RIGHT_LABEL_W), 1, 2)
    sgrid.addLayout(hbox(win.change_dpi, win.dpi, spacing=8, stretch_end=True), 1, 3)
    zl.addLayout(sgrid)
    zl.addWidget(label("비율 유지 · DPI만 바꾸면 픽셀 수는 그대로입니다. 미지정 시 저장 가능한 형식에 원본 DPI를 유지합니다.", "muted"))
    return win.size_card


# ============================================================================
# GROUP 6: Right Panel — 04 Quality & Target Capacity (#capacityCard)
# ============================================================================
def build_capacity_settings_group(win) -> QFrame:
    win.capacity_card, cl = card("04  품질과 목표 용량", step_ObjectName="stepTeal", card_id="capacityCard")
    cgrid = QGridLayout()
    _configure_unified_4col_grid(cgrid)

    win.quality = spin(1, 100, 95, obj="qualitySpin")
    win.lossless = QCheckBox("WebP 무손실 압축")
    win.png = spin(0, 9, 6, obj="pngSpin")
    win.use_target = QCheckBox("이미지 한 장당")
    win.use_target.toggled.connect(win._on_use_target_toggled)
    win.target = spin(1, 1024000, 500, "", obj="targetSpin")
    win.target.setFixedWidth(92)
    win.target_unit = make_combo([("KB", "KB"), ("MB", "MB")], win._on_target_unit_changed, fixed_w=76, obj="targetUnitCombo")
    win.shrink = QCheckBox("용량이 초과하면 픽셀 크기도 추가 축소")
    win.shrink.setChecked(True)

    cgrid.addWidget(label("JPG / WebP 품질", "fieldLabel", min_w=LEFT_LABEL_W), 0, 0)
    cgrid.addLayout(hbox(win.quality, win.lossless, spacing=8, stretch_end=True), 0, 1)
    cgrid.addWidget(label("PNG 압축", "fieldLabel", min_w=RIGHT_LABEL_W), 0, 2)
    cgrid.addLayout(hbox(win.png, label("단계 (0~9)", "muted"), spacing=8, stretch_end=True), 0, 3)
    cgrid.addWidget(label("목표 최대 용량", "fieldLabel", min_w=LEFT_LABEL_W), 1, 0)
    cgrid.addLayout(hbox(win.use_target, win.target, win.target_unit, spacing=6, stretch_end=True), 1, 1)
    cgrid.addWidget(label("초과 시 처리", "fieldLabel", min_w=RIGHT_LABEL_W), 1, 2)
    cgrid.addWidget(win.shrink, 1, 3)
    cl.addLayout(cgrid)
    cl.addWidget(label("KB(킬로바이트) · MB(메가바이트) 단위로 이미지 최대 용량을 지정할 수 있습니다. (1 MB = 1,024 KB)", "muted"))
    return win.capacity_card


# ============================================================================
# GROUP 7: Right Panel — Summary, Progress Panel & Action Footer (#progressPanel)
# ============================================================================
def attach_progress_footer_group(win, right_layout: QVBoxLayout, hancom_notice: str):
    win.summary = label("", "summary")
    right_layout.addWidget(win.summary)

    progress_panel = QFrame()
    progress_panel.setObjectName("progressPanel")
    pl = QVBoxLayout(progress_panel)
    pl.setContentsMargins(12, 6, 12, 6)
    pl.setSpacing(4)

    win.current_document = ElidedLabel("현재 문서: 추출 대기")
    win.document_counts = label("문서 완료 0 / 0 · 남음 0", "muted", wrap=False)
    pl.addLayout(hbox((win.current_document, 1), win.document_counts, spacing=8))

    win.current_image = ElidedLabel("현재 이미지: —")
    win.current_image.setObjectName("muted")
    win.status = ElidedLabel("준비 완료")
    win.status.setObjectName("statusText")
    pl.addLayout(hbox((win.current_image, 2), (win.status, 3), spacing=8))

    win.progress = QProgressBar()
    win.progress.setRange(0, 1000)
    win.progress.setFormat("전체 진행 · 추출 대기")
    win.document_progress = QProgressBar()
    win.document_progress.setObjectName("documentProgress")
    win.document_progress.setRange(0, 1000)
    win.document_progress.setFormat("현재 문서 · 추출 대기")
    for bar in (win.progress, win.document_progress):
        bar.setValue(0)
        bar.setTextVisible(True)
        bar.setMinimumHeight(20)
    pl.addLayout(hbox((win.progress, 1), (win.document_progress, 1), spacing=8))
    right_layout.addWidget(progress_panel, 1)

    win.tabs = QTabWidget()
    win.tabs.setMaximumHeight(120)
    win.tabs.setMinimumHeight(80)
    win.log = QTextEdit()
    win.log.setReadOnly(True)
    win.tabs.addTab(win.log, "처리 기록")
    right_layout.addWidget(win.tabs)
    win.tabs.hide()

    win.open_result = make_btn("결과 폴더 열기", win.open_folder, fixed_policy=False)
    win.open_result.setEnabled(False)
    win.reset = make_btn("설정 초기화", win.reset_settings, fixed_policy=False)
    win.toggle_log = make_btn("처리 기록 보기", fixed_policy=False)
    win.toggle_log.setCheckable(True)
    win.toggle_log.toggled.connect(win.show_log)
    win.stop = make_btn("중지", win.cancel_work, obj="danger", fixed_policy=False)
    win.stop.setEnabled(False)
    win.optimize_btn = make_btn(
        "선택 이미지 문서 내 변환",
        win.start_optimize_work,
        obj="optimizeButton",
        fixed_policy=False,
        tip="문서(HWPX, PDF, XLSX, DOCX, PPTX) 안에서 현재 선택(체크)된 이미지만 변환하여 용량을 줄인 사본 문서를 생성합니다.",
    )
    win.start = make_btn(
        "선택 이미지 변환 추출",
        win.start_work,
        obj="primary",
        fixed_policy=False,
        tip="현재 선택(체크)된 이미지만 지정한 저장 형식과 해상도로 변환하여 폴더에 추출합니다.",
    )
    right_layout.addLayout(hbox(win.open_result, win.reset, win.toggle_log, 1, win.stop, win.optimize_btn, win.start, spacing=6))
    right_layout.addWidget(label(hancom_notice, "muted", wrap=False))


# ============================================================================
# GROUP 8: Preview Dialog Layout Groups (#previewTopCard, #previewListCard, #previewViewCard)
# ============================================================================
def build_preview_top_bar_group(dlg) -> QFrame:
    top_card = QFrame()
    top_card.setObjectName("previewTopCard")
    top_vbox = QVBoxLayout(top_card)
    top_vbox.setContentsMargins(12, 7, 12, 7)
    top_vbox.setSpacing(5)

    logo_lbl = QLabel()
    logo_lbl.setPixmap(brand_logo_pixmap(22))
    logo_lbl.setFixedSize(22, 22)

    dlg.doc_combo = SmartComboBox(auto_min_width=False, obj="previewDocCombo")
    dlg.doc_combo.setMinimumWidth(240)
    dlg.doc_combo.currentIndexChanged.connect(dlg._on_doc_combo_changed)
    dlg.extract_single_button = make_btn(
        "이 이미지만 바로 추출",
        dlg.extract_current,
        obj="singleExtractButton",
        tip="현재 오른쪽 VIEW에 표시된 이미지 1장만 현재 변환 설정으로 즉시 추출합니다.",
    )
    dlg.extract_checked_button = make_btn(
        "선택 이미지 변환 추출",
        dlg.extract_checked_all,
        obj="primary",
        tip="현재 문서에서 체크(선택)된 이미지만 지정한 형식으로 변환하여 폴더에 추출합니다.",
    )
    dlg.optimize_doc_button = make_btn(
        "선택 이미지 문서 내 변환",
        dlg.optimize_current_doc,
        obj="optimizeButton",
        tip="현재 문서에서 체크(선택)된 이미지만 변환하여 경량화 문서 사본을 생성합니다 (미선택 이미지는 원본 유지).",
    )
    dlg.open_folder_button = make_btn("결과 폴더 열기", dlg.main_window.open_folder)
    dlg.open_folder_button.setEnabled(False)

    top_vbox.addLayout(hbox(
        logo_lbl, label("문서 선택", "stepCoral", wrap=False), (dlg.doc_combo, 1),
        dlg.extract_single_button, dlg.extract_checked_button, dlg.optimize_doc_button, dlg.open_folder_button,
        spacing=6,
    ))

    dlg.popup_format_combo = SmartComboBox(fixed_w=236, auto_min_width=False, obj="previewFormatCombo")
    for i in range(dlg.main_window.format.count()):
        dlg.popup_format_combo.addItem(dlg.main_window.format.itemText(i))
    dlg.popup_format_combo.currentIndexChanged.connect(dlg._on_popup_format_changed)

    dlg.popup_crop_check = QCheckBox("한글 본문 자르기 반영 (HWPX)")
    dlg.popup_crop_check.toggled.connect(dlg._on_popup_crop_toggled)
    dlg.popup_target_check = QCheckBox("목표 최대 용량 제한 사용")
    dlg.popup_target_check.toggled.connect(dlg._on_popup_target_toggled)
    dlg.popup_summary_label = ElidedLabel("")
    dlg.popup_summary_label.setObjectName("muted")

    top_vbox.addLayout(hbox(
        label("빠른 설정 연동", "fieldLabel", wrap=False),
        dlg.popup_format_combo, dlg.popup_crop_check, dlg.popup_target_check,
        (dlg.popup_summary_label, 1), spacing=10,
    ))
    return top_card


def build_preview_list_group(dlg) -> QFrame:
    list_card, list_layout = card(
        "이미지 목록 / 체크한 항목만 변환·추출",
        dlg.main_window.selection_badge,
        step_tag="LIST",
        step_ObjectName="stepIndigo",
        card_id="previewListCard",
    )
    list_card.setMinimumWidth(450)

    list_layout.addLayout(hbox((dlg.main_window.search, 1), dlg.main_window.refresh, spacing=6))

    dlg.filter_1mb_btn = make_btn(
        "1MB↑",
        lambda: dlg._apply_quick_filter("over_1mb", "1MB 이상 대용량"),
        obj="docPreviewButton",
        tip="현재 문서에서 1MB 이상인 이미지만 체크 선택합니다.",
    )
    dlg.filter_500kb_btn = make_btn(
        "500KB↑",
        lambda: dlg._apply_quick_filter("over_500kb", "500KB 이상"),
        obj="docPreviewButton",
        tip="현재 문서에서 500KB 이상인 이미지만 체크 선택합니다.",
    )
    dlg.filter_lossless_btn = make_btn(
        "PNG·BMP",
        lambda: dlg._apply_quick_filter("lossless_only", "PNG·BMP 무손실"),
        obj="docPreviewButton",
        tip="현재 문서에서 PNG·BMP·TIFF 무손실 이미지만 체크 선택합니다.",
    )
    dlg.convert_selected_btn = make_btn(
        "선택 이미지만 변환",
        dlg.optimize_current_doc,
        obj="optimizeSmallButton",
        tip="체크(선택)된 이미지(예: PNG·BMP)만 현재 설정 형식으로 문서 내 직접 변환합니다.",
    )
    dlg.extract_selected_inline_btn = make_btn(
        "선택 변환 추출",
        dlg.extract_checked_all,
        obj="primarySmallButton",
        tip="체크(선택)된 이미지만 현재 설정 형식으로 변환하여 폴더에 개별 이미지로 저장합니다.",
    )

    list_layout.addLayout(hbox(
        (dlg.main_window.check_all, 1), (dlg.main_window.check_none, 1),
        (dlg.main_window.invert_btn, 1), (dlg.main_window.selection_tools, 1),
        spacing=6,
    ))
    list_layout.addLayout(hbox(
        label("빠른 필터:", "fieldLabel", wrap=False),
        dlg.filter_1mb_btn, dlg.filter_500kb_btn, dlg.filter_lossless_btn,
        1,
        dlg.convert_selected_btn, dlg.extract_selected_inline_btn,
        spacing=5,
    ))
    list_layout.addWidget(dlg.main_window.tree, 1)
    list_layout.addWidget(dlg.main_window.selection_info)
    return list_card


def build_preview_view_group(dlg) -> QFrame:
    dlg.item_title = ElidedLabel("선택된 이미지 미리보기")
    dlg.item_title.setObjectName("muted")
    preview_card, preview_layout = card(
        "미리보기 / 원본 비교",
        dlg.item_title,
        step_tag="VIEW",
        step_ObjectName="stepViolet",
        card_id="previewViewCard",
    )
    preview_card.setMinimumWidth(480)

    dlg.prev_button = dlg.main_window.prev_item_btn
    dlg.prev_button.setText("◀ 이전")
    dlg.next_button = dlg.main_window.next_item_btn
    dlg.next_button.setText("다음 ▶")
    dlg.mode_combo = dlg.main_window.preview_mode
    dlg.mode_combo.setMinimumWidth(120)
    dlg.toggle_compare_btn = make_btn("원본 ⇄ 결과", dlg.toggle_compare_mode, obj="accentSubtleButton")
    dlg.zoom_out_btn = make_btn("－", lambda: dlg.step_zoom(-1), fixed_w=28, obj="iconSmallButton")
    dlg.zoom_reset_btn = make_btn("창 맞춤", dlg.toggle_zoom_fit)
    dlg.zoom_in_btn = make_btn("＋", lambda: dlg.step_zoom(1), fixed_w=28, obj="iconSmallButton")
    dlg.refresh_button = dlg.main_window.preview_button

    preview_layout.addLayout(hbox(
        dlg.prev_button, dlg.next_button, (dlg.mode_combo, 1),
        dlg.toggle_compare_btn, dlg.zoom_out_btn, dlg.zoom_reset_btn, dlg.zoom_in_btn, dlg.refresh_button,
        spacing=5,
    ))

    dlg.image = dlg.main_window.image
    dlg.image.setMinimumSize(320, 260)
    dlg.image.clicked.connect(dlg.toggle_compare_mode)
    dlg.image.zoom_requested.connect(dlg.step_zoom)
    preview_layout.addWidget(dlg.image, 1)

    dlg.preview_info = dlg.main_window.preview_info
    preview_layout.addWidget(dlg.preview_info)
    return preview_card


def _header_style(p: dict[str, str]) -> str:
    """Group 2: Top studio header card, preset pills, and theme switcher."""
    return f"""
        QFrame#headerCard {{ background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #181625,stop:0.55 #231D38,stop:1 #311E34); border:1px solid #312E52; border-radius:10px; }}
        QFrame#sunriseBar {{ background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #F97316,stop:0.48 #F59E0B,stop:1 #6366F1); border-radius:1px; }}
        QLabel#brandMark {{ background:transparent; padding:0px; }}
        QLabel#title {{ font-size:17px; font-weight:800; color:#FFFFFF; }}
        QLabel#headerSub {{ color:#E2E8F0; font-size:11px; font-weight:500; }}
        QLabel#presetCaption {{ color:#FDE68A; font-size:11px; font-weight:700; }}
        QLabel#badge {{ color:#FED7AA; background:rgba(255,255,255,0.12); border:1px solid rgba(253,186,116,0.50); border-radius:6px; padding:2px 10px; font-size:11px; font-weight:800; }}
        QPushButton#presetButton {{ background:rgba(255,255,255,0.14); border:1px solid rgba(255,255,255,0.30); border-radius:10px; padding:2px 10px; min-height:20px; font-size:11px; font-weight:700; color:#FFFFFF; }}
        QPushButton#presetButton:hover {{ background:rgba(249,115,22,0.35); border-color:#FB923C; color:#FFFFFF; }}
        QPushButton#presetButton[activePreset="true"] {{ background:rgba(249,115,22,0.48); border:1px solid #FB923C; color:#FFFFFF; }}
        QPushButton#themeButton {{ background:rgba(255,255,255,0.18); border:1px solid rgba(253,230,138,0.55); border-radius:10px; padding:2px 10px; min-height:20px; font-size:11px; font-weight:700; color:#FDE68A; }}
    """


def _document_list_style(p):
    return f"QFrame#docListCard {{ background:{p['card_bg']}; border:1px solid {p['card_bd']}; border-radius:9px; }}"


def _format_style(p):
    return f"QFrame#formatCard {{ background:{p['card_bg']}; border:1px solid {p['card_bd']}; border-radius:9px; }}"


def _resolution_style(p):
    return f"QFrame#sizeCard {{ background:{p['card_bg']}; border:1px solid {p['card_bd']}; border-radius:9px; }}"


def _capacity_style(p):
    return f"QFrame#capacityCard {{ background:{p['card_bg']}; border:1px solid {p['card_bd']}; border-radius:9px; }}"


def _preview_top_style(p):
    return f"QFrame#previewTopCard {{ background:{p['card_bg']}; border:1px solid {p['card_bd']}; border-radius:9px; }}"


def _preview_list_style(p):
    return f"QFrame#previewListCard {{ background:{p['card_bg']}; border:1px solid {p['card_bd']}; border-radius:9px; }}"


def _preview_view_style(p):
    return f"QFrame#previewViewCard {{ background:{p['card_bg']}; border:1px solid {p['card_bd']}; border-radius:9px; }}"


def _progress_style(p):
    return f"QFrame#progressPanel {{ background:{p['card_bg']}; border:1px solid {p['card_bd']}; border-radius:9px; }}"

def apply_layout_styles(window, dark):
    """Layout owners hold component geometry; theme supplies only foundation/primitive rules."""
    p = _palette(dark)
    roots = [window]
    if window.preview_dialog is not None:
        roots.append(window.preview_dialog)
    providers = {
        'docListCard': _document_list_style,
        'formatCard': _format_style,
        'sizeCard': _resolution_style,
        'capacityCard': _capacity_style,
        'previewTopCard': _preview_top_style,
        'previewListCard': _preview_list_style,
        'previewViewCard': _preview_view_style,
        'progressPanel': _progress_style,
        'headerCard': _header_style,
    }
    for root in roots:
        for role, provider in providers.items():
            for card_widget in root.findChildren(QFrame, role):
                card_widget.setStyleSheet(provider(p))
        for label_widget in root.findChildren(QLabel):
            name = label_widget.objectName()
            if name == 'infoNote':
                label_widget.setStyleSheet(f"""QLabel#infoNote {{ background:{p['note_bg']}; color:{p['note_fg']}; border:1px solid {p['card_bd']}; border-radius:6px; padding:4px 10px; font-size:11px; font-weight:600; }}""")
            elif name == 'previewMeta':
                label_widget.setStyleSheet(f"""QLabel#previewMeta {{ background:{p['meta_bg']}; color:{p['meta_fg']}; border:1px solid {p['sub_bd']}; border-radius:6px; padding:4px 10px; font-size:11px; font-weight:700; }}""")
            elif name == 'summary':
                label_widget.setStyleSheet(f"""QLabel#summary {{ background:{p['sub_bg']}; color:{p['sub_fg']}; border:1px solid {p['sub_bd']}; border-radius:7px; padding:4px 12px; font-weight:800; font-size:12px; }}""")
            elif name == 'preview':
                label_widget.setStyleSheet(f"""QLabel#preview {{ background:{p['input_bg']}; border:1px solid {p['card_bd']}; border-radius:7px; color:{p['muted']}; }}""")
    # Per-table row geometry belongs to the document/list layout owners.
    window.doc_table.setStyleSheet(f"""QTreeWidget#docTable::item {{ min-height:28px; padding:2px 4px; border-bottom:1px solid {p['row_bd']}; }}""")
    window.tree.setStyleSheet(f"""QTreeWidget#imageTree::item {{ min-height:26px; padding:2px 6px; border-bottom:1px solid {p['row_bd']}; }}""")
    window.document_progress.setStyleSheet("QProgressBar::chunk { background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #F97316,stop:1 #F59E0B); border-radius:5px; }")
