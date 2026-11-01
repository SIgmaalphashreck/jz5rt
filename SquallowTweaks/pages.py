"""SquallowTweaks - Seiten: Dashboard, Tweaks, Fortnite, Netzwerk, Prozesse, Einstellungen."""
from __future__ import annotations

import os
import platform
import webbrowser
from pathlib import Path

import psutil
from PySide6.QtCore import QAbstractTableModel, QModelIndex, QRectF, QSortFilterProxyModel, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (QAbstractItemView, QFrame, QLabel, QGridLayout, QHBoxLayout, QHeaderView, QLineEdit, QMessageBox,
                               QProgressBar, QPushButton, QScrollArea, QStyledItemDelegate, QTableView, QVBoxLayout, QWidget)

import catalog
import engine as eng
import fnmon
import netlab
import service as svc
from ui_common import (glow, ACCENT, ACCENT2, BORDER, CARD, CYAN, DIM, GREEN, MUTED, PINK, RED, TEXT, YELLOW, Card, Chips, LineChart,
                       RingGauge, StatTile, TweakRow, label, pill)


def page_layout(widget: QWidget, title: str, subtitle: str = "") -> QVBoxLayout:
    """Gemeinsames Seitengeruest: Titel + Untertitel, danach Inhalt."""
    lay = QVBoxLayout(widget)
    lay.setContentsMargins(32, 26, 32, 20)
    lay.setSpacing(14)
    head = QVBoxLayout()
    head.setSpacing(2)
    head.addWidget(label(title, "h1"))
    if subtitle:
        head.addWidget(label(subtitle, "muted"))
    lay.addLayout(head)
    return lay


def scroll_list() -> tuple[QScrollArea, QVBoxLayout]:
    area = QScrollArea()
    area.setWidgetResizable(True)
    inner = QWidget()
    lay = QVBoxLayout(inner)
    lay.setContentsMargins(0, 0, 8, 0)
    lay.setSpacing(8)
    area.setWidget(inner)
    return area, lay


# ===========================================================================
class DashboardPage(QWidget):
    def __init__(self, service: svc.Service):
        super().__init__()
        self.service = service
        lay = page_layout(self, "Dashboard", "Live-Überblick über deinen PC")
        row = QHBoxLayout()
        row.setSpacing(14)
        self.gauges: dict[str, tuple[RingGauge, QLabel]] = {}
        for key, title, c1, c2 in (("cpu", "CPU", ACCENT, CYAN), ("gpu", "GPU", CYAN, GREEN), ("ram", "RAM", PINK, ACCENT), ("disk", "LAUFWERK", YELLOW, PINK)):
            card = Card()
            v = QVBoxLayout(card)
            v.setContentsMargins(16, 14, 16, 14)
            v.addWidget(label(title, "dim"))
            g = RingGauge(c1, c2)
            v.addWidget(g, 1)
            sub = label("", "muted")
            sub.setAlignment(Qt.AlignCenter)
            v.addWidget(sub)
            self.gauges[key] = (g, sub)
            row.addWidget(card, 1)
        lay.addLayout(row)
        lower = QHBoxLayout()
        lower.setSpacing(14)
        chart_card = Card()
        cv = QVBoxLayout(chart_card)
        cv.setContentsMargins(18, 14, 18, 14)
        cv.addWidget(label("Auslastung · letzte 90 Sekunden", "h2"))
        self.chart = LineChart(100.0, "%")
        for n, c in (("CPU", ACCENT), ("GPU", CYAN), ("RAM", PINK)):
            self.chart.add_series(n, c)
        cv.addWidget(self.chart, 1)
        lower.addWidget(chart_card, 3)
        side = QVBoxLayout()
        side.setSpacing(14)
        self.net = StatTile("Netzwerk", CYAN)
        self.fn = StatTile("Fortnite", GREEN)
        self.opt = StatTile("Aktive Tweaks", ACCENT2)
        for t in (self.net, self.fn, self.opt):
            side.addWidget(t)
        lower.addLayout(side, 1)
        lay.addLayout(lower, 1)
        self.service.states_changed.connect(self._tweaks)
        self._tweaks()

    def _tweaks(self):
        total = sum(1 for t in self.service.catalog)
        self.opt.set(f"{self.service.active_count()} / {total}", "von SquallowTweaks verwaltet")

    def on_sample(self, d: dict):
        gpu = d.get("gpu") or {}
        self.gauges["cpu"][0].set_value(d["cpu"] / 100, f"{d['cpu']:.0f}%", f"{psutil.cpu_count(logical=False) or '?'} Kerne · {psutil.cpu_count()} Threads")
        gu = gpu.get("usage")
        self.gauges["gpu"][0].set_value((gu or 0) / 100, f"{gu:.0f}%" if gu is not None else "N/A", f"{gpu['temp']:.0f} °C" if gpu.get("temp") is not None else "")
        self.gauges["gpu"][1].setText(gpu.get("name", "Kein NVIDIA-Sensor"))
        self.gauges["ram"][0].set_value(d["ram"] / 100, f"{d['ram']:.0f}%", svc.fmt_bytes(d["ram_used"]))
        self.gauges["ram"][1].setText(f"von {svc.fmt_bytes(d['ram_total'])}")
        if d.get("disk") is not None:
            self.gauges["disk"][0].set_value(d["disk"] / 100, f"{d['disk']:.0f}%", "belegt")
            self.gauges["disk"][1].setText(f"{svc.fmt_bytes(d['disk_free'])} frei")
        self.gauges["cpu"][1].setText(platform.processor()[:34] or "Prozessor")
        self.chart.push("CPU", d["cpu"])
        self.chart.push("GPU", gu or 0)
        self.chart.push("RAM", d["ram"])
        self.chart.update()
        self.net.set(f"↓ {svc.fmt_bytes(d['down'])}/s", f"↑ {svc.fmt_bytes(d['up'])}/s")
        fn = d.get("fn")
        self.fn.value.setStyleSheet(f"color:{GREEN if fn else DIM};")
        self.fn.set("Läuft" if fn else "Aus", ("Priorität HOCH" if fn.get("high") else "Priorität normal") if fn else "Startet automatisch mit Priorität HOCH")


