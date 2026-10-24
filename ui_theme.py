"""Sunrise Image — Modularized, Layout-Grouped Studio Theme (Light & Dark QSS).

Engineered for crisp 1px integer borders (zero fractional-DPI line breaks),
seamless edge-to-edge subcontrol dividers on QComboBox/QSpinBox, vertically
centered dropdown text, and non-overlapping QTreeWidget#imageTree checkboxes.
"""
from __future__ import annotations
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

INDIGO, CORAL, TEAL, RED, INK = "#4F46E5", "#F97316", "#0D9488", "#E11D48", "#18181B"
BLUE = INDIGO


def brand_logo_pixmap(size: int = 28) -> QPixmap:
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.scale(size / 64, size / 64)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(INDIGO))
        painter.drawRoundedRect(2, 2, 60, 60, 14, 14)
        painter.setPen(QPen(QColor("white"), 3.2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(12, 14, 40, 36, 6, 6)
        painter.setBrush(QColor("#FDBA74"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(35, 19, 10, 10)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor("white"), 3.4))
        path = QPainterPath()
        for idx, (x, y) in enumerate([(16, 44), (26, 31), (34, 39), (41, 33), (48, 44)]):
            (path.moveTo if idx == 0 else path.lineTo)(x, y)
        painter.drawPath(path)
    finally:
        painter.end()
    return pix


def application_icon(size: int = 64) -> QIcon:
    return QIcon(brand_logo_pixmap(size))


def _palette(dark: bool) -> dict[str, str]:
    return {
        "fg": "#F4F4F5" if dark else "#0F172A",
        "bg": "#0F1117" if dark else "#F1F5F9",
        "card_bg": "#161923" if dark else "#FFFFFF",
        "card_bd": "#282E42" if dark else "#CBD5E1",
        "row_bd": "#1E2436" if dark else "#E2E8F0",
        "muted": "#94A3B8" if dark else "#475569",
        "field": "#E4E4E7" if dark else "#1E293B",
        "input_bg": "#10131C" if dark else "#FFFFFF",
        "input_bd": "#38415C" if dark else "#94A3B8",
        "chk_bd": "#64748B" if dark else "#64748B",
        "dis_bg": "#151821" if dark else "#F1F5F9",
        "dis_fg": "#64748B" if dark else "#94A3B8",
        "dis_bd": "#232736" if dark else "#CBD5E1",
        "btn_bg": "#212636" if dark else "#F1F5F9",
        "btn_bd": "#363E57" if dark else "#94A3B8",
        "btn_hv_bg": "#2D344C" if dark else "#E0E7FF",
        "btn_hv_fg": "#C7D2FE" if dark else "#312E81",
        "sub_bg": "#1E1B4B" if dark else "#EEF2FF",
        "sub_fg": "#C7D2FE" if dark else "#312E81",
        "sub_bd": "#4338CA" if dark else "#6366F1",
        "coral_bg": "#431407" if dark else "#FFEDD5",
        "coral_fg": "#FED7AA" if dark else "#9A3412",
        "coral_bd": "#9A3412" if dark else "#FDBA74",
        "violet_bg": "#2E1065" if dark else "#F3E8FF",
        "violet_fg": "#E9D5FF" if dark else "#5B21B6",
        "violet_bd": "#6D28D9" if dark else "#C4B5FD",
        "teal_bg": "#042F2E" if dark else "#CCFBF1",
        "teal_fg": "#99F6E4" if dark else "#115E59",
        "teal_bd": "#0F766E" if dark else "#5EEAD4",
        "note_bg": "#181C28" if dark else "#F8FAFC",
        "note_fg": "#E2E8F0" if dark else "#334155",
        "meta_bg": "#181C28" if dark else "#F5F3FF",
        "meta_fg": "#E2E8F0" if dark else "#1E1B4B",
        "hdr_sec": "#1A1F2E" if dark else "#F1F5F9",
        "alt_bg": "#151925" if dark else "#F8FAFC",
        "sel_bg": "#2E2B5F" if dark else "#E0E7FF",
        "sel_fg": "#FFFFFF" if dark else "#1E1B4B",
        "pbar_bg": "#22283A" if dark else "#E2E8F0",
    }


def _qss_base_containers(p: dict[str, str]) -> str:
    """Group 1: Window background, section cards, and typography badges."""
    return f"""
        QWidget {{ color:{p['fg']}; font-family:"Malgun Gothic","Noto Sans CJK KR","NanumGothic",sans-serif; font-size:12px; }}
        Window, QDialog#previewDialog, QWidget#workspacePanel, QSplitter#documentsSplit {{ background:{p['bg']}; border:0px; }}
        QLabel#muted {{ color:{p['muted']}; font-size:11px; }}
        QLabel#fieldLabel {{ color:{p['field']}; font-size:12px; font-weight:700; }}
        QLabel#statusText, QLabel#cardTitle {{ color:{p['fg']}; font-size:12px; font-weight:800; }}
        QLabel#stepCoral, QLabel#pillBadgeCoral {{ color:{p['coral_fg']}; background:{p['coral_bg']}; border:1px solid {p['coral_bd']}; border-radius:6px; padding:2px 8px; font-size:11px; font-weight:800; }}
        QLabel#stepIndigo, QLabel#pillBadge {{ color:{p['sub_fg']}; background:{p['sub_bg']}; border:1px solid {p['sub_bd']}; border-radius:6px; padding:2px 8px; font-size:11px; font-weight:800; }}
        QLabel#stepViolet {{ color:{p['violet_fg']}; background:{p['violet_bg']}; border:1px solid {p['violet_bd']}; border-radius:6px; padding:2px 7px; font-size:11px; font-weight:800; }}
        QLabel#stepTeal {{ color:{p['teal_fg']}; background:{p['teal_bg']}; border:1px solid {p['teal_bd']}; border-radius:6px; padding:2px 7px; font-size:11px; font-weight:800; }}
    """


def _qss_buttons_group(p: dict[str, str], dark: bool) -> str:
    """Group 3: Role-scoped button styles with integer 1px borders."""
    return f"""
        QPushButton, QToolButton {{ background:{p['btn_bg']}; border:1px solid {p['btn_bd']}; border-radius:6px; padding:0px 10px; min-height:25px; font-size:12px; font-weight:700; color:{p['fg']}; }}
        QPushButton:hover, QToolButton:hover {{ background:{p['btn_hv_bg']}; border-color:#4F46E5; color:{p['btn_hv_fg']}; }}
        QPushButton:pressed, QToolButton:pressed {{ background:{'#1E1B4B' if dark else '#CBD5E1'}; border-color:#4F46E5; }}
        QToolButton::menu-indicator {{ image:none; width:0px; }}
        QPushButton#iconSmallButton {{ padding:0px; min-width:26px; max-width:28px; min-height:25px; font-size:13px; font-weight:800; }}
        QPushButton#accentSubtleButton, QPushButton#backButton {{ background:{p['sub_bg']}; color:{p['sub_fg']}; border:1px solid {p['sub_bd']}; padding:0px 10px; min-height:25px; font-size:12px; font-weight:700; }}
        QPushButton#accentSubtleButton:hover, QPushButton#backButton:hover {{ background:#4F46E5; color:#FFFFFF; border-color:#4338CA; }}
        QPushButton#accentSubtleButton:pressed, QPushButton#backButton:pressed {{ background:{'#312E81' if dark else '#C7D2FE'}; }}
        QPushButton#docPreviewButton, QPushButton#filterChipButton {{ background:{p['sub_bg']}; color:{p['sub_fg']}; border:1px solid {p['sub_bd']}; border-radius:5px; padding:0px 7px; min-height:22px; font-size:11px; font-weight:700; }}
        QPushButton#docPreviewButton:hover, QPushButton#filterChipButton:hover {{ background:#4F46E5; color:#FFFFFF; border-color:#4338CA; }}
        QPushButton#docPreviewButton:pressed, QPushButton#filterChipButton:pressed {{ background:{'#312E81' if dark else '#C7D2FE'}; }}
        QPushButton#filterChipButton[activeFilter="true"] {{ background:#4F46E5; color:#FFFFFF; border:1px solid #3730A3; font-weight:800; }}
        QPushButton#optimizeSmallButton {{ background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #0D9488,stop:1 #2563EB); color:#FFFFFF; border:0; border-radius:5px; padding:0px 9px; min-height:22px; font-size:11px; font-weight:800; }}
        QPushButton#optimizeSmallButton:hover {{ background:#0F766E; color:#FFFFFF; }}
        QPushButton#primarySmallButton {{ background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #4F46E5,stop:1 #7C3AED); color:#FFFFFF; border:0; border-radius:5px; padding:0px 9px; min-height:22px; font-size:11px; font-weight:800; }}
        QPushButton#primarySmallButton:hover {{ background:#4338CA; color:#FFFFFF; }}
        QPushButton#singleExtractButton {{ background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #0D9488,stop:1 #4F46E5); color:#FFFFFF; border:0; padding:0px 12px; min-height:26px; font-size:12px; font-weight:800; border-radius:6px; }}
        QPushButton#optimizeButton {{ background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #0D9488,stop:1 #2563EB); color:#FFFFFF; border:0; padding:0px 13px; min-height:28px; font-size:12px; font-weight:800; border-radius:7px; }}
        QPushButton#primary {{ background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #4F46E5,stop:0.58 #7C3AED,stop:1 #EA580C); color:#FFFFFF; border:0; padding:0px 14px; min-height:28px; font-size:12px; font-weight:800; border-radius:7px; }}
        QPushButton#danger {{ color:#BE123C; border:1px solid #F43F5E; background:#FFF1F2; padding:0px 10px; min-height:28px; font-weight:800; border-radius:7px; }}
        QPushButton#danger:hover {{ color:#FFFFFF; border-color:#E11D48; background:#E11D48; }}
        QPushButton:disabled, QToolButton:disabled {{ color:{p['dis_fg']}; background:{p['dis_bg']}; border-color:{p['dis_bd']}; }}
    """


def _qss_inputs_combos_spins_group(p: dict[str, str], asset_dir: str) -> str:
    """Group 4: QLineEdit, QComboBox, and QSpinBox with seamless edge-to-edge lines and exact vertical text centering.

    - 0px vertical padding (`padding: 0px ...`) lets Qt natively center text vertically at the exact midpoint.
    - `margin: 0px` with `subcontrol-origin: padding` on `::drop-down`, `::up-button`, `::down-button`
      connects the inner divider lines 100% seamlessly from top border to bottom border with zero mid-line breaks,
      while `background: transparent` keeps the outer 4-sided rounded border 100% intact.
    """
    return f"""
        QLineEdit, QSpinBox, QComboBox {{
            background:{p['input_bg']};
            border:1px solid {p['input_bd']};
            border-radius:6px;
            padding:0px 10px;
            min-height:25px;
            color:{p['fg']};
            font-size:12px;
            font-weight:600;
        }}
        QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{
            border:1px solid #4F46E5;
            background:{p['input_bg']};
        }}
        QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled {{
            background:{p['dis_bg']};
            color:{p['dis_fg']};
            border:1px solid {p['dis_bd']};
        }}
        QComboBox {{
            padding:0px 28px 0px 10px;
        }}
        QComboBox::drop-down {{
            subcontrol-origin:padding;
            subcontrol-position:top right;
            width:24px;
            margin:0px;
            border:0px;
            border-left:1px solid {p['card_bd']};
            background:transparent;
        }}
        QComboBox::down-arrow {{
            image:url('{asset_dir}/chevron_down.svg');
            width:11px;
            height:11px;
        }}
        QComboBox QFrame {{
            background-color:{p['card_bg']};
            border:0px;
            border-radius:0px;
            margin:0px;
            padding:0px;
        }}
        QComboBox QAbstractItemView {{
            background-color:{p['card_bg']};
            border:1px solid {p['sub_bd']};
            border-radius:0px;
            margin:0px;
            padding:2px;
            color:{p['fg']};
            selection-background-color:{p['sel_bg']};
            selection-color:{p['sel_fg']};
            outline:0;
        }}
        QComboBox QAbstractItemView::item {{
            min-height:25px;
            padding:0px 10px;
            border-radius:0px;
            color:{p['fg']};
        }}
        QComboBox QAbstractItemView::item:hover {{
            background-color:{p['sub_bg']};
            color:{p['sub_fg']};
        }}
        QComboBox QAbstractItemView::item:selected {{
            background-color:{p['sel_bg']};
            color:{p['sel_fg']};
            font-weight:700;
        }}
        QSpinBox {{
            padding:0px 23px 0px 10px;
        }}
        QSpinBox::up-button {{
            subcontrol-origin:padding;
            subcontrol-position:top right;
            width:20px;
            margin:0px;
            border:0px;
            border-left:1px solid {p['card_bd']};
            border-bottom:1px solid {p['card_bd']};
            background:transparent;
        }}
        QSpinBox::down-button {{
            subcontrol-origin:padding;
            subcontrol-position:bottom right;
            width:20px;
            margin:0px;
            border:0px;
            border-left:1px solid {p['card_bd']};
            background:transparent;
        }}
        QSpinBox::up-arrow {{
            image:url('{asset_dir}/chevron_up.svg');
            width:9px;
            height:9px;
        }}
        QSpinBox::down-arrow {{
            image:url('{asset_dir}/chevron_down.svg');
            width:9px;
            height:9px;
        }}
    """


def _qss_form_checkbox_group(p: dict[str, str], asset_dir: str) -> str:
    """Group 5: Standalone QCheckBox controls inside settings cards."""
    return f"""
        QCheckBox {{ spacing:6px; font-size:12px; font-weight:600; color:{p['fg']}; }}
        QCheckBox:disabled {{ color:{p['dis_fg']}; }}
        QCheckBox::indicator {{
            width:15px;
            height:15px;
            border-radius:4px;
            border:1px solid {p['chk_bd']};
            background:{p['input_bg']};
        }}
        QCheckBox::indicator:hover {{ border-color:#4F46E5; background:{p['sub_bg']}; }}
        QCheckBox::indicator:checked {{ background:#4F46E5; border:1px solid #4338CA; image:url('{asset_dir}/check.svg'); }}
        QCheckBox::indicator:checked:hover {{ background:#4338CA; border-color:#3730A3; image:url('{asset_dir}/check.svg'); }}
        QCheckBox::indicator:disabled {{ background:{p['dis_bg']}; border:1px solid {p['dis_bd']}; image:none; }}
        QCheckBox::indicator:checked:disabled {{ background:#94A3B8; border:1px solid #94A3B8; image:url('{asset_dir}/check.svg'); }}
    """


def _qss_tables_and_trees_group(p: dict[str, str], asset_dir: str) -> str:
    """Group 6: Scoped rules for #docTable and #imageTree with continuous row lines."""
    return f"""
        QListWidget, QTextEdit, QTreeWidget {{
            background:{p['input_bg']};
            border:1px solid {p['card_bd']};
            border-radius:7px;
            outline:0;
            show-decoration-selected:1;
            alternate-background-color:{p['alt_bg']};
            color:{p['fg']};
        }}
        QListWidget::item:hover, QTreeWidget::item:hover {{ background:{p['sub_bg']}; }}
        QListWidget::item:selected, QTreeWidget::item:selected {{ background:{p['sel_bg']}; color:{p['sel_fg']}; font-weight:700; }}

        QTreeWidget::indicator, QTreeWidget#imageTree::indicator {{
            width:13px;
            height:13px;
            margin:2px 6px 2px 4px;
            border-radius:3px;
            border:1px solid {p['chk_bd']};
            background:{p['input_bg']};
        }}
        QTreeWidget::indicator:hover, QTreeWidget#imageTree::indicator:hover {{
            border-color:#4F46E5;
            background:{p['sub_bg']};
        }}
        QTreeWidget::indicator:checked, QTreeWidget#imageTree::indicator:checked {{
            background:#4F46E5;
            border:1px solid #4338CA;
            image:url('{asset_dir}/check.svg');
        }}
        QTreeWidget::indicator:checked:hover, QTreeWidget#imageTree::indicator:checked:hover {{
            background:#4338CA;
            border-color:#3730A3;
            image:url('{asset_dir}/check.svg');
        }}
        QTreeWidget::indicator:disabled, QTreeWidget#imageTree::indicator:disabled {{
            background:{p['dis_bg']};
            border:1px solid {p['dis_bd']};
            image:none;
        }}
        QHeaderView::section {{
            background:{p['hdr_sec']};
            padding:5px 6px;
            border:0px;
            border-bottom:1px solid {p['card_bd']};
            border-right:1px solid {p['row_bd']};
            color:{p['field']};
            font-size:11px;
            font-weight:800;
        }}
        QHeaderView::section:last {{
            border-right:0px;
        }}
        QHeaderView::section:hover {{ background:{p['sub_bg']}; color:{p['sub_fg']}; }}
    """


def _qss_progress_and_menus_group(p: dict[str, str]) -> str:
    """Group 7: Progress bars, scrollbars, and popup menus."""
    return f"""
        QProgressBar {{ background:{p['pbar_bg']}; border:1px solid {p['card_bd']}; border-radius:6px; min-height:20px; text-align:center; font-size:11px; font-weight:800; color:{p['fg']}; }}
        QProgressBar::chunk {{ background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #6366F1,stop:1 #8B5CF6); border-radius:5px; }}
        QScrollBar:vertical {{ background:{p['bg']}; width:10px; margin:0px; border-radius:5px; }}
        QScrollBar::handle:vertical {{ background:{p['card_bd']}; min-height:24px; border-radius:5px; }}
        QScrollBar::handle:vertical:hover {{ background:#6366F1; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0px; }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background:none; }}
        QScrollBar:horizontal {{ background:{p['bg']}; height:10px; margin:0px; border-radius:5px; }}
        QScrollBar::handle:horizontal {{ background:{p['card_bd']}; min-width:24px; border-radius:5px; }}
        QScrollBar::handle:horizontal:hover {{ background:#6366F1; }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width:0px; }}
        QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background:none; }}
        QMenu {{ background-color:{p['card_bg']}; border:1px solid {p['sub_bd']}; padding:3px; margin:0px; border-radius:0px; color:{p['fg']}; }}
        QMenu::item {{ padding:6px 14px; border-radius:0px; color:{p['fg']}; }}
        QMenu::item:selected {{ background:{p['sub_bg']}; color:{p['sub_fg']}; font-weight:700; }}
        QMenu::separator {{ height:1px; background:{p['card_bd']}; margin:4px 6px; }}
    """


def build_stylesheet(dark: bool, asset_dir: str) -> str:
    p = _palette(dark)
    return "\n".join([
        _qss_base_containers(p),
        _qss_buttons_group(p, dark),
        _qss_inputs_combos_spins_group(p, asset_dir),
        _qss_form_checkbox_group(p, asset_dir),
        _qss_tables_and_trees_group(p, asset_dir),
        _qss_progress_and_menus_group(p),
    ])