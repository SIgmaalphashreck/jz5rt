"""SquallowTweaks - Farben, Stylesheet und wiederverwendbare Widgets."""
from __future__ import annotations

import math
from collections import deque
from typing import Optional

from PySide6.QtCore import (Property, QEasingCurve, QPointF, QPropertyAnimation, QRectF, QSize, Qt, Signal)
from PySide6.QtGui import (QBrush, QColor, QFont, QFontMetrics, QIcon, QLinearGradient, QPainter, QPainterPath, QPen,
                           QPixmap, QPolygonF)
from PySide6.QtWidgets import (QGraphicsDropShadowEffect, QAbstractButton, QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget)

BG = "#0A0A10"
SIDEBAR = "#0D0D15"
CARD = "#13131D"
CARD2 = "#1A1A28"
BORDER = "#23233A"
TEXT = "#EDEDF7"
MUTED = "#8C8CA8"
DIM = "#5E5E7A"
ACCENT = "#8B7CF6"
ACCENT2 = "#B89CFF"
GREEN = "#4ADE80"
YELLOW = "#FBBF24"
RED = "#F87171"
CYAN = "#5EEAD4"
PINK = "#F472B6"

TAG_COLORS = {"FPS": ACCENT2, "LATENZ": CYAN, "PING": GREEN, "FRAMETIME": PINK}

QSS = f"""
* {{ font-family: "Segoe UI Variable Text", "Segoe UI", "Inter", "Noto Sans", "DejaVu Sans", sans-serif; font-size: 13px; color: {TEXT}; }}
QMainWindow, #root {{ background: {BG}; }}
QWidget {{ background: transparent; }}
#sidebar {{ background: {SIDEBAR}; border-right: 1px solid {BORDER}; }}
#card {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 14px; }}
#row {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 12px; }}
#row:hover {{ background: {CARD2}; border-color: #34345A; }}
#hero {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #1D1838, stop:1 #13131D); border: 1px solid #2E2A55; border-radius: 16px; }}
QLabel#h1 {{ font-size: 24px; font-weight: 700; }}
QLabel#h2 {{ font-size: 15px; font-weight: 600; }}
QLabel#muted {{ color: {MUTED}; }}
QLabel#dim {{ color: {DIM}; font-size: 11px; }}
QLabel#big {{ font-size: 26px; font-weight: 700; }}
QLabel#pill {{ border-radius: 8px; padding: 2px 8px; font-size: 10px; font-weight: 700; letter-spacing: 1px; }}
QPushButton {{ border: none; }}
QPushButton#nav {{ text-align: left; padding: 11px 14px; border-radius: 10px; color: {MUTED}; font-size: 14px; font-weight: 500; }}
QPushButton#nav:hover {{ background: #171724; color: {TEXT}; }}
QPushButton#nav:checked {{ background: #1E1B3A; color: {TEXT}; }}
QPushButton#accent {{ color: white; font-weight: 700; font-size: 15px; padding: 14px 26px; border-radius: 12px;
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #7C6CF0, stop:1 #A98BFF); }}
QPushButton#accent:hover {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #8D7EFF, stop:1 #BBA0FF); }}
QPushButton#accent:disabled {{ background: #2A2848; color: {DIM}; }}
QPushButton#ghost {{ background: {CARD2}; border: 1px solid {BORDER}; border-radius: 10px; padding: 9px 16px; font-weight: 600; }}
QPushButton#ghost:hover {{ border-color: {ACCENT}; background: #201E36; }}
QPushButton#danger {{ background: #2A1A22; border: 1px solid #4A2630; border-radius: 10px; padding: 9px 16px; font-weight: 600; color: {RED}; }}
QPushButton#danger:hover {{ background: #3A202B; }}
QPushButton#chip {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 15px; padding: 6px 14px; color: {MUTED}; font-weight: 600; }}
QPushButton#chip:hover {{ color: {TEXT}; border-color: #34345A; }}
QPushButton#chip:checked {{ background: #261F4D; border-color: {ACCENT}; color: white; }}
QLineEdit {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 10px; padding: 9px 12px; selection-background-color: {ACCENT}; }}
QLineEdit:focus {{ border-color: {ACCENT}; }}
QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #2B2B45; border-radius: 4px; min-height: 36px; }}
QScrollBar::handle:vertical:hover {{ background: #3B3B60; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar:horizontal {{ height: 0; }}
QProgressBar {{ background: #1B1B2B; border: none; border-radius: 3px; max-height: 6px; min-height: 6px; }}
QProgressBar::chunk {{ border-radius: 3px; background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 {ACCENT}, stop:1 {CYAN}); }}
QToolTip {{ background: #1B1B2B; color: {TEXT}; border: 1px solid #34345A; padding: 8px; border-radius: 6px; }}
QTableView {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 12px; gridline-color: transparent; outline: 0;
    selection-background-color: #251F4B; alternate-background-color: #151522; }}
QTableView::item {{ padding-left: 8px; border: none; }}
QHeaderView::section {{ background: {CARD}; color: {MUTED}; border: none; border-bottom: 1px solid {BORDER}; padding: 9px 8px;
    font-size: 11px; font-weight: 700; letter-spacing: 1px; }}
QMessageBox {{ background: {CARD}; }}
"""