# ===========================================================================
class TweaksList(QWidget):
    """Gefilterte Liste von TweakRows (Zeilen werden einmal gebaut und nur ein-/ausgeblendet)."""

    def __init__(self, service: svc.Service, tweaks: list, with_filters: bool = True):
        super().__init__()
        self.service = service
        self.rows: dict[str, TweakRow] = {}
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        self.filter = "Alle"
        self.query = ""
        if with_filters:
            top = QHBoxLayout()
            top.setSpacing(12)
            self.search = QLineEdit()
            self.search.setPlaceholderText("Suchen …")
            self.search.setFixedWidth(220)
            self.search.textChanged.connect(self._q)
            top.addWidget(self.search)
            self.chips = Chips(["Alle", "Empfohlen", "FPS", "Latenz", "Ping", "Aktiv"])
            self.chips.changed.connect(self._f)
            top.addWidget(self.chips, 1)
            lay.addLayout(top)
        area, inner = scroll_list()
        lay.addWidget(area, 1)
        for t in tweaks:
            r = TweakRow(t, service.admin)
            r.toggled.connect(service.set_tweak)
            inner.addWidget(r)
            self.rows[t.id] = r
        inner.addStretch(1)
        self.empty = label("Keine Tweaks für diese Auswahl.", "muted")
        self.empty.setAlignment(Qt.AlignCenter)
        inner.insertWidget(0, self.empty)
        self.empty.hide()
        service.states_changed.connect(self.sync)
        self.sync()

    def _q(self, text: str):
        self.query = text.strip().lower()
        self.sync()

    def _f(self, name: str):
        self.filter = name
        self.sync()

    def sync(self):
        shown = 0
        for tid, row in self.rows.items():
            t = row.tweak
            st = self.service.states.get(tid, (eng.STATUS_UNKNOWN, ""))
            row.set_state(*st) if tid in self.service.states else None
            ok = True
            if self.filter == "Empfohlen":
                ok = bool(t.recommended)
            elif self.filter in ("FPS", "Latenz", "Ping"):
                ok = self.filter.upper() in t.tags
            elif self.filter == "Aktiv":
                ok = st[0] == eng.STATUS_ACTIVE
            if self.query and self.query not in (t.name + " " + t.description + " " + " ".join(t.tags)).lower():
                ok = False
            row.setVisible(ok)
            shown += ok
        self.empty.setVisible(shown == 0)


