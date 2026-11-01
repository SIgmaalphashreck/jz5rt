"""SquallowTweaks - Hauptfenster."""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QLabel, QMainWindow, QPushButton, QStackedWidget, QVBoxLayout, QWidget

import pages
import service as svc
from ui_common import ACCENT2, GREEN, MUTED, RED, label, make_icon, pill, tinted_pixmap

APP_NAME = "SquallowTweaks"
VERSION = "1.0"


def asset(name: str) -> str:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return str(base / "assets" / name)


class MainWindow(QMainWindow):
    NAV = (("Dashboard", "dashboard"), ("Tweaks", "bolt"), ("Fortnite", "target"), ("Netzwerk", "signal"),
           ("Prozesse", "list"), ("Einstellungen", "gear"))

    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(QIcon(asset("bird.png")))
        self.resize(1280, 800)
        self.setMinimumSize(1100, 700)
        self.service = svc.Service()
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        h = QHBoxLayout(root)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        h.addWidget(self._sidebar())
        self.stack = QStackedWidget()
        self.pages = {
            "Dashboard": pages.DashboardPage(self.service), "Tweaks": pages.TweaksPage(self.service),
            "Fortnite": pages.FortnitePage(self.service), "Netzwerk": pages.NetworkPage(self.service),
            "Prozesse": pages.ProcessesPage(self.service), "Einstellungen": pages.SettingsPage(self.service),
        }
        for p in self.pages.values():
            self.stack.addWidget(p)
        h.addWidget(self.stack, 1)
        self.sampler = svc.Sampler()
        self.sampler.sample.connect(self.on_sample)
        self.sampler.procs.connect(self.pages["Prozesse"].on_procs)
        self.sampler.start()
        self.service.refresh_states()
        self.go("Dashboard")

    def _sidebar(self) -> QWidget:
        side = QWidget()
        side.setObjectName("sidebar")
        side.setFixedWidth(232)
        v = QVBoxLayout(side)
        v.setContentsMargins(14, 22, 14, 16)
        v.setSpacing(4)
        logo = QHBoxLayout()
        logo.setContentsMargins(6, 0, 0, 14)
        icon = QLabel()
        icon.setPixmap(tinted_pixmap(asset("bird.png"), 40))
        logo.addWidget(icon)
        name = QVBoxLayout()
        name.setSpacing(0)
        t1 = QLabel("Squallow")
        t1.setStyleSheet("font-size:19px;font-weight:700;")
        t2 = QLabel("TWEAKS")
        t2.setStyleSheet(f"font-size:10px;font-weight:700;letter-spacing:4px;color:{ACCENT2};")
        name.addWidget(t1)
        name.addWidget(t2)
        logo.addLayout(name)
        logo.addStretch(1)
        v.addLayout(logo)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.nav_buttons: dict[str, QPushButton] = {}
        for text, ico in self.NAV:
            b = QPushButton("  " + text)
            b.setObjectName("nav")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setIconSize(QSize(20, 20))
            b.setIcon(make_icon(ico, MUTED))
            b.setProperty("ico", ico)
            b.clicked.connect(lambda _c=False, n=text: self.go(n))
            self.group.addButton(b)
            v.addWidget(b)
            self.nav_buttons[text] = b
        v.addStretch(1)
        self.admin_pill = pill("ADMIN" if self.service.admin else "KEIN ADMIN", GREEN if self.service.admin else RED)
        row = QHBoxLayout()
        row.addWidget(self.admin_pill)
        row.addStretch(1)
        row.addWidget(label(f"v{VERSION}", "dim"))
        v.addLayout(row)
        return side

    def go(self, name: str):
        for n, b in self.nav_buttons.items():
            on = n == name
            b.setChecked(on)
            b.setIcon(make_icon(b.property("ico"), ACCENT2 if on else MUTED))
        self.stack.setCurrentWidget(self.pages[name])
        self.sampler.want_procs = name == "Prozesse"
        if name == "Fortnite":
            self.pages["Fortnite"].refresh()
        if name == "Netzwerk":
            if not self.pages["Netzwerk"].monitor:
                self.pages["Netzwerk"].start()
        else:
            self.pages["Netzwerk"].stop()

    def on_sample(self, d: dict):
        self.service.fortnite_running = bool(d.get("fn"))
        self.pages["Dashboard"].on_sample(d)
        if self.stack.currentWidget() is self.pages["Fortnite"]:
            self.pages["Fortnite"].refresh()

    def closeEvent(self, e):
        self.sampler.stop()
        self.pages["Netzwerk"].shutdown()
        self.sampler.wait(2500)
        super().closeEvent(e)