# ---------------------------------------------------------------------------
# Icons (gezeichnet, keine Schrift/Dateien noetig)
# ---------------------------------------------------------------------------
def make_icon(name: str, color: str = MUTED, size: int = 22) -> QIcon:
    pm = QPixmap(size * 2, size * 2)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.scale(2, 2)
    c = QColor(color)
    pen = QPen(c, 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    s = float(size)
    if name == "dashboard":
        g = s * 0.14
        w = (s - 3 * g) / 2
        for r in range(2):
            for q in range(2):
                p.drawRoundedRect(QRectF(g + q * (w + g), g + r * (w + g), w, w), 3, 3)
    elif name == "bolt":
        poly = QPolygonF([QPointF(s * .58, s * .08), QPointF(s * .22, s * .56), QPointF(s * .47, s * .56),
                          QPointF(s * .40, s * .92), QPointF(s * .78, s * .42), QPointF(s * .52, s * .42)])
        p.setBrush(c)
        p.drawPolygon(poly)
    elif name == "target":
        p.drawEllipse(QRectF(s * .14, s * .14, s * .72, s * .72))
        p.drawEllipse(QRectF(s * .36, s * .36, s * .28, s * .28))
        for a, b, c2, d in ((.5, .02, .5, .2), (.5, .8, .5, .98), (.02, .5, .2, .5), (.8, .5, .98, .5)):
            p.drawLine(QPointF(s * a, s * b), QPointF(s * c2, s * d))
    elif name == "signal":
        p.setPen(Qt.NoPen)
        p.setBrush(c)
        for i in range(4):
            h = s * (0.25 + i * 0.2)
            p.drawRoundedRect(QRectF(s * (0.1 + i * 0.22), s * .9 - h, s * .14, h), 2, 2)
    elif name == "list":
        for i in range(3):
            y = s * (0.22 + i * 0.28)
            p.drawLine(QPointF(s * .30, y), QPointF(s * .92, y))
            p.setBrush(c)
            p.drawEllipse(QPointF(s * .12, y), 1.4, 1.4)
            p.setBrush(Qt.NoBrush)
    elif name == "gear":
        p.drawEllipse(QRectF(s * .30, s * .30, s * .40, s * .40))
        for i in range(8):
            a = math.radians(i * 45)
            p.drawLine(QPointF(s * .5 + math.cos(a) * s * .30, s * .5 + math.sin(a) * s * .30),
                       QPointF(s * .5 + math.cos(a) * s * .44, s * .5 + math.sin(a) * s * .44))
    p.end()
    return QIcon(pm)


def tinted_pixmap(path: str, size: int) -> QPixmap:
    pm = QPixmap(path)
    return pm.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)


# ---------------------------------------------------------------------------
# Kleine Bausteine
# ---------------------------------------------------------------------------
def label(text: str = "", name: str = "", wrap: bool = False) -> QLabel:
    lab = QLabel(text)
    if name:
        lab.setObjectName(name)
    lab.setWordWrap(wrap)
    return lab


def pill(text: str, color: str) -> QLabel:
    lab = QLabel(text)
    lab.setObjectName("pill")
    c = QColor(color)
    lab.setStyleSheet(f"QLabel#pill {{ color: {color}; background: rgba({c.red()},{c.green()},{c.blue()},38); }}")
    lab.setAlignment(Qt.AlignCenter)
    lab.setFixedHeight(20)
    lab.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
    return lab