class TweaksPage(QWidget):
    def __init__(self, service: svc.Service):
        super().__init__()
        self.service = service
        lay = page_layout(self, "Tweaks", "Schalter umlegen, fertig. Jede Änderung wird gesichert, geprüft und lässt sich zurücknehmen.")
        hero = Card("hero")
        h = QHBoxLayout(hero)
        h.setContentsMargins(22, 18, 22, 18)
        h.setSpacing(20)
        left = QVBoxLayout()
        left.setSpacing(4)
        left.addWidget(label("Ein Klick für alles", "h2"))
        self.msg = label("Erkennt dein System und setzt alle passenden Tweaks selbst.", "muted", True)
        left.addWidget(self.msg)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setRange(0, 1000)
        self.bar.setValue(0)
        left.addSpacing(6)
        left.addWidget(self.bar)
        h.addLayout(left, 1)
        self.profile = Chips([v[0] for v in catalog.PROFILES.values()], "Competitive")
        h.addWidget(self.profile)
        self.btn = QPushButton("Auto Optimize")
        self.btn.setObjectName("accent")
        self.btn.setCursor(Qt.PointingHandCursor)
        self.btn.clicked.connect(self.run_auto)
        glow(self.btn)
        h.addWidget(self.btn)
        lay.addWidget(hero)
        self.list = TweaksList(service, service.catalog)
        lay.addWidget(self.list, 1)
        service.progress.connect(self._progress)
        service.auto_finished.connect(self._finished)

    def run_auto(self):
        key = next(k for k, v in catalog.PROFILES.items() if v[0] == self.profile.current)
        self.btn.setEnabled(False)
        self.bar.setValue(10)
        self.service.auto(key)

    def _progress(self, frac: float, text: str):
        self.bar.setValue(int(frac * 1000))
        self.msg.setText(text)

    def _finished(self, profile, results, skipped, cleaned):
        self.btn.setEnabled(True)
        ok = sum(1 for r in results if r[0])
        bad = [r for r in results if not r[0]]
        txt = f"{ok} Tweaks angewendet" if results else "Alles war schon optimal eingestellt"
        if bad:
            txt += f" · {len(bad)} fehlgeschlagen"
        restart = any(("Neustart" in (self.service.by_id[t].restart or "")) for t in self.service.by_id if self.service.engine.has_backup(t))
        if restart and ok:
            txt += " · Neustart empfohlen"
        self.msg.setText(txt + (f" · {cleaned}" if cleaned else ""))
        if bad:
            QMessageBox.warning(self, "SquallowTweaks", "Nicht alles ließ sich anwenden:\n\n" + "\n".join(f"• {n}: {m}" for _o, n, m in bad))


