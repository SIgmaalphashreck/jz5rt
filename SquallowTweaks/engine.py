"""SquallowTweaks - Tweak-Engine.

Jeder Tweak sichert vor der ersten Aenderung den Originalzustand (tweak_state.json),
liest den Wert nach dem Schreiben zurueck, rollt bei Abweichung automatisch zurueck
und ist per Undo umkehrbar. Arten: registry (HKCU/HKLM), power, powersetting,
ini (Fortnite GameUserSettings.ini) und netadapter (Ethernet-Energiespar-Funktionen).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional, Protocol

IS_WINDOWS = os.name == "nt"

REG_SZ, REG_BINARY, REG_DWORD = 1, 3, 4

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APPROVED_KEY = r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"



# --------------------------------------------------------------------------
# Registry-Backends
# --------------------------------------------------------------------------
class RegBackend(Protocol):
    def read(self, path: str, name: str) -> tuple[bool, Optional[int], object]: ...
    def write(self, path: str, name: str, rtype: int, value: object) -> None: ...
    def delete(self, path: str, name: str) -> None: ...
    def enum(self, path: str) -> list[tuple[str, object, int]]: ...


class WinRegBackend:
    """HKEY_CURRENT_USER; Pfade mit Praefix 'HKLM\\' gehen nach HKEY_LOCAL_MACHINE (Adminrechte noetig).
    Nur unter Windows nutzbar."""

    def __init__(self):
        import winreg  # noqa: PLC0415
        self.w = winreg

    def _root(self, path):
        if path.upper().startswith("HKLM\\"):
            return self.w.HKEY_LOCAL_MACHINE, path[5:]
        return self.w.HKEY_CURRENT_USER, path

    def read(self, path, name):
        root, sub = self._root(path)
        try:
            with self.w.OpenKey(root, sub, 0, self.w.KEY_READ) as key:
                value, rtype = self.w.QueryValueEx(key, name)
                return True, int(rtype), value
        except OSError:
            return False, None, None

    def write(self, path, name, rtype, value):
        root, sub = self._root(path)
        with self.w.CreateKeyEx(root, sub, 0, self.w.KEY_SET_VALUE) as key:
            self.w.SetValueEx(key, name, 0, rtype, value)

    def delete(self, path, name):
        root, sub = self._root(path)
        try:
            with self.w.OpenKey(root, sub, 0, self.w.KEY_SET_VALUE) as key:
                self.w.DeleteValue(key, name)
        except FileNotFoundError:
            pass

    def enum(self, path):
        root, sub = self._root(path)
        out = []
        try:
            with self.w.OpenKey(root, sub, 0, self.w.KEY_READ) as key:
                i = 0
                while True:
                    try:
                        n, v, t = self.w.EnumValue(key, i)
                    except OSError:
                        break
                    out.append((n, v, int(t)))
                    i += 1
        except OSError:
            pass
        return out

    def subkeys(self, path):
        root, sub = self._root(path)
        out = []
        try:
            with self.w.OpenKey(root, sub, 0, self.w.KEY_READ) as key:
                i = 0
                while True:
                    try:
                        out.append(self.w.EnumKey(key, i))
                    except OSError:
                        break
                    i += 1
        except OSError:
            pass
        return out


class MemoryBackend:
    """Fake-Registry fuer Tests (Namen wie in Windows: case-insensitiv, Schreibweise bleibt erhalten)."""

    def __init__(self):
        self.data: dict[tuple[str, str], tuple[str, int, object]] = {}

    def read(self, path, name):
        item = self.data.get((path.lower(), name.lower()))
        return (True, item[1], item[2]) if item else (False, None, None)

    def write(self, path, name, rtype, value):
        self.data[(path.lower(), name.lower())] = (name, rtype, value)

    def delete(self, path, name):
        self.data.pop((path.lower(), name.lower()), None)

    def enum(self, path):
        return [(v[0], v[2], v[1]) for k, v in self.data.items() if k[0] == path.lower()]

    def subkeys(self, path):
        prefix = path.lower() + "\\"
        seen: dict[str, str] = {}
        for (p, _n), _v in self.data.items():
            if p.startswith(prefix):
                seg = p[len(prefix):].split("\\")[0]
                seen.setdefault(seg, seg)
        return list(seen)


def read_hklm(path: str, name: str):
    """Reiner Lesezugriff auf HKLM (fuer Statusanzeigen)."""
    if not IS_WINDOWS:
        return None
    try:
        import winreg  # noqa: PLC0415
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path, 0, winreg.KEY_READ) as key:
            return winreg.QueryValueEx(key, name)[0]
    except OSError:
        return None


# --------------------------------------------------------------------------
# Datenmodell
# --------------------------------------------------------------------------
@dataclass
class RegValue:
    path: str
    name: str
    rtype: int
    value: object


@dataclass
class Tweak:
    id: str
    name: str
    categories: list[str]
    description: str
    impact: str                      # Erklaerung der Auswirkungen / Nebenwirkungen
    kind: str = "registry"           # registry | power | action | info
    values: list[RegValue] = field(default_factory=list)
    restart: str = "Nein"            # Hinweis zur Wirksamkeit
    hook: str = ""                   # z. B. "mouse_live"
    power_target: str = ""           # high | ultimate
    action_id: str = ""              # fuer kind == action
    action_label: str = "Ausfuehren"
    info_text: str = ""              # fuer kind == info
    status_fn: Optional[Callable[[], str]] = None
    open_uri: str = ""               # Button-Ziel fuer info-Karten
    open_label: str = ""
    ps_sub: str = ""                 # powersetting: Untergruppe (Alias oder GUID)
    ps_setting: str = ""             # powersetting: Einstellung (Alias oder GUID)
    ps_value: int = 0                # powersetting: Zielwert (Netzbetrieb)
    ini_section: str = ""            # ini: Abschnitt in GameUserSettings.ini
    ini_values: dict = field(default_factory=dict)
    recommended: str = ""            # "" | baseline | desktop | fortnite  (fuer 'Best Tweaks')
    why: str = ""                    # Kurzbegruendung fuer die Empfehlung
    admin: bool = False              # braucht Administratorrechte (HKLM)
    dynamic: Optional[Callable] = None   # liefert RegValue-Liste zur Laufzeit (z. B. GPU-Geraete)
    tags: tuple = ()                 # Kurzlabels fuer die UI: FPS, LATENZ, PING, FRAMETIME
    risk: str = "niedrig"            # niedrig | mittel
    adapter_props: dict = field(default_factory=dict)  # netadapter: {RegistryKeyword: Zielwert}


TOGGLE_KINDS = ("registry", "power", "powersetting", "ini", "netadapter")


@dataclass
class Result:
    ok: bool
    message: str
    verified: bool = False


STATUS_ACTIVE, STATUS_INACTIVE, STATUS_PARTIAL, STATUS_UNKNOWN = "aktiv", "nicht aktiv", "teilweise", "unbekannt"


def _same(a, b) -> bool:
    if isinstance(a, (bytes, bytearray)) or isinstance(b, (bytes, bytearray)):
        return bytes(a or b"") == bytes(b or b"")
    if isinstance(a, int) or isinstance(b, int):
        try:
            return int(a) == int(b)
        except (TypeError, ValueError):
            return False
    return str(a) == str(b)


def _enc(v):
    import base64
    return {"__bytes__": base64.b64encode(bytes(v)).decode("ascii")} if isinstance(v, (bytes, bytearray)) else v


def _dec(v):
    import base64
    return base64.b64decode(v["__bytes__"]) if isinstance(v, dict) and "__bytes__" in v else v


GUID_RE = re.compile(r"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})")
HIGH_PERF_GUID = "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"
ULTIMATE_SRC_GUID = "e9a42b02-d5df-448d-aa00-03f14749eb61"


def is_admin() -> bool:
    if not IS_WINDOWS:
        return True
    try:
        import ctypes  # noqa: PLC0415
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:  # noqa: BLE001
        return False


def default_runner(args: list[str], timeout: int = 12) -> tuple[int, str]:
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if IS_WINDOWS else 0
    try:
        p = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=timeout, shell=False, creationflags=flags)
        return p.returncode, ((p.stdout or "") + (p.stderr or "")).strip()
    except Exception as exc:  # noqa: BLE001
        return 1, str(exc)


# --------------------------------------------------------------------------
# INI-Hilfen (Fortnite GameUserSettings.ini)
# --------------------------------------------------------------------------
def fortnite_ini_path() -> Path:
    base = os.environ.get("LOCALAPPDATA", str(Path.home()))
    return Path(base) / "FortniteGame" / "Saved" / "Config" / "WindowsClient" / "GameUserSettings.ini"


def _ini_load(path: Path) -> tuple[list[str], str, bool]:
    raw = path.read_bytes()
    bom = raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8-sig", errors="replace")
    eol = "\r\n" if "\r\n" in text else "\n"
    return text.splitlines(keepends=True), eol, bom


def _ini_store(path: Path, lines: list[str], bom: bool) -> None:
    data = "".join(lines).encode("utf-8")
    path.write_bytes((b"\xef\xbb\xbf" if bom else b"") + data)


def _section_bounds(lines: list[str], section: str) -> Optional[tuple[int, int]]:
    start = None
    for i, ln in enumerate(lines):
        st = ln.strip()
        if st.lower() == f"[{section}]".lower():
            start = i
        elif start is not None and st.startswith("["):
            return start, i
    return (start, len(lines)) if start is not None else None


FORT_SECTION = "/Script/FortniteGame.FortGameUserSettings"


def _sk(t, key: str) -> tuple[str, str]:
    """ini_values-Schluessel 'Abschnitt|Name' -> (Abschnitt, Name); ohne Praefix gilt t.ini_section."""
    if "|" in key:
        sec, name = key.split("|", 1)
        return sec, name
    return t.ini_section, key


def ini_read(path: Path, section: str, key: str) -> Optional[str]:
    if not path.exists():
        return None
    lines, _, _ = _ini_load(path)
    b = _section_bounds(lines, section)
    if not b:
        return None
    for ln in lines[b[0] + 1:b[1]]:
        k, sep, v = ln.partition("=")
        if sep and k.strip().lower() == key.lower():
            return v.strip()
    return None


def ini_write(path: Path, section: str, key: str, value: Optional[str]) -> None:
    """Setzt (oder loescht bei None) einen Schluessel; alle anderen Zeilen bleiben unveraendert."""
    lines, eol, bom = _ini_load(path)
    b = _section_bounds(lines, section)
    if b is None:
        if value is None:
            return
        if lines and not lines[-1].endswith(("\n", "\r")):
            lines[-1] += eol
        lines += [f"[{section}]{eol}", f"{key}={value}{eol}"]
        _ini_store(path, lines, bom)
        return
    for i in range(b[0] + 1, b[1]):
        k, sep, _ = lines[i].partition("=")
        if sep and k.strip().lower() == key.lower():
            if value is None:
                del lines[i]
            else:
                lines[i] = f"{k.rstrip()}={value}{eol}"
            _ini_store(path, lines, bom)
            return
    if value is None:
        return
    insert_at = b[1]
    while insert_at - 1 > b[0] and not lines[insert_at - 1].strip():
        insert_at -= 1
    if insert_at > 0 and not lines[insert_at - 1].endswith(("\n", "\r")):
        lines[insert_at - 1] += eol
    lines.insert(insert_at, f"{key}={value}{eol}")
    _ini_store(path, lines, bom)


def _same_text(a: Optional[str], b: Optional[str]) -> bool:
    if a is None or b is None:
        return a is b
    try:
        return abs(float(a) - float(b)) < 1e-6
    except ValueError:
        return a.strip().lower() == b.strip().lower()


# --------------------------------------------------------------------------
# Engine
# --------------------------------------------------------------------------
class TweakEngine:
    def __init__(self, backend: RegBackend, state_path: Path,
                 runner: Callable[[list[str]], tuple[int, str]] = default_runner,
                 hooks: Optional[dict[str, Callable[[RegBackend], None]]] = None,
                 logger: Callable[[str], None] = lambda m: None,
                 ini_path: Optional[Path] = None,
                 fortnite_running: Callable[[], bool] = lambda: False,
                 admin_check: Optional[Callable[[], bool]] = None):
        self.admin_check = admin_check if admin_check is not None else is_admin
        self.ini_path = ini_path if ini_path is not None else fortnite_ini_path()
        self.fortnite_running = fortnite_running
        self.backend = backend
        self.state_path = state_path
        self.runner = runner
        self.hooks = hooks if hooks is not None else {}
        self.log = logger
        self.state: dict = {}
        self._load()

    # ---- Zustand -------------------------------------------------------
    def _load(self):
        try:
            if self.state_path.exists():
                data = json.loads(self.state_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    self.state = data
        except Exception as exc:  # noqa: BLE001
            self.log(f"Tweak-State lesen fehlgeschlagen: {exc}")

    def _save(self):
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.state, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.state_path)

    def has_backup(self, tweak_id: str) -> bool:
        return tweak_id in self.state

    def _vals(self, t: Tweak) -> list:
        if t.dynamic is not None:
            try:
                return list(t.dynamic(self.backend))
            except Exception as exc:  # noqa: BLE001
                self.log(f"dynamic {t.id}: {exc}")
                return []
        return t.values

    # ---- Status ----------------------------------------------------------
    def status(self, t: Tweak) -> tuple[str, str]:
        try:
            if t.kind == "registry":
                vals = self._vals(t)
                if not vals:
                    return STATUS_UNKNOWN, "Kein passendes Geraet/Eintrag auf diesem System gefunden."
                matches = 0
                for v in vals:
                    exists, _, cur = self.backend.read(v.path, v.name)
                    if exists and _same(cur, v.value):
                        matches += 1
                if matches == len(vals):
                    return STATUS_ACTIVE, "Alle Werte entsprechen dem Tweak."
                if matches == 0:
                    return STATUS_INACTIVE, "Standard bzw. unveraendert."
                return STATUS_PARTIAL, f"{matches}/{len(vals)} Werte gesetzt."
            if t.kind == "power":
                cur = self._active_guid()
                if cur is None:
                    return STATUS_UNKNOWN, "Aktiver Energieplan nicht lesbar."
                if t.power_target == "high":
                    return (STATUS_ACTIVE, "Höchstleistung ist aktiv.") if cur.lower() == HIGH_PERF_GUID \
                        else (STATUS_INACTIVE, "Anderer Energieplan aktiv.")
                made = self.state.get(t.id, {}).get("created_scheme")
                if made and cur.lower() == made.lower():
                    return STATUS_ACTIVE, "Ultimative Leistung ist aktiv."
                return STATUS_INACTIVE, "Anderer Energieplan aktiv."
            if t.kind == "powersetting":
                cur = self._ps_query(self._active_guid() or "SCHEME_CURRENT", t)
                if cur is None:
                    return STATUS_UNKNOWN, "Einstellung auf diesem System nicht verfügbar."
                return (STATUS_ACTIVE, f"Wert {cur} (Ziel {t.ps_value}).") if cur == t.ps_value \
                    else (STATUS_INACTIVE, f"Aktueller Wert {cur}, Ziel {t.ps_value}.")
            if t.kind == "ini":
                if not self.ini_path.exists():
                    return STATUS_UNKNOWN, "Fortnite-Config nicht gefunden (Fortnite einmal starten)."
                hits = sum(1 for k, v in t.ini_values.items() if _same_text(ini_read(self.ini_path, *_sk(t, k)), str(v)))
                if hits == len(t.ini_values):
                    return STATUS_ACTIVE, "Werte stehen in der Config."
                return (STATUS_INACTIVE, "Standard bzw. andere Werte.") if hits == 0 else (STATUS_PARTIAL, f"{hits}/{len(t.ini_values)} Werte.")
            if t.kind == "netadapter":
                return self._na_status(t)
        except Exception as exc:  # noqa: BLE001
            return STATUS_UNKNOWN, str(exc)
        return STATUS_UNKNOWN, ""

    # ---- Apply -----------------------------------------------------------
    def apply(self, t: Tweak) -> Result:
        if t.admin and not self.admin_check():
            return Result(False, "Administratorrechte nötig: SquallowTweaks als Administrator starten.")
        if t.kind == "registry":
            return self._apply_registry(t)
        if t.kind == "power":
            return self._apply_power(t)
        if t.kind == "powersetting":
            return self._apply_powersetting(t)
        if t.kind == "ini":
            return self._apply_ini(t)
        if t.kind == "netadapter":
            return self._apply_netadapter(t)
        return Result(False, "Dieser Eintrag ist keine aenderbare Einstellung.")

    def _apply_registry(self, t: Tweak) -> Result:
        vals = self._vals(t)
        if not vals:
            return Result(False, "Kein passendes Geraet/Eintrag auf diesem System gefunden.")
        if t.id not in self.state:
            originals = []
            for v in vals:
                exists, rtype, val = self.backend.read(v.path, v.name)
                originals.append({"path": v.path, "name": v.name, "existed": exists,
                                  "type": rtype, "value": _enc(val)})
            self.state[t.id] = {"registry": originals, "saved_at": datetime.now().isoformat(timespec="seconds")}
            self._save()  # Backup MUSS vor der ersten Aenderung auf der Platte liegen
        try:
            for v in vals:
                self.backend.write(v.path, v.name, v.rtype, v.value)
            self._run_hook(t)
        except Exception as exc:  # noqa: BLE001
            self.log(f"Apply {t.id} Fehler: {exc}")
            self.undo(t)
            return Result(False, f"Schreiben fehlgeschlagen, Original wiederhergestellt: {exc}")
        bad = []
        for v in vals:
            exists, _, cur = self.backend.read(v.path, v.name)
            if not (exists and _same(cur, v.value)):
                bad.append(v.name)
        if bad:
            self.undo(t)
            return Result(False, f"Verifikation fehlgeschlagen ({', '.join(bad)}). Original wurde wiederhergestellt.")
        self.log(f"Tweak angewendet: {t.id}")
        note = f" Wirksam: {t.restart}." if t.restart and t.restart != "Nein" else ""
        return Result(True, "Angewendet und per Rücklesen verifiziert." + note, verified=True)

    def _run_hook(self, t: Tweak):
        if t.hook and t.hook in self.hooks:
            self.hooks[t.hook](self.backend)

    def _active_guid(self) -> Optional[str]:
        code, out = self.runner(["powercfg", "/getactivescheme"])
        m = GUID_RE.search(out)
        return m.group(1) if code == 0 and m else None

    def _apply_power(self, t: Tweak) -> Result:
        current = self._active_guid()
        if not current:
            return Result(False, "Aktiver Energieplan konnte nicht gelesen werden.")
        entry = self.state.setdefault(t.id, {})
        entry.setdefault("power_plan", current)
        entry.setdefault("saved_at", datetime.now().isoformat(timespec="seconds"))
        self._save()
        if t.power_target == "high":
            target = HIGH_PERF_GUID
            code, out = self.runner(["powercfg", "/setactive", "SCHEME_MIN"])
            if code != 0:
                self._drop_if_unchanged(t.id, current)
                return Result(False, f"Energieplan 'Höchstleistung' nicht verfügbar: {out[:200]}")
        else:
            code, out = self.runner(["powercfg", "-duplicatescheme", ULTIMATE_SRC_GUID])
            m = GUID_RE.search(out)
            if code != 0 or not m:
                self._drop_if_unchanged(t.id, current)
                return Result(False, f"'Ultimative Leistung' nicht verfügbar auf diesem System: {out[:200]}")
            target = m.group(1)
            entry["created_scheme"] = target
            self._save()
            code, out = self.runner(["powercfg", "/setactive", target])
            if code != 0:
                self.runner(["powercfg", "/delete", target])
                self._drop_if_unchanged(t.id, current)
                return Result(False, f"Aktivieren fehlgeschlagen: {out[:200]}")
        now = self._active_guid()
        if not now or now.lower() != target.lower():
            self.undo(t)
            return Result(False, "Verifikation fehlgeschlagen: Energieplan ist nicht aktiv. Zurückgesetzt.")
        return Result(True, "Energieplan gesetzt und verifiziert. Mehr Verbrauch/Wärme möglich; FPS-Gewinn nicht garantiert.", True)

    # ---- powercfg-Einzeleinstellungen ----------------------------------
    def _ps_query(self, scheme: str, t: Tweak) -> Optional[int]:
        code, out = self.runner(["powercfg", "/query", scheme, t.ps_sub, t.ps_setting])
        hexes = re.findall(r"0x[0-9a-fA-F]{1,8}", out)
        if code != 0 or len(hexes) < 2:
            return None
        return int(hexes[-2], 16)  # die letzten zwei Werte sind AC und DC

    def _apply_powersetting(self, t: Tweak) -> Result:
        scheme = self._active_guid()
        if not scheme:
            return Result(False, "Aktiver Energieplan konnte nicht gelesen werden.")
        orig = self._ps_query(scheme, t)
        if orig is None:
            return Result(False, "Diese Energieeinstellung ist auf diesem System nicht verfügbar.")
        if t.id not in self.state:
            self.state[t.id] = {"scheme": scheme, "ac_orig": orig, "saved_at": datetime.now().isoformat(timespec="seconds")}
            self._save()
        scheme = self.state[t.id]["scheme"]
        code, out = self.runner(["powercfg", "/setacvalueindex", scheme, t.ps_sub, t.ps_setting, str(t.ps_value)])
        if code == 0:
            code, out = self.runner(["powercfg", "/setactive", scheme])
        if code != 0 or self._ps_query(scheme, t) != t.ps_value:
            self._undo_powersetting(t, self.state[t.id])
            return Result(False, f"Verifikation fehlgeschlagen oder Fehler: {out[:160]}. Zurückgesetzt.")
        return Result(True, "Gesetzt und per powercfg verifiziert (Netzbetrieb).", True)

    def _undo_powersetting(self, t: Tweak, entry: dict) -> Result:
        scheme, orig = entry["scheme"], int(entry["ac_orig"])
        code, out = self.runner(["powercfg", "/setacvalueindex", scheme, t.ps_sub, t.ps_setting, str(orig)])
        if code == 0:
            code, out = self.runner(["powercfg", "/setactive", scheme])
        if code != 0 or self._ps_query(scheme, t) != orig:
            return Result(False, f"Zurücksetzen nicht verifiziert: {out[:160]}. Backup bleibt erhalten.")
        self.state.pop(t.id, None)
        self._save()
        return Result(True, "Originalwert wiederhergestellt und verifiziert.", True)

    # ---- Fortnite-INI ----------------------------------------------------
    def _apply_ini(self, t: Tweak) -> Result:
        if self.fortnite_running():
            return Result(False, "Fortnite läuft. Beende das Spiel zuerst, sonst überschreibt es die Datei beim Beenden.")
        if not self.ini_path.exists():
            return Result(False, "GameUserSettings.ini nicht gefunden. Starte Fortnite einmal, damit sie erzeugt wird.")
        if t.id not in self.state:
            originals = {k: ini_read(self.ini_path, *_sk(t, k)) for k in t.ini_values}
            backup_dir = self.state_path.parent / "config_backups"
            backup_dir.mkdir(parents=True, exist_ok=True)
            copy = backup_dir / f"GameUserSettings.{datetime.now():%Y%m%d-%H%M%S}.ini"
            shutil.copy2(self.ini_path, copy)
            self.state[t.id] = {"ini": originals, "file_copy": str(copy), "saved_at": datetime.now().isoformat(timespec="seconds")}
            self._save()
        try:
            for k, v in t.ini_values.items():
                ini_write(self.ini_path, *_sk(t, k), str(v))
        except OSError as exc:
            self._undo_ini(t, self.state[t.id])
            return Result(False, f"Schreiben fehlgeschlagen: {exc}")
        bad = [k for k, v in t.ini_values.items() if not _same_text(ini_read(self.ini_path, *_sk(t, k)), str(v))]
        if bad:
            self._undo_ini(t, self.state[t.id])
            return Result(False, f"Verifikation fehlgeschlagen ({', '.join(bad)}). Zurückgesetzt.")
        return Result(True, "In GameUserSettings.ini geschrieben (Kopie der Datei gesichert). Ob Fortnite den Wert übernimmt, siehst du im Spiel.", True)

    def _undo_ini(self, t: Tweak, entry: dict) -> Result:
        if self.fortnite_running():
            return Result(False, "Fortnite läuft. Beende das Spiel zuerst.")
        try:
            for k, v in entry.get("ini", {}).items():
                ini_write(self.ini_path, *_sk(t, k), v)
        except OSError as exc:
            return Result(False, f"Zurücksetzen fehlgeschlagen: {exc}")
        bad = [k for k, v in entry.get("ini", {}).items() if not _same_text(ini_read(self.ini_path, *_sk(t, k)), v)]
        if bad:
            return Result(False, f"Zurücksetzen unvollständig: {', '.join(bad)}. Backup-Kopie: {entry.get('file_copy')}")
        self.state.pop(t.id, None)
        self._save()
        return Result(True, "Originalwerte wiederhergestellt und verifiziert.", True)


    # ---- Netzwerkadapter (Ethernet-Energiespar-Funktionen) ---------------
    @staticmethod
    def _psq(value: str) -> str:
        return "'" + str(value).replace("'", "''") + "'"

    def _ps_json(self, script: str, timeout: int = 25):
        code, out = self.runner(["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                                 "-Command", "$ErrorActionPreference='Stop';" + script], timeout)
        if code != 0:
            return None
        out = out.strip().lstrip("\ufeff")
        if not out:
            return []
        try:
            data = json.loads(out)
        except json.JSONDecodeError:
            return None
        return data if isinstance(data, list) else [data]

    def _na_adapters(self) -> list[str]:
        rows = self._ps_json("Get-NetAdapter -Physical | Where-Object { $_.Status -eq 'Up' -and $_.PhysicalMediaType -match '802.3' } "
                             "| ForEach-Object { [pscustomobject]@{Name=$_.Name} } | ConvertTo-Json -Compress")
        return [r["Name"] for r in rows or [] if isinstance(r, dict) and r.get("Name")]

    def _na_read(self, name: str) -> Optional[dict]:
        rows = self._ps_json(f"Get-NetAdapterAdvancedProperty -Name {self._psq(name)} | ForEach-Object "
                             "{ [pscustomobject]@{K=$_.RegistryKeyword;V=[string]$_.RegistryValue} } | ConvertTo-Json -Compress")
        if rows is None:
            return None
        return {r["K"]: str(r["V"]) for r in rows if isinstance(r, dict) and r.get("K")}

    def _na_set(self, name: str, keyword: str, value: str) -> bool:
        code, _ = self.runner(["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command",
                               f"Set-NetAdapterAdvancedProperty -Name {self._psq(name)} -RegistryKeyword {self._psq(keyword)} "
                               f"-RegistryValue {self._psq(value)} -NoRestart"], 30)
        return code == 0

    def _na_plan(self, t: Tweak) -> list[tuple[str, str, str, str]]:
        """[(Adapter, Keyword, Istwert, Zielwert)] nur fuer Keywords, die der Treiber wirklich anbietet."""
        plan = []
        for name in self._na_adapters():
            props = self._na_read(name)
            if not props:
                continue
            for kw, target in t.adapter_props.items():
                if kw in props:
                    plan.append((name, kw, props[kw], str(target)))
        return plan

    def _na_status(self, t: Tweak) -> tuple[str, str]:
        plan = self._na_plan(t)
        if not plan:
            return STATUS_UNKNOWN, "Kein LAN-Adapter mit diesen Einstellungen gefunden."
        hits = sum(1 for _n, _k, cur, tgt in plan if cur == tgt)
        if hits == len(plan):
            return STATUS_ACTIVE, f"{len(plan)} Adapter-Einstellungen gesetzt."
        return (STATUS_INACTIVE, "Standard.") if hits == 0 else (STATUS_PARTIAL, f"{hits}/{len(plan)} gesetzt.")

    def _apply_netadapter(self, t: Tweak) -> Result:
        plan = self._na_plan(t)
        if not plan:
            return Result(False, "Kein verbundener LAN-Adapter mit passenden Einstellungen gefunden (WLAN wird nicht verändert).")
        if t.id not in self.state:
            self.state[t.id] = {"adapter": [{"name": n, "keyword": k, "value": cur} for n, k, cur, _t in plan],
                                "saved_at": datetime.now().isoformat(timespec="seconds")}
            self._save()
        for name, kw, _cur, tgt in plan:
            if not self._na_set(name, kw, tgt):
                self._undo_netadapter(t, self.state[t.id])
                return Result(False, f"Setzen fehlgeschlagen ({kw}). Zurückgesetzt.")
        bad = [kw for name, kw, _c, tgt in plan if (self._na_read(name) or {}).get(kw) != tgt]
        if bad:
            self._undo_netadapter(t, self.state[t.id])
            return Result(False, f"Verifikation fehlgeschlagen ({', '.join(bad)}). Zurückgesetzt.")
        return Result(True, "Gesetzt und verifiziert. Die Verbindung kann kurz (1–3 s) unterbrochen sein.", True)

    def _undo_netadapter(self, t: Tweak, entry: dict) -> Result:
        failed = [r["keyword"] for r in entry.get("adapter", []) if not self._na_set(r["name"], r["keyword"], r["value"])]
        bad = [r["keyword"] for r in entry.get("adapter", []) if (self._na_read(r["name"]) or {}).get(r["keyword"]) != r["value"]]
        if failed or bad:
            return Result(False, f"Zurücksetzen unvollständig: {', '.join(failed + bad)}. Backup bleibt erhalten.")
        self.state.pop(t.id, None)
        self._save()
        return Result(True, "Originalwerte wiederhergestellt und verifiziert.", True)

    def _drop_if_unchanged(self, tid: str, current: str):
        entry = self.state.get(tid, {})
        if entry.get("power_plan") == current and not entry.get("created_scheme"):
            self.state.pop(tid, None)
            self._save()

    # ---- Undo ------------------------------------------------------------
    def undo(self, t: Tweak) -> Result:
        entry = self.state.get(t.id)
        if not entry:
            return Result(False, "Kein Backup vorhanden: dieser Tweak wurde nicht von SquallowTweaks angewendet, daher gibt es nichts zurückzusetzen.")
        if t.kind == "registry":
            return self._undo_registry(t, entry)
        if t.kind == "power":
            return self._undo_power(t, entry)
        if t.kind == "powersetting":
            return self._undo_powersetting(t, entry)
        if t.kind == "ini":
            return self._undo_ini(t, entry)
        if t.kind == "netadapter":
            return self._undo_netadapter(t, entry)
        return Result(False, "Nicht umkehrbar.")

    def _undo_registry(self, t: Tweak, entry: dict) -> Result:
        failed = []
        for rec in entry.get("registry", []):
            try:
                if rec["existed"]:
                    self.backend.write(rec["path"], rec["name"], int(rec["type"]), _dec(rec["value"]))
                else:
                    self.backend.delete(rec["path"], rec["name"])
            except Exception as exc:  # noqa: BLE001
                failed.append(f"{rec['name']}: {exc}")
        try:
            self._run_hook(t)
        except Exception as exc:  # noqa: BLE001
            self.log(f"Hook nach Undo {t.id}: {exc}")
        bad = []
        for rec in entry.get("registry", []):
            exists, _, cur = self.backend.read(rec["path"], rec["name"])
            if rec["existed"]:
                if not (exists and _same(cur, _dec(rec["value"]))):
                    bad.append(rec["name"])
            elif exists:
                bad.append(rec["name"])
        if failed or bad:
            return Result(False, f"Zurücksetzen unvollständig: {', '.join(failed + bad)}. Backup bleibt erhalten.")
        self.state.pop(t.id, None)
        self._save()
        self.log(f"Tweak zurückgesetzt: {t.id}")
        return Result(True, "Originalzustand wiederhergestellt und verifiziert.", True)

    def _undo_power(self, t: Tweak, entry: dict) -> Result:
        orig = entry.get("power_plan")
        if not orig:
            return Result(False, "Kein ursprünglicher Energieplan gesichert.")
        code, out = self.runner(["powercfg", "/setactive", orig])
        if code != 0:
            return Result(False, f"Ursprünglicher Plan konnte nicht aktiviert werden: {out[:200]}")
        now = self._active_guid()
        if not now or now.lower() != orig.lower():
            return Result(False, "Verifikation fehlgeschlagen: ursprünglicher Plan ist nicht aktiv.")
        made = entry.get("created_scheme")
        if made:
            self.runner(["powercfg", "/delete", made])
        self.state.pop(t.id, None)
        self._save()
        return Result(True, "Ursprünglicher Energieplan wieder aktiv (verifiziert).", True)

    def undo_all(self, tweaks: list[Tweak]) -> tuple[int, int]:
        ok = bad = 0
        for t in tweaks:
            if t.id in self.state:
                r = self.undo(t)
                ok += 1 if r.ok else 0
                bad += 0 if r.ok else 1
        return ok, bad


# --------------------------------------------------------------------------
# Autostart (HKCU Run + StartupApproved - exakt wie der Task-Manager)
# --------------------------------------------------------------------------
@dataclass
class StartupEntry:
    name: str
    command: str
    enabled: bool


def list_startup(backend: RegBackend) -> list[StartupEntry]:
    entries = []
    approved = {n.lower(): v for n, v, _ in backend.enum(APPROVED_KEY)}
    for name, value, rtype in backend.enum(RUN_KEY):
        flag = approved.get(name.lower())
        disabled = bool(flag) and isinstance(flag, (bytes, bytearray)) and len(flag) > 0 and flag[0] % 2 == 1
        entries.append(StartupEntry(name, str(value), not disabled))
    return sorted(entries, key=lambda e: e.name.lower())


def set_startup_enabled(backend: RegBackend, name: str, enabled: bool) -> Result:
    flag = (b"\x02" if enabled else b"\x03") + b"\x00" * 11
    try:
        backend.write(APPROVED_KEY, name, REG_BINARY, flag)
    except Exception as exc:  # noqa: BLE001
        return Result(False, f"Fehlgeschlagen: {exc}")
    now = next((e for e in list_startup(backend) if e.name == name), None)
    if now is None or now.enabled != enabled:
        return Result(False, "Verifikation fehlgeschlagen.")
    return Result(True, ("Autostart aktiviert" if enabled else "Autostart deaktiviert") + " (verifiziert). Der Eintrag bleibt erhalten und kann jederzeit umgeschaltet werden.", True)


# --------------------------------------------------------------------------
# Live-Hooks
# --------------------------------------------------------------------------
def mouse_live_hook(backend: RegBackend) -> None:
    """Uebernimmt die Maus-Registry-Werte sofort (ohne Neuanmeldung)."""
    if not IS_WINDOWS:
        return
    import ctypes  # noqa: PLC0415

    def val(name: str) -> int:
        exists, _, v = backend.read(r"Control Panel\Mouse", name)
        try:
            return int(v) if exists else 0
        except (TypeError, ValueError):
            return 0

    arr = (ctypes.c_int * 3)(val("MouseThreshold1"), val("MouseThreshold2"), val("MouseSpeed"))
    SPI_SETMOUSE, SPIF_UPDATEINIFILE, SPIF_SENDCHANGE = 0x0004, 0x01, 0x02
    ctypes.windll.user32.SystemParametersInfoW(SPI_SETMOUSE, 0, arr, SPIF_UPDATEINIFILE | SPIF_SENDCHANGE)


DEFAULT_HOOKS = {"mouse_live": mouse_live_hook}