class ElidedLabel(QLabel):
    """Einzeiliges Label, das zu langen Text mit … abschneidet (voller Text im Tooltip)."""

    def __init__(self, text: str = "", name: str = ""):
        super().__init__(text)
        if name:
            self.setObjectName(name)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.setMinimumWidth(40)

    def paintEvent(self, _e):
        p = QPainter(self)
        fm = QFontMetrics(self.font())
        p.setPen(self.palette().color(self.foregroundRole()))
        p.setFont(self.font())
        p.drawText(self.rect(), Qt.AlignVCenter | Qt.AlignLeft, fm.elidedText(self.text(), Qt.ElideRight, self.width()))


class Card(QFrame):
    def __init__(self, name: str = "card"):
        super().__init__()
        self.setObjectName(name)
        self.setAttribute(Qt.WA_StyledBackground, True)


class Toggle(QAbstractButton):
    """Animierter Schalter."""

    def __init__(self):
        super().__init__()
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(46, 26)
        self._pos = 0.0
        self._anim = QPropertyAnimation(self, b"offset", self)
        self._anim.setDuration(140)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self.toggled.connect(self._animate)

    def _get(self) -> float:
        return self._pos

    def _set(self, v: float) -> None:
        self._pos = v
        self.update()

    offset = Property(float, _get, _set)

    def _animate(self, on: bool):
        self._anim.stop()
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def set_checked_silent(self, on: bool):
        self.blockSignals(True)
        self.setChecked(on)
        self.blockSignals(False)
        self._anim.stop()
        self._pos = 1.0 if on else 0.0
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(1, 1, self.width() - 2, self.height() - 2)
        off, on = QColor("#2A2A42"), QColor(ACCENT)
        t = self._pos
        col = QColor(int(off.red() + (on.red() - off.red()) * t), int(off.green() + (on.green() - off.green()) * t),
                     int(off.blue() + (on.blue() - off.blue()) * t))
        if not self.isEnabled():
            col.setAlpha(110)
        p.setPen(Qt.NoPen)
        p.setBrush(col)
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        d = r.height() - 6
        x = r.left() + 3 + (r.width() - d - 6) * t
        p.setBrush(QColor("#ffffff" if self.isEnabled() else "#9A9AB0"))
        p.drawEllipse(QRectF(x, r.top() + 3, d, d))


class Chips(QWidget):
    """Gruppe exklusiver Chips; sendet changed(name)."""
    changed = Signal(str)

    def __init__(self, names: list[str], current: Optional[str] = None):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self.buttons: dict[str, QPushButton] = {}
        for n in names:
            b = QPushButton(n)
            b.setObjectName("chip")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _c=False, name=n: self.select(name))
            lay.addWidget(b)
            self.buttons[n] = b
        lay.addStretch(1)
        self.select(current or names[0], emit=False)

    def select(self, name: str, emit: bool = True):
        for n, b in self.buttons.items():
            b.setChecked(n == name)
        self.current = name
        if emit:
            self.changed.emit(name)