# ===========================================================================
class FortnitePage(QWidget):
    def __init__(self, service: svc.Service):
        super().__init__()
        self.service = service
        self.last_stats = None
        lay = page_layout(self, "Fortnite", "Config-Tweaks für FPS und Latenz · Fortnite muss dafür beendet sein")
        hero = Card("hero")
        h = QHBoxLayout(hero)
        h.setContentsMargins(22, 18, 22, 18)
        h.setSpacing(20)
        left = QVBoxLayout()
        self.state = label("", "h2")
        self.cfg = label("", "muted", True)
        left.addWidget(self.state)
        left.addWidget(self.cfg)
        h.addLayout(left, 1)
        self.btn = QPushButton("Fortnite optimieren")
        self.btn.setObjectName("accent")
        self.btn.setCursor(Qt.PointingHandCursor)
        self.btn.clicked.connect(self.optimize)
        glow(self.btn)
        h.addWidget(self.btn)
        lay.addWidget(hero)
        fn_tweaks = [t for t in service.catalog if catalog.F in t.categories]
        lay.addWidget(TweaksList(service, fn_tweaks, with_filters=False), 1)
        meas = Card()
        m = QHBoxLayout(meas)
        m.setContentsMargins(18, 14, 18, 14)
        m.setSpacing(14)
        info = QVBoxLayout()
        info.addWidget(label("Messung mit PresentMon", "h2"))
        self.meas_msg = label("FPS, 1%-Low und Ruckler aus echten Daten. Miss vor und nach dem Optimieren.", "muted", True)
        info.addWidget(self.meas_msg)
        m.addLayout(info, 1)
        self.tiles = {k: StatTile(t, c) for k, t, c in (("avg", "Ø FPS", TEXT), ("low1", "1% Low", CYAN), ("low01", "0,1% Low", PINK), ("stut", "Ruckler", YELLOW))}
        for t in self.tiles.values():
            t.setFixedWidth(120)
            m.addWidget(t)
        b = QPushButton("30 s messen")
        b.setObjectName("ghost")
        b.clicked.connect(self.measure)
        m.addWidget(b)
        lay.addWidget(meas)
        self.refresh()

    def refresh(self):
        ini = eng.fortnite_ini_path()
        self.cfg.setText("Config gefunden." if ini.exists() else "Keine GameUserSettings.ini gefunden. Starte Fortnite einmal bis ins Menü und beende es wieder.")
        self.state.setText("Fortnite läuft" if self.service.fortnite_running else "Fortnite ist beendet")
        self.state.setStyleSheet(f"color:{GREEN if self.service.fortnite_running else TEXT};")

    def optimize(self):
        if not eng.fortnite_ini_path().exists():
            QMessageBox.information(self, "SquallowTweaks", "Keine GameUserSettings.ini gefunden. Starte Fortnite einmal bis ins Menü, beende es und klicke dann erneut.")
            return
        if self.service.fortnite_running:
            if QMessageBox.question(self, "SquallowTweaks", "Fortnite läuft und muss beendet werden, sonst überschreibt es die Config.\n\nJetzt beenden und optimieren?") != QMessageBox.Yes:
                return
            for p in psutil.process_iter(["name"]):
                try:
                    if (p.info.get("name") or "").lower() == svc.FORTNITE_EXE:
                        p.terminate()
                except Exception:  # noqa: BLE001
                    pass
            self.service.fortnite_running = False
        self.btn.setEnabled(False)
        self.service.auto("competitive", only_fortnite=True)
        self.service.auto_finished.connect(self._done)

    def _done(self, *_a):
        try:
            self.service.auto_finished.disconnect(self._done)
        except (RuntimeError, TypeError):
            pass
        self.btn.setEnabled(True)
        self.cfg.setText("Fertig. Starte Fortnite jetzt normal.")

    def measure(self):
        exe = fnmon.find_presentmon()
        if not exe:
            if QMessageBox.question(self, "SquallowTweaks", "PresentMon.exe fehlt (Intel, kostenlos).\n\nLege es in den Ordner von SquallowTweaks.exe. Download-Seite öffnen?") == QMessageBox.Yes:
                webbrowser.open("https://github.com/GameTechDev/PresentMon/releases")
            return
        if not self.service.fortnite_running:
            QMessageBox.information(self, "SquallowTweaks", "Fortnite läuft nicht. Starte ein Match oder den Übungsmodus.")
            return
        self.meas_msg.setText("Messung läuft 30 s … bleib im Spiel.")
        out = svc.APP_DIR / "capture.csv"

        def work():
            ok, err = fnmon.run_capture(exe, out, 30)
            if not ok:
                return err
            return fnmon.compute_frame_stats(fnmon.parse_presentmon_csv(out))

        def done(res):
            if isinstance(res, str) or res is None or isinstance(res, Exception):
                self.meas_msg.setText("Messung fehlgeschlagen (Administratorrechte? Fortnite im Vordergrund?).")
                return
            prev = self.last_stats
            self.last_stats = res
            self.tiles["avg"].set(f"{res.avg_fps:.0f}", self._delta(res.avg_fps, prev.avg_fps if prev else None))
            self.tiles["low1"].set(f"{res.low1_fps:.0f}", self._delta(res.low1_fps, prev.low1_fps if prev else None))
            self.tiles["low01"].set(f"{res.low01_fps:.0f}", self._delta(res.low01_fps, prev.low01_fps if prev else None))
            self.tiles["stut"].set(str(res.stutters), "")
            self.meas_msg.setText(f"{res.frames} Frames in {res.duration_s:.0f} s · 99. Perzentil {res.p99_ms:.1f} ms")
        svc.run_async(work, done)

    @staticmethod
    def _delta(now: float, before) -> str:
        if before is None or before <= 0:
            return ""
        d = (now / before - 1) * 100
        return f"{d:+.0f}% zur letzten Messung"


