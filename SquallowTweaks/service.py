"""SquallowTweaks - Hintergrunddienste (Messwerte, Ping, Tweak-Ausfuehrung). Kein Widget-Zugriff ausserhalb des UI-Threads."""
from __future__ import annotations

import os
import shutil
import threading
import time
from pathlib import Path
from typing import Callable, Optional

import psutil
from PySide6.QtCore import QObject, QRunnable, QThread, QThreadPool, Signal

import catalog
import engine as eng
import netlab

IS_WINDOWS = os.name == "nt"
APP_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".local" / "share"))) / "SquallowTweaks"
STATE_FILE = APP_DIR / "tweak_state.json"
LOG_FILE = APP_DIR / "squallow.log"
FORTNITE_EXE = "fortniteclient-win64-shipping.exe"


def log(msg: str) -> None:
    try:
        APP_DIR.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {msg}\n")
    except Exception:  # noqa: BLE001
        pass


def fmt_bytes(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


# ---------------------------------------------------------------------------
class _JobSignals(QObject):
    done = Signal(object)


class _Job(QRunnable):
    def __init__(self, fn: Callable, signals: _JobSignals):
        super().__init__()
        self.fn, self.signals = fn, signals

    def run(self):
        try:
            res = self.fn()
        except Exception as exc:  # noqa: BLE001
            log(f"job error: {exc!r}")
            res = exc
        self.signals.done.emit(res)


_keep: set = set()


def run_async(fn: Callable, on_done: Optional[Callable] = None) -> None:
    """fn laeuft im Thread-Pool, on_done im UI-Thread."""
    sig = _JobSignals()
    _keep.add(sig)

    def finish(res):
        _keep.discard(sig)
        if on_done:
            on_done(res)
    sig.done.connect(finish)
    QThreadPool.globalInstance().start(_Job(fn, sig))


# ---------------------------------------------------------------------------
class Sampler(QThread):
    """Misst jede Sekunde CPU/RAM/Disk/Netz/GPU, sucht Fortnite und setzt optional dessen Prioritaet auf HOCH."""
    sample = Signal(dict)
    procs = Signal(list)

    def __init__(self):
        super().__init__()
        self._stop = threading.Event()
        self.want_procs = False
        self.auto_high = True
        self.last_net = psutil.net_io_counters()
        self.last_t = time.time()
        self.gpu: dict = {}
        self._gpu_at = 0.0
        self._cpu_name = ""

    def stop(self):
        self._stop.set()

    def _read_gpu(self) -> dict:
        exe = shutil.which("nvidia-smi")
        if not exe:
            return {}
        code, out = eng.default_runner([exe, "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw,clocks.gr",
                                        "--format=csv,noheader,nounits"], 5)
        if code != 0 or not out:
            return {}
        parts = [x.strip() for x in out.splitlines()[0].split(",")]

        def num(i):
            try:
                return float(parts[i])
            except (ValueError, IndexError):
                return None
        return {"name": parts[0], "usage": num(1), "mem_used": num(2), "mem_total": num(3), "temp": num(4), "power": num(5), "clock": num(6)}

    def _fortnite(self) -> Optional[dict]:
        procs = []
        for p in psutil.process_iter(["name"]):
            try:
                if (p.info.get("name") or "").lower() == FORTNITE_EXE:
                    procs.append(p)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        if not procs:
            return None
        high = getattr(psutil, "HIGH_PRIORITY_CLASS", None)
        info = {"pid": procs[0].pid, "high": False, "boosted": False}
        try:
            info["ram_mb"] = procs[0].memory_info().rss / 1048576
            info["cpu"] = procs[0].cpu_percent(None) / (psutil.cpu_count() or 1)
            if high is not None:
                for p in procs:
                    try:
                        if self.auto_high and p.nice() != high:
                            p.nice(high)
                            info["boosted"] = True
                        info["high"] = p.nice() == high
                    except Exception:  # noqa: BLE001
                        pass
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
        return info

    def _collect_procs(self) -> list:
        n = psutil.cpu_count() or 1
        rows = []
        for p in psutil.process_iter(["pid", "name", "memory_info", "num_threads"]):
            try:
                i = p.info
                mem = i.get("memory_info")
                rows.append((i.get("name") or "?", int(i["pid"]), p.cpu_percent(None) / n, (mem.rss / 1048576) if mem else 0.0, i.get("num_threads") or 0))
            except Exception:  # noqa: BLE001
                continue
        return rows

    def run(self):
        psutil.cpu_percent(None)
        while not self._stop.wait(1.0):
            try:
                now = time.time()
                net = psutil.net_io_counters()
                dt = max(0.001, now - self.last_t)
                d = {"cpu": psutil.cpu_percent(None), "down": max(0, net.bytes_recv - self.last_net.bytes_recv) / dt,
                     "up": max(0, net.bytes_sent - self.last_net.bytes_sent) / dt}
                self.last_net, self.last_t = net, now
                vm = psutil.virtual_memory()
                d.update(ram=vm.percent, ram_used=vm.used, ram_total=vm.total)
                try:
                    du = psutil.disk_usage(Path.home().anchor or "/")
                    d.update(disk=du.percent, disk_free=du.free)
                except Exception:  # noqa: BLE001
                    d.update(disk=None, disk_free=0)
                if now - self._gpu_at > 3:
                    self.gpu, self._gpu_at = self._read_gpu(), now
                d["gpu"] = self.gpu
                d["fn"] = self._fortnite()
                d["uptime"] = max(0.0, now - psutil.boot_time())
                self.sample.emit(d)
                if self.want_procs:
                    self.procs.emit(self._collect_procs())
            except Exception as exc:  # noqa: BLE001
                log(f"sampler: {exc!r}")


class PingMonitor(QThread):
    result = Signal(object)   # float | None

    def __init__(self, host: str):
        super().__init__()
        self.host = host
        self._stop = threading.Event()

    def stop(self):
        self._stop.set()

    def run(self):
        while not self._stop.is_set():
            t0 = time.time()
            val = netlab.ping_once(self.host, 900)
            self.result.emit(val)
            self._stop.wait(max(0.05, 1.0 - (time.time() - t0)))


# ---------------------------------------------------------------------------
class Service(QObject):
    """Tweak-Logik fuer die UI: Status lesen, Schalter setzen, Auto-Optimize."""
    states_changed = Signal()
    tweak_done = Signal(str, bool, str)       # id, ok, Nachricht
    progress = Signal(float, str)
    auto_finished = Signal(str, list, list, str)   # Profil, Ergebnisse(ok,name,msg), uebersprungen, Aufraeum-Text

    def __init__(self):
        super().__init__()
        APP_DIR.mkdir(parents=True, exist_ok=True)
        backend = eng.WinRegBackend() if IS_WINDOWS else eng.MemoryBackend()
        self.engine = eng.TweakEngine(backend, STATE_FILE, hooks=eng.DEFAULT_HOOKS, logger=log,
                                      fortnite_running=lambda: self.fortnite_running)
        self.catalog = catalog.build_catalog()
        self.by_id = {t.id: t for t in self.catalog}
        self.states: dict[str, tuple[str, str]] = {}
        self.fortnite_running = False
        self.busy = False
        self.admin = eng.is_admin()

    # ---- Status
    def refresh_states(self):
        def work():
            out = {}
            for t in self.catalog:
                try:
                    out[t.id] = self.engine.status(t)
                except Exception as exc:  # noqa: BLE001
                    out[t.id] = (eng.STATUS_UNKNOWN, str(exc))
            return out

        def done(res):
            if isinstance(res, dict):
                self.states.update(res)
                self.states_changed.emit()
        run_async(work, done)

    def active_count(self) -> int:
        return sum(1 for s, _ in self.states.values() if s == eng.STATUS_ACTIVE)

    # ---- einzelner Schalter
    def set_tweak(self, tweak_id: str, on: bool):
        if self.busy:
            self.states_changed.emit()
            return
        t = self.by_id[tweak_id]
        self.busy = True

        def work():
            used, res = self._apply_one(t, on)
            try:
                st = self.engine.status(used)
            except Exception as exc:  # noqa: BLE001
                st = (eng.STATUS_UNKNOWN, str(exc))
            return used, res, st

        def done(r):
            self.busy = False
            if isinstance(r, Exception):
                self.tweak_done.emit(tweak_id, False, str(r))
            else:
                used, res, st = r
                self.states[used.id] = st
                self.tweak_done.emit(tweak_id, res.ok, res.message)
            self.states_changed.emit()
        run_async(work, done)

    def _apply_one(self, t, on: bool):
        if on:
            r = self.engine.apply(t)
            if not r.ok and t.id == "power_ultimate":
                fb = self.by_id["power_high"]
                r2 = self.engine.apply(fb)
                if r2.ok:
                    return fb, eng.Result(True, "Höchstleistung gesetzt (Ultimative Leistung nicht verfügbar).", True)
            return t, r
        if self.engine.has_backup(t.id):
            return t, self.engine.undo(t)
        return t, eng.Result(False, "Nicht von SquallowTweaks gesetzt, daher kein Backup zum Zurücksetzen.")

    # ---- Kontext & Auto
    def context(self) -> dict:
        try:
            battery = psutil.sensors_battery() if hasattr(psutil, "sensors_battery") else None
        except Exception:  # noqa: BLE001
            battery = None
        return {"desktop": battery is None, "fortnite_config": eng.fortnite_ini_path().exists(),
                "fortnite_running": self.fortnite_running, "admin": self.admin}

    def auto(self, profile: str = "competitive", only_fortnite: bool = False):
        if self.busy:
            return
        self.busy = True

        def work():
            ctx = self.context()
            chosen, skipped = catalog.select_for_profile(self.catalog, self.engine, ctx, profile)
            if only_fortnite:
                chosen = [t for t in chosen if t.kind == "ini" or "fso" in t.id or t.id == "fn_exe_flags"]
            chosen.sort(key=lambda x: 0 if x.kind == "power" else 1)
            results = []
            total = len(chosen) + 2
            if self.admin and chosen and not only_fortnite:
                self.progress.emit(0.04, "Wiederherstellungspunkt …")
                try:
                    eng.default_runner(["powershell.exe", "-NoProfile", "-Command",
                                        "Checkpoint-Computer -Description 'SquallowTweaks' -RestorePointType MODIFY_SETTINGS"], 90)
                except Exception as exc:  # noqa: BLE001
                    log(f"restore point: {exc}")
            for i, t in enumerate(chosen):
                self.progress.emit((i + 1) / total, t.name)
                used, r = self._apply_one(t, True)
                results.append((r.ok, used.name, r.message))
            cleaned = ""
            if not only_fortnite:
                self.progress.emit((total - 1) / total, "Aufräumen …")
                cleaned = self.cleanup()
            for t in self.catalog:
                try:
                    self.states[t.id] = self.engine.status(t)
                except Exception:  # noqa: BLE001
                    pass
            self.progress.emit(1.0, "Fertig")
            return profile, results, [(t.name, why) for t, why in skipped], cleaned

        def done(r):
            self.busy = False
            if isinstance(r, Exception):
                self.auto_finished.emit(profile, [(False, "Fehler", str(r))], [], "")
            else:
                self.auto_finished.emit(*r)
            self.states_changed.emit()
        run_async(work, done)

    def cleanup(self) -> str:
        temp = Path(os.environ.get("TEMP", str(Path.home() / "AppData/Local/Temp")))
        deleted = skipped = 0
        if temp.is_dir():
            for item in temp.iterdir():
                try:
                    if item.is_symlink():
                        skipped += 1
                    elif item.is_dir():
                        shutil.rmtree(item)
                        deleted += 1
                    else:
                        item.unlink()
                        deleted += 1
                except Exception:  # noqa: BLE001
                    skipped += 1
        ok, _ = netlab.flush_dns()
        return f"Temp: {deleted} gelöscht · DNS-Cache {'geleert' if ok else '–'}"

    def undo_all(self, on_done: Callable):
        def work():
            return self.engine.undo_all(self.catalog)

        def done(r):
            self.refresh_states()
            on_done(r)
        run_async(work, done)
