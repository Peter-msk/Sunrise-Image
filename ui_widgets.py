"""Sunrise Image — Core UI widgets, async task runner, and non-clipping widget builders."""
from __future__ import annotations
import re
import uuid
from PySide6.QtCore import QObject, QRunnable, QSize, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QLabel, QListView, QPushButton,
    QSizePolicy, QSpinBox, QVBoxLayout, QWidget,
)


def format_size(num_bytes: int | float) -> str:
    b = max(0.0, float(num_bytes))
    if b >= 1024 * 1024:
        return f"{b / (1024 * 1024):,.2f} MB"
    if b >= 1024:
        return f"{b / 1024:,.1f} KB"
    return f"{b / 1024:,.2f} KB" if b > 0 else "0 KB"


def format_compact_size(num_bytes: int | float) -> str:
    b = max(0.0, float(num_bytes))
    if b >= 1024 * 1024:
        mb = b / (1024 * 1024)
        return f"{mb:,.0f}MB" if mb >= 100 else f"{mb:,.1f}MB"
    if b >= 1024:
        return f"{b / 1024:,.0f}KB"
    return f"{int(b)}B" if b > 0 else "0KB"


class Signals(QObject):
    event = Signal(object)


class PreviewLabel(QLabel):
    resized = Signal()
    clicked = Signal()
    zoom_requested = Signal(int)

    def sizeHint(self):
        return QSize(360, 260)

    def minimumSizeHint(self):
        return QSize(180, 120)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.resized.emit()

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        if hasattr(event, "button") and event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()

    def wheelEvent(self, event):
        if hasattr(event, "angleDelta"):
            delta = event.angleDelta().y()
            if delta:
                self.zoom_requested.emit(1 if delta > 0 else -1)
                event.accept()
                return
        super().wheelEvent(event)


class ElidedLabel(QLabel):
    def __init__(self, text=""):
        super().__init__()
        self.full_text = ""
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.setMinimumWidth(0)
        self.setText(text)

    def setText(self, text):
        self.full_text = str(text)
        self.setToolTip(self.full_text)
        self._fit_text()

    def _fit_text(self):
        super().setText(self.fontMetrics().elidedText(self.full_text, Qt.TextElideMode.ElideMiddle, max(0, self.width())))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_text()


class Task(QRunnable):
    def __init__(self, function, kind):
        super().__init__()
        self.id = uuid.uuid4().hex
        self.function, self.kind = function, kind
        self.signals = Signals()

    def run(self):
        emit = lambda val: self.signals.event.emit({"job": self.id, "kind": "progress", "value": val})
        try:
            packet = {"job": self.id, "kind": self.kind, "value": self.function(emit)}
        except Exception as exc:
            packet = {"job": self.id, "kind": self.kind, "error": str(exc)}
        self.signals.event.emit(packet)


class SmartButton(QPushButton):
    """QPushButton that recalculates an exact non-clipping minimumWidth after QSS polish and setText."""
    def __init__(self, text="", fixed_w=None, obj=""):
        super().__init__(text)
        self._fixed_w = fixed_w
        if obj:
            self.setObjectName(obj)
        if fixed_w:
            if fixed_w <= 32 and not obj:
                self.setObjectName("iconSmallButton")
            self.setFixedWidth(fixed_w)
            self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        else:
            self.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
            self.update_min_width()

    def setText(self, text):
        super().setText(text)
        if not self._fixed_w:
            self.update_min_width()

    def update_min_width(self):
        if self._fixed_w:
            return
        self.ensurePolished()
        obj = self.objectName()
        adv = self.fontMetrics().horizontalAdvance(self.text() or "")
        if obj == "iconSmallButton":
            pad = 8
        elif obj in {"docPreviewButton", "filterChipButton", "optimizeSmallButton", "primarySmallButton"}:
            pad = 16
        elif obj in {"presetButton", "themeButton", "accentSubtleButton", "backButton"}:
            pad = 22
        elif obj in {"primary", "optimizeButton", "singleExtractButton"}:
            pad = 28
        else:
            pad = 22
        self.setMinimumWidth(adv + pad)

    def showEvent(self, event):
        super().showEvent(event)
        if not self._fixed_w:
            self.update_min_width()


def setup_combo_view(cb: QComboBox):
    """Configure QComboBox popup view and container for crisp rectangular borders and centered item text."""
    view = QListView(cb)
    view.setFrameShape(QFrame.Shape.NoFrame)
    view.setViewportMargins(0, 0, 0, 0)
    view.setSpacing(0)
    view.setUniformItemSizes(True)
    cb.setView(view)
    container = cb.findChild(QFrame)
    if container is not None:
        container.setFrameShape(QFrame.Shape.NoFrame)
        container.setContentsMargins(0, 0, 0, 0)
        container.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        container.setWindowFlags(
            Qt.WindowType.Popup
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint
        )