# ===========================================================================
class NetworkPage(QWidget):
    TARGETS = {"Cloudflare": "1.1.1.1", "Google": "8.8.8.8", "Gateway": ""}

    def __init__(self, service: svc.Service):
        super().__init__()
        self.service = service
        self.monitor = None
        self._zombies: list = []
        self.samples: list = []
        self.gateway = ""
        lay = page_layout(self, "Netzwerk", "Ping-Stabilität live beobachten und verbessern")
        card = Card()
        v = QVBoxLayout(card)
        v.setContentsMargins(18, 14, 18, 14)
        top = QHBoxLayout()
        top.addWidget(label("Ping-Monitor", "h2"))
        top.addStretch(1)
        self.target = Chips(list(self.TARGETS), "Cloudflare")
        self.target.changed.connect(self._restart)
        top.addWidget(self.target)
        self.toggle_btn = QPushButton("Start")
        self.toggle_btn.setObjectName("ghost")
        self.toggle_btn.clicked.connect(self.toggle)
        top.addWidget(self.toggle_btn)
        v.addLayout(top)
        self.chart = LineChart(None, " ms", 120, show_legend=False)
        self.chart.add_series("Ping", CYAN)
        self.chart.setMinimumHeight(170)
        v.addWidget(self.chart, 1)
        lay.addWidget(card, 1)
        tiles = QHBoxLayout()
        tiles.setSpacing(14)
        self.t = {k: StatTile(n, c) for k, n, c in (("avg", "Ø Ping", TEXT), ("jit", "Jitter", CYAN), ("loss", "Verlust", YELLOW), ("max", "Maximum", PINK))}
        for x in self.t.values():
            tiles.addWidget(x)
        lay.addLayout(tiles)
        lay.addWidget(label("Ping-Stabilisierung", "h2"))
        ping_tweaks = [t for t in service.catalog if "PING" in t.tags]
        lst = TweaksList(service, ping_tweaks, with_filters=False)
        lst.setMaximumHeight(68 * len(ping_tweaks) + 10 * len(ping_tweaks))
        lay.addWidget(lst)
        self.conn = label("", "muted", True)
        lay.addWidget(self.conn)
        QTimer.singleShot(300, self.detect)

    def detect(self):
        def work():
            return netlab.get_network_config(), netlab.psutil_adapters()
        def done(r):
            if isinstance(r, Exception):
                return
            cfg, ad = r
            for c in cfg:
                if c["gateway"]:
                    self.gateway = c["gateway"][0]
                    break
            lan = [a for a in ad if a["kind"] == "LAN" and a["is_up"]]
            wifi = [a for a in ad if a["kind"] == "WLAN" and a["is_up"]]
            if lan:
                self.conn.setText("LAN verbunden · " + ", ".join(f"{a['name']} ({a['speed_mbit']} Mbit/s)" if a["speed_mbit"] else a["name"] for a in lan))
            elif wifi:
                self.conn.setText("Du nutzt WLAN. Ein LAN-Kabel ist die größte Einzelverbesserung für einen stabilen Ping.")
            else:
                self.conn.setText("Kein aktiver Netzwerkadapter erkannt.")
        svc.run_async(work, done)

    def host(self) -> str:
        t = self.target.current
        return self.gateway if t == "Gateway" else self.TARGETS[t]

    def toggle(self):
        if self.monitor:
            self.stop()
        else:
            self.start()

    def _restart(self, _n=""):
        if self.monitor:
            self.stop()
            self.start()

    def start(self):
        h = self.host()
        if not h:
            self.conn.setText("Kein Gateway erkannt. Wähle ein anderes Ziel.")
            return
        self.samples.clear()
        self.chart.clear()
        self.monitor = svc.PingMonitor(h)
        self.monitor.result.connect(self.on_ping)
        self.monitor.start()
        self.toggle_btn.setText("Stopp")

    def stop(self):
        m = self.monitor
        if m:
            m.stop()
            try:
                m.result.disconnect(self.on_ping)
            except (RuntimeError, TypeError):
                pass
            self._zombies.append(m)       # Referenz halten, bis der Thread wirklich fertig ist
            m.finished.connect(lambda mm=m: self._zombies.remove(mm) if mm in self._zombies else None)
            self.monitor = None
        self.toggle_btn.setText("Start")

    def shutdown(self):
        self.stop()
        for m in list(self._zombies):
            m.wait(4000)

    def on_ping(self, v):
        self.samples.append(v)
        self.samples = self.samples[-300:]
        self.chart.push("Ping", v)
        self.chart.update()
        ok = [x for x in self.samples if x is not None]
        if ok:
            self.t["avg"].set(f"{sum(ok) / len(ok):.0f} ms", "")
            self.t["max"].set(f"{max(ok):.0f} ms", "")
            self.t["jit"].set(f"{netlab.calc_jitter(ok) or 0:.1f} ms", "mittlere Schwankung")
        lost = len(self.samples) - len(ok)
        self.t["loss"].set(f"{100 * lost / len(self.samples):.0f}%", f"{lost} von {len(self.samples)}")