class RingGauge(QWidget):
    def __init__(self, c1: str = ACCENT, c2: str = CYAN):
        super().__init__()
        self.c1, self.c2 = QColor(c1), QColor(c2)
        self._target = 0.0
        self._shown = 0.0
        self.text = "–"
        self.sub = ""
        self.setMinimumSize(150, 150)
        self._anim = QPropertyAnimation(self, b"shown", self)
        self._anim.setDuration(450)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

    def _g(self) -> float:
        return self._shown

    def _s(self, v: float) -> None:
        self._shown = v
        self.update()

    shown = Property(float, _g, _s)

    def set_value(self, frac: Optional[float], text: str, sub: str = ""):
        self.text, self.sub = text, sub
        frac = max(0.0, min(1.0, frac or 0.0))
        if abs(frac - self._target) > 0.004:
            self._target = frac
            self._anim.stop()
            self._anim.setStartValue(self._shown)
            self._anim.setEndValue(frac)
            self._anim.start()
        else:
            self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        side = min(self.width(), self.height())
        th = max(10, side * 0.085)
        r = QRectF((self.width() - side) / 2 + th, (self.height() - side) / 2 + th, side - 2 * th, side - 2 * th)
        p.setPen(QPen(QColor("#1D1D2E"), th, Qt.SolidLine, Qt.RoundCap))
        p.drawArc(r, 0, 360 * 16)
        t = self._shown
        col = QColor(int(self.c1.red() + (self.c2.red() - self.c1.red()) * t), int(self.c1.green() + (self.c2.green() - self.c1.green()) * t),
                     int(self.c1.blue() + (self.c2.blue() - self.c1.blue()) * t))
        if t > 0.8:
            k = (t - 0.8) / 0.2
            red = QColor(RED)
            col = QColor(int(col.red() + (red.red() - col.red()) * k), int(col.green() + (red.green() - col.green()) * k),
                         int(col.blue() + (red.blue() - col.blue()) * k))
        p.setPen(QPen(col, th, Qt.SolidLine, Qt.RoundCap))
        if t > 0.004:
            p.drawArc(r, 90 * 16, int(-360 * 16 * t))
        p.setPen(QColor(TEXT))
        f = QFont(self.font())
        f.setPixelSize(int(side * 0.22))
        f.setBold(True)
        p.setFont(f)
        p.drawText(QRectF(r.left(), r.top() + r.height() * 0.22, r.width(), r.height() * 0.36), Qt.AlignCenter, self.text)
        f.setPixelSize(max(10, int(side * 0.085)))
        f.setBold(False)
        p.setFont(f)
        p.setPen(QColor(MUTED))
        p.drawText(QRectF(r.left(), r.top() + r.height() * 0.56, r.width(), r.height() * 0.2), Qt.AlignCenter, self.sub)