class SmartComboBox(QComboBox):
    """QComboBox with clean rectangular popup container, intact 4-sided outer border, and vertically centered text."""
    def __init__(self, fixed_w=None, auto_min_width=True, obj=""):
        super().__init__()
        self._fixed_w = fixed_w
        self._auto_min_width = auto_min_width
        if obj:
            self.setObjectName(obj)
        setup_combo_view(self)
        if fixed_w:
            self.setFixedWidth(fixed_w)
            self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def addItem(self, *args, **kwargs):
        super().addItem(*args, **kwargs)
        idx = self.count() - 1
        if idx >= 0:
            self.setItemData(idx, int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), Qt.ItemDataRole.TextAlignmentRole)

    def update_min_width(self):
        self.ensurePolished()
        if self.count() == 0:
            return
        fm = self.fontMetrics()
        max_adv = max(fm.horizontalAdvance(self.itemText(i)) for i in range(self.count()))
        if self.view() is not None:
            self.view().setMinimumWidth(max(self.width(), max_adv + 40))
        if not self._fixed_w and self._auto_min_width:
            self.setMinimumWidth(min(248, max_adv + 42))

    def showPopup(self):
        container = self.findChild(QFrame)
        if container is not None:
            container.setFrameShape(QFrame.Shape.NoFrame)
            container.setContentsMargins(0, 0, 0, 0)
        self.update_min_width()
        super().showPopup()

    def showEvent(self, event):
        super().showEvent(event)
        self.update_min_width()


def relayout_widget_tree(root: QWidget):
    """Polish all child widgets and recursively invalidate/activate all layouts to prevent initial launch layout glitches."""
    if root is None:
        return
    root.ensurePolished()
    for child in root.findChildren(QWidget):
        child.ensurePolished()
        if isinstance(child, (SmartButton, SmartComboBox)):
            child.update_min_width()
        child.updateGeometry()

    def _activate(lay):
        if lay is None:
            return
        for i in range(lay.count()):
            item = lay.itemAt(i)
            if item is not None and item.layout() is not None:
                _activate(item.layout())
        lay.invalidate()
        lay.activate()

    _activate(root.layout())
    for child in root.findChildren(QWidget):
        if child.layout() is not None:
            _activate(child.layout())
    root.updateGeometry()
    root.update()


def label(text, object_name="", wrap=None, min_w=None):
    lbl = QLabel(text)
    lbl.setWordWrap(object_name not in {"fieldLabel", "cardTitle", "title"} if wrap is None else bool(wrap))
    if object_name:
        lbl.setObjectName(object_name)
    if object_name == "fieldLabel":
        lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    if min_w:
        lbl.setMinimumWidth(min_w)
    return lbl


def make_btn(text, slot=None, obj="", tip="", fixed_w=None, fixed_policy=True):
    btn = SmartButton(str(text), fixed_w=fixed_w, obj=obj)
    if tip:
        btn.setToolTip(tip)
    if slot is not None:
        btn.clicked.connect(slot)
    return btn


def make_combo(items, slot=None, tip="", fixed_w=None, auto_min_width=True, obj=""):
    cb = SmartComboBox(fixed_w=fixed_w, auto_min_width=auto_min_width, obj=obj)
    for entry in items:
        if isinstance(entry, tuple):
            cb.addItem(entry[0], entry[1])
        else:
            cb.addItem(str(entry))
    cb.update_min_width()
    if tip:
        cb.setToolTip(tip)
    if slot is not None:
        cb.currentIndexChanged.connect(slot)
    return cb


def hbox(*widgets, spacing=6, margins=(0, 0, 0, 0), stretch_end=False):
    lay = QHBoxLayout()
    lay.setContentsMargins(*margins)
    lay.setSpacing(spacing)
    for item in widgets:
        if isinstance(item, tuple):
            lay.addWidget(item[0], item[1])
        elif isinstance(item, int):
            lay.addStretch(item)
        else:
            lay.addWidget(item)
    if stretch_end:
        lay.addStretch()
    return lay


def card(title, right_widget=None, step_tag="", step_ObjectName="stepIndigo", card_id="card"):
    box = QFrame()
    box.setObjectName(card_id or "card")
    layout = QVBoxLayout(box)
    layout.setContentsMargins(12, 8, 12, 8)
    layout.setSpacing(5)
    header = QHBoxLayout()
    header.setContentsMargins(0, 0, 0, 0)
    header.setSpacing(8)
    m = re.match(r"^(0[0-9])\s+(.*)$", title)
    if m and not step_tag:
        step_tag, title = m.group(1), m.group(2)
    if step_tag:
        tag_lbl = QLabel(step_tag)
        tag_lbl.setObjectName(step_ObjectName)
        tag_lbl.setWordWrap(False)
        tag_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tag_lbl.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        header.addWidget(tag_lbl)
    header.addWidget(label(title, "cardTitle"))
    header.addStretch(1)
    if right_widget is not None:
        header.addWidget(right_widget)
    layout.addLayout(header)
    return box, layout


def spin(low, high, value, suffix="", obj=""):
    s = QSpinBox()
    if obj:
        s.setObjectName(obj)
    s.setRange(low, high)
    s.setValue(value)
    s.setSuffix(suffix)
    s.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    s.setFixedWidth(120 if high >= 100000 else 108 if suffix else 92)
    s.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    return s