# ===========================================================================
class ProcModel(QAbstractTableModel):
    HEAD = ["PROZESS", "PID", "CPU", "RAM", "THREADS"]

    def __init__(self):
        super().__init__()
        self.rows: list = []

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return len(self.HEAD)

    def headerData(self, s, o, role=Qt.DisplayRole):
        if o == Qt.Horizontal and role == Qt.DisplayRole:
            return self.HEAD[s]
        if o == Qt.Horizontal and role == Qt.TextAlignmentRole:
            return int(Qt.AlignVCenter | (Qt.AlignLeft if s == 0 else Qt.AlignRight))
        return None

    def data(self, idx, role=Qt.DisplayRole):
        if not idx.isValid():
            return None
        r = self.rows[idx.row()]
        c = idx.column()
        if role == Qt.DisplayRole:
            return (r[0], str(r[1]), f"{r[2]:.1f}%", f"{r[3]:.0f} MB", str(r[4]))[c]
        if role == Qt.UserRole:
            return (0, 0, r[2], r[3], 0)[c]
        if role == Qt.TextAlignmentRole and c in (1, 2, 3, 4):
            return int(Qt.AlignVCenter | Qt.AlignRight)
        return None

    def set_rows(self, rows: list):
        self.beginResetModel()
        self.rows = rows
        self.endResetModel()


class BarDelegate(QStyledItemDelegate):
    def __init__(self, vmax: float, color: str, parent=None):
        super().__init__(parent)
        self.vmax, self.color = vmax, QColor(color)

    def paint(self, p: QPainter, opt, idx):
        super().paint(p, opt, idx)
        v = idx.data(Qt.UserRole) or 0.0
        frac = max(0.0, min(1.0, v / self.vmax))
        if frac <= 0.002:
            return
        r = QRectF(opt.rect)
        bar = QRectF(r.left() + 8, r.bottom() - 8, (r.width() - 16) * frac, 4)
        col = QColor(self.color)
        if frac > 0.6:
            col = QColor(RED)
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(col)
        p.drawRoundedRect(bar, 1.5, 1.5)
        p.restore()