class LineChart(QWidget):
    """Verlaufsgrafik mit mehreren Reihen. Werte None = Messfehler (roter Strich)."""

    def __init__(self, vmax: Optional[float] = 100.0, unit: str = "%", maxlen: int = 90, show_legend: bool = True):
        super().__init__()
        self.vmax, self.unit, self.maxlen, self.show_legend = vmax, unit, maxlen, show_legend
        self.series: dict[str, tuple[QColor, deque]] = {}
        self.setMinimumHeight(150)

    def add_series(self, name: str, color: str):
        self.series[name] = (QColor(color), deque(maxlen=self.maxlen))

    def push(self, name: str, value: Optional[float]):
        self.series[name][1].append(value)

    def clear(self):
        for _c, d in self.series.values():
            d.clear()
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        top_pad, bot_pad = (30 if self.show_legend else 8), 8
        plot_h = h - top_pad - bot_pad
        vals = [v for _c, d in self.series.values() for v in d if v is not None]
        vmax = self.vmax or max(max(vals, default=1.0) * 1.25, 1.0)
        p.setPen(QPen(QColor("#1F1F33"), 1))
        for i in range(5):
            y = top_pad + plot_h * i / 4
            p.drawLine(QPointF(0, y), QPointF(w, y))
        p.setPen(QColor(DIM))
        f = QFont(self.font())
        f.setPixelSize(10)
        p.setFont(f)
        p.drawText(QRectF(w - 70, top_pad - 14, 66, 12), Qt.AlignRight, f"{vmax:.0f}{self.unit}")
        x = 4
        for name, (col, data) in self.series.items():
            if self.show_legend:
                p.setBrush(col)
                p.setPen(Qt.NoPen)
                p.drawEllipse(QPointF(x + 4, 14), 4, 4)
                p.setPen(QColor(MUTED))
                p.setFont(QFont(self.font()))
                f2 = p.font()
                f2.setPixelSize(12)
                p.setFont(f2)
                p.drawText(QPointF(x + 14, 18), name)
                x += 24 + QFontMetrics(f2).horizontalAdvance(name)
            pts = list(data)
            if len(pts) < 2:
                continue
            step = w / max(1, self.maxlen - 1)
            x0 = w - step * (len(pts) - 1)
            path = QPainterPath()
            started = False
            for i, v in enumerate(pts):
                px = x0 + i * step
                if v is None:
                    p.setPen(QPen(QColor(RED), 2))
                    p.drawLine(QPointF(px, h - bot_pad), QPointF(px, h - bot_pad - 14))
                    started = False
                    continue
                py = top_pad + plot_h * (1 - min(1.0, v / vmax))
                if not started:
                    path.moveTo(px, py)
                    started = True
                else:
                    path.lineTo(px, py)
            fill = QPainterPath(path)
            if started:
                fill.lineTo(QPointF(w, h - bot_pad))
                fill.lineTo(QPointF(x0, h - bot_pad))
                g = QLinearGradient(0, top_pad, 0, h)
                c1 = QColor(col)
                c1.setAlpha(60)
                c2 = QColor(col)
                c2.setAlpha(0)
                g.setColorAt(0, c1)
                g.setColorAt(1, c2)
                if len(self.series) == 1:
                    p.setPen(Qt.NoPen)
                    p.setBrush(g)
                    p.drawPath(fill)
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(col, 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.drawPath(path)


class StatTile(Card):
    def __init__(self, title: str, color: str = TEXT):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(2)
        self.title = label(title.upper(), "dim")
        self.value = label("–", "big")
        self.value.setStyleSheet(f"color:{color};")
        self.sub = label("", "muted")
        lay.addWidget(self.title)
        lay.addWidget(self.value)
        lay.addWidget(self.sub)

    def set(self, value: str, sub: str = ""):
        self.value.setText(value)
        self.sub.setText(sub)


class TweakRow(QFrame):
    """Eine Zeile: Name + EIN Satz + Tags + Schalter. Details nur im Tooltip."""
    toggled = Signal(str, bool)

    def __init__(self, tweak, admin_ok: bool):
        super().__init__()
        self.tweak = tweak
        self.locked = tweak.admin and not admin_ok
        self.setObjectName("row")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedHeight(68)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 8, 16, 8)
        lay.setSpacing(12)
        col = QVBoxLayout()
        col.setSpacing(2)
        head = QHBoxLayout()
        head.setSpacing(6)
        name = QLabel(tweak.name)
        name.setStyleSheet("font-size:14px;font-weight:600;")
        head.addWidget(name)
        if tweak.recommended:
            star = QLabel("★")
            star.setStyleSheet(f"color:{ACCENT2};")
            star.setToolTip("Empfohlen")
            head.addWidget(star)
        head.addStretch(1)
        col.addLayout(head)
        col.addWidget(ElidedLabel(tweak.description, "muted"))
        lay.addLayout(col, 1)
        tags = QHBoxLayout()
        tags.setSpacing(6)
        for t in tweak.tags:
            tags.addWidget(pill(t, TAG_COLORS.get(t, MUTED)))
        if tweak.admin:
            tags.addWidget(pill("ADMIN", RED if self.locked else DIM))
        lay.addLayout(tags)
        self.status = QLabel("")
        self.status.setObjectName("dim")
        self.status.setFixedWidth(0)
        self.toggle = Toggle()
        lay.addWidget(self.toggle)
        self.toggle.clicked.connect(lambda c: self.toggled.emit(self.tweak.id, bool(c)))
        tip = f"{tweak.description}\n\n{tweak.impact}"
        if tweak.restart and tweak.restart != "Nein":
            tip += f"\n\nWirksam: {tweak.restart}"
        if tweak.risk != "niedrig":
            tip += f"\nRisiko: {tweak.risk}"
        self.setToolTip(tip)
        if self.locked:
            self.toggle.setEnabled(False)
            self.setToolTip(tip + "\n\nBraucht Administratorrechte.")

    def set_state(self, state: str, msg: str = ""):
        from engine import STATUS_ACTIVE, STATUS_UNKNOWN
        active = state == STATUS_ACTIVE
        self.toggle.set_checked_silent(active)
        unavailable = state == STATUS_UNKNOWN
        self.toggle.setEnabled(not unavailable and not self.locked)
        self.setWindowOpacity(1.0)
        self.setStyleSheet("" if not unavailable else "QFrame#row { background: #101018; } QLabel { color: #5E5E7A; }")


def glow(widget: QWidget, color: str = ACCENT, radius: int = 28) -> None:
    """Weicher farbiger Schein hinter einem Widget (z. B. Hauptbutton)."""
    eff = QGraphicsDropShadowEffect(widget)
    eff.setBlurRadius(radius)
    eff.setOffset(0, 4)
    c = QColor(color)
    c.setAlpha(120)
    eff.setColor(c)
    widget.setGraphicsEffect(eff)