class ProcessesPage(QWidget):
    def __init__(self, service: svc.Service):
        super().__init__()
        self.service = service
        self.all_rows: list = []
        self.sort = "cpu"
        self.filter = "Alle"
        lay = page_layout(self, "Prozesse", "Was gerade Leistung frisst")
        tiles = QHBoxLayout()
        tiles.setSpacing(14)
        self.t = {k: StatTile(n, c) for k, n, c in (("count", "Prozesse", TEXT), ("cpu", "CPU gesamt", ACCENT2), ("ram", "RAM belegt", PINK), ("top", "Größter Verbraucher", YELLOW))}
        for x in self.t.values():
            tiles.addWidget(x)
        lay.addLayout(tiles)
        bar = QHBoxLayout()
        bar.setSpacing(12)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Prozess suchen …")
        self.search.setFixedWidth(240)
        self.search.textChanged.connect(self.apply)
        bar.addWidget(self.search)
        self.chips = Chips(["Alle", "Hohe Last", "Fortnite/Epic"])
        self.chips.changed.connect(self._filter)
        bar.addWidget(self.chips)
        bar.addStretch(1)
        self.sorts = Chips(["CPU", "RAM", "Name"], "CPU")
        self.sorts.changed.connect(self._sort)
        bar.addWidget(self.sorts)
        lay.addLayout(bar)
        self.model = ProcModel()
        self.view = QTableView()
        self.view.setModel(self.model)
        self.view.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.view.setSelectionMode(QAbstractItemView.SingleSelection)
        self.view.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.view.setAlternatingRowColors(True)
        self.view.setShowGrid(False)
        self.view.verticalHeader().hide()
        self.view.verticalHeader().setDefaultSectionSize(38)
        hh = self.view.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        for c, w in ((1, 90), (2, 150), (3, 150), (4, 100)):
            hh.setSectionResizeMode(c, QHeaderView.Fixed)
            self.view.setColumnWidth(c, w)
        hh.setHighlightSections(False)
        self.view.setItemDelegateForColumn(2, BarDelegate(30.0, ACCENT, self.view))
        self.view.setItemDelegateForColumn(3, BarDelegate(2000.0, CYAN, self.view))
        lay.addWidget(self.view, 1)
        actions = QHBoxLayout()
        actions.setSpacing(10)
        kill = QPushButton("Beenden")
        kill.setObjectName("danger")
        kill.clicked.connect(self.kill)
        actions.addWidget(kill)
        for text, lvl in (("Priorität Hoch", "high"), ("Normal", "normal"), ("Niedrig", "low")):
            b = QPushButton(text)
            b.setObjectName("ghost")
            b.clicked.connect(lambda _c=False, l=lvl: self.priority(l))
            actions.addWidget(b)
        actions.addStretch(1)
        self.count = label("", "dim")
        actions.addWidget(self.count)
        lay.addLayout(actions)

    def _filter(self, n):
        self.filter = n
        self.apply()

    def _sort(self, n):
        self.sort = n.lower()
        self.apply()

    def on_procs(self, rows: list):
        self.all_rows = rows
        vm = psutil.virtual_memory()
        top = max(rows, key=lambda r: r[2], default=None)
        self.t["count"].set(str(len(rows)), "laufende Prozesse")
        self.t["cpu"].set(f"{psutil.cpu_percent(None):.0f}%", "")
        self.t["ram"].set(f"{vm.percent:.0f}%", f"{svc.fmt_bytes(vm.used)} von {svc.fmt_bytes(vm.total)}")
        if top:
            self.t["top"].set(top[0][:16], f"{top[2]:.1f}% CPU")
        self.apply()

    def apply(self, *_):
        q = self.search.text().strip().lower()
        rows = []
        for r in self.all_rows:
            n = r[0].lower()
            if q and q not in n:
                continue
            if self.filter == "Hohe Last" and not (r[2] >= 2.0 or r[3] >= 500):
                continue
            if self.filter == "Fortnite/Epic" and not any(x in n for x in ("fortnite", "epic", "easyanticheat")):
                continue
            rows.append(r)
        key = {"cpu": lambda r: -r[2], "ram": lambda r: -r[3], "name": lambda r: r[0].lower()}[self.sort]
        rows.sort(key=key)
        sel = self.selected_pid()
        sb = self.view.verticalScrollBar()
        pos = sb.value()
        self.model.set_rows(rows[:200])
        sb.setValue(pos)
        if sel is not None:
            for i, r in enumerate(self.model.rows):
                if r[1] == sel:
                    self.view.selectRow(i)
                    break
        self.count.setText(f"{min(len(rows), 200)} von {len(self.all_rows)} angezeigt")

    def selected_pid(self):
        sel = self.view.selectionModel().selectedRows() if self.view.selectionModel() else []
        return self.model.rows[sel[0].row()][1] if sel else None

    def kill(self):
        pid = self.selected_pid()
        if pid is None:
            return
        try:
            p = psutil.Process(pid)
            name = p.name()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "SquallowTweaks", f"Prozess nicht mehr verfügbar: {exc}")
            return
        protected = {"system", "registry", "smss.exe", "csrss.exe", "wininit.exe", "services.exe", "lsass.exe", "winlogon.exe", "svchost.exe", "dwm.exe", "fontdrvhost.exe"}
        if pid <= 4 or name.lower() in protected:
            QMessageBox.warning(self, "SquallowTweaks", "Dieser Windows-Systemprozess ist geschützt.")
            return
        if QMessageBox.question(self, "Prozess beenden?", f"'{name}' (PID {pid}) wirklich beenden?\nUngespeicherte Daten gehen verloren.") == QMessageBox.Yes:
            try:
                p.terminate()
            except Exception as exc:  # noqa: BLE001
                QMessageBox.warning(self, "SquallowTweaks", str(exc))

    def priority(self, level: str):
        pid = self.selected_pid()
        cls = {"high": getattr(psutil, "HIGH_PRIORITY_CLASS", None), "normal": getattr(psutil, "NORMAL_PRIORITY_CLASS", None),
               "low": getattr(psutil, "IDLE_PRIORITY_CLASS", None)}[level]
        if pid is None or cls is None:
            return
        try:
            psutil.Process(pid).nice(cls)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "SquallowTweaks", f"Priorität nicht änderbar: {exc}")


# ===========================================================================
class SettingsPage(QWidget):
    def __init__(self, service: svc.Service):
        super().__init__()
        self.service = service
        lay = page_layout(self, "Einstellungen", "Zurücksetzen, aufräumen, Infos")

        def card(title: str, text: str, buttons: list) -> Card:
            c = Card()
            row = QHBoxLayout(c)
            row.setContentsMargins(20, 16, 20, 16)
            col = QVBoxLayout()
            col.addWidget(label(title, "h2"))
            col.addWidget(label(text, "muted", True))
            row.addLayout(col, 1)
            for name, obj, fn in buttons:
                b = QPushButton(name)
                b.setObjectName(obj)
                b.clicked.connect(fn)
                row.addWidget(b)
            return c

        self.status = label("", "muted")
        lay.addWidget(card("Alles zurücksetzen", "Stellt alle von SquallowTweaks gesetzten Einstellungen auf den gesicherten Originalzustand zurück.",
                           [("Zurücksetzen", "danger", self.undo_all)]))
        lay.addWidget(card("Aufräumen", "Löscht temporäre Benutzerdateien und leert den DNS-Cache. Gesperrte Dateien werden übersprungen.",
                           [("Jetzt aufräumen", "ghost", self.cleanup)]))
        lay.addWidget(card("Daten & Log", f"Backups und Protokoll liegen in {svc.APP_DIR}.", [("Ordner öffnen", "ghost", self.open_dir)]))
        lay.addWidget(card("Rechte", "Administrator: aktiv. Alle Tweaks sind verfügbar." if service.admin else
                           "Ohne Administratorrechte sind Tweaks mit ADMIN-Label gesperrt. Starte SquallowTweaks per Rechtsklick als Administrator.", []))
        lay.addWidget(self.status)
        lay.addStretch(1)
        lay.addWidget(label("SquallowTweaks 1.0 · Änderungen sind lokal und umkehrbar. Es wird nichts an Defender, Firewall oder Anti-Cheat verändert.", "dim", True))

    def undo_all(self):
        if QMessageBox.question(self, "SquallowTweaks", "Alle Tweaks auf den Originalzustand zurücksetzen?") != QMessageBox.Yes:
            return
        self.status.setText("Setze zurück …")
        self.service.undo_all(lambda r: self.status.setText(f"Zurückgesetzt: {r[0]} · Fehler: {r[1]}" if not isinstance(r, Exception) else str(r)))

    def cleanup(self):
        self.status.setText("Räume auf …")
        svc.run_async(self.service.cleanup, lambda r: self.status.setText(str(r)))

    def open_dir(self):
        svc.APP_DIR.mkdir(parents=True, exist_ok=True)
        if svc.IS_WINDOWS:
            os.startfile(str(svc.APP_DIR))  # noqa: S606
        else:
            webbrowser.open(svc.APP_DIR.as_uri())
