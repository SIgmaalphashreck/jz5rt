"""SquallowTweaks - Tweak-Katalog (kurz und lesbar).

Pro Tweak: Name, EIN kurzer Satz, Tags (FPS / LATENZ / PING / FRAMETIME) und
ein Detailtext, der nur im Tooltip erscheint.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from engine import (REG_DWORD, REG_SZ, STATUS_ACTIVE, STATUS_UNKNOWN, TOGGLE_KINDS, RegValue, Tweak, TweakEngine,
                    FORT_SECTION)

CATEGORIES = ["Gaming", "Fortnite", "Latenz", "Netzwerk", "System"]
G, F, L, N, S = CATEGORIES

HKLM_MM = r"HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile"


def _dw(path, name, value):
    return RegValue(path, name, REG_DWORD, value)


def _sz(path, name, value):
    return RegValue(path, name, REG_SZ, value)


def msi_gpu_values(backend) -> list:
    """MSI-Modus fuer alle Grafikkarten (PCI-Klasse 'Display'), zur Laufzeit ermittelt."""
    base = r"HKLM\SYSTEM\CurrentControlSet\Enum\PCI"
    out = []
    for dev in backend.subkeys(base):
        for inst in backend.subkeys(base + "\\" + dev):
            path = base + "\\" + dev + "\\" + inst
            ok, _, cls = backend.read(path, "Class")
            if ok and str(cls).lower() == "display":
                out.append(RegValue(path + r"\Device Parameters\Interrupt Management\MessageSignaledInterruptProperties",
                                    "MSISupported", REG_DWORD, 1))
    return out


def fortnite_exe_path() -> Optional[str]:
    """Installationspfad von Fortnite laut Epic-Launcher (LauncherInstalled.dat)."""
    base = os.environ.get("ProgramData", r"C:\ProgramData")
    f = Path(base) / "Epic" / "UnrealEngineLauncher" / "LauncherInstalled.dat"
    try:
        data = json.loads(f.read_text(encoding="utf-8", errors="replace"))
        for item in data.get("InstallationList", []):
            if item.get("AppName") == "Fortnite" and item.get("InstallLocation"):
                exe = Path(item["InstallLocation"]) / "FortniteGame" / "Binaries" / "Win64" / "FortniteClient-Win64-Shipping.exe"
                return str(exe)
    except Exception:  # noqa: BLE001
        pass
    return None


def fortnite_exe_flag_values(_backend) -> list:
    exe = fortnite_exe_path()
    if not exe:
        return []
    return [RegValue(r"Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers", exe, REG_SZ,
                     "~ DISABLEDXMAXIMIZEDWINDOWEDMODE")]


_FG = FORT_SECTION
_GFX = {}
for _k in ("ShadowQuality", "PostProcessQuality", "EffectsQuality", "FoliageQuality", "ShadingQuality",
           "GlobalIlluminationQuality", "ReflectionQuality"):
    _GFX[f"{_FG}|sg.{_k}"] = "0"
    _GFX[f"ScalabilityGroups|sg.{_k}"] = "0"

LAN_PROPS = {"*EEE": "0", "EEELinkAdvertisement": "0", "AdvancedEEE": "0", "GreenEthernet": "0", "EnableGreenEthernet": "0",
             "PowerSavingMode": "0", "ULPMode": "0", "GigaLite": "0", "*FlowControl": "0"}


def build_catalog() -> list[Tweak]:
    T = Tweak
    return [
        # ------------------------------------------------------------------ FPS / Frametime
        T("power_ultimate", "Ultimative Leistung", [G, L], "Stärkster Windows-Energieplan, kein Takt-Absenken.",
          "Legt den versteckten Plan 'Ultimative Leistung' an. Mehr Verbrauch und Wärme. Fällt auf Höchstleistung zurück, falls nicht vorhanden.",
          kind="power", power_target="ultimate", recommended="desktop", tags=("FPS", "FRAMETIME"), why="Stabilere Taktung am Desktop."),
        T("power_high", "Höchstleistung", [G], "Windows-Energieplan 'Höchstleistung'.",
          "Alternative zu 'Ultimative Leistung'.", kind="power", power_target="high", tags=("FPS",)),
        T("ps_min_cpu", "CPU-Takt immer oben", [G, L], "Prozessor-Mindestzustand 100 % im Netzbetrieb.",
          "Die CPU taktet nicht mehr herunter und reagiert ohne Hochtakt-Verzögerung. Mehr Leerlaufverbrauch.",
          kind="powersetting", ps_sub="SUB_PROCESSOR", ps_setting="PROCTHROTTLEMIN", ps_value=100,
          recommended="desktop", tags=("FRAMETIME", "LATENZ"), why="Kein Takt-Absenken beim Spielen."),
        T("ps_core_parking_off", "Kernparken aus", [G, L], "Alle CPU-Kerne bleiben aktiv.",
          "Verhindert, dass Windows Kerne schlafen legt und bei Lastspitzen erst aufwecken muss.",
          kind="powersetting", ps_sub="SUB_PROCESSOR", ps_setting="CPMINCORES", ps_value=100,
          recommended="desktop", tags=("FRAMETIME",), why="Weniger Aufwach-Ruckler."),
        T("games_task", "Spiele-Priorität im Scheduler", [G, F], "Windows bevorzugt Spiele bei CPU und GPU.",
          "MMCSS-Aufgabe 'Games': GPU-Priorität 8, Priorität 6, Kategorie High. Hilft bei Hintergrundlast und 1%-Lows.",
          values=[_dw(HKLM_MM + r"\Tasks\Games", "GPU Priority", 8), _dw(HKLM_MM + r"\Tasks\Games", "Priority", 6),
                  _sz(HKLM_MM + r"\Tasks\Games", "Scheduling Category", "High"), _sz(HKLM_MM + r"\Tasks\Games", "SFIO Priority", "High")],
          admin=True, restart="Neustart", recommended="baseline", tags=("FPS", "FRAMETIME"), why="Spiel bekommt Vorrang."),
        T("win32_prio", "Vordergrund-Boost", [G, L], "Das aktive Spiel bekommt mehr Rechenzeit.",
          "Win32PrioritySeparation = 0x26: kurze, feste Zeitscheiben mit starker Vordergrund-Bevorzugung.",
          values=[_dw(r"HKLM\SYSTEM\CurrentControlSet\Control\PriorityControl", "Win32PrioritySeparation", 38)],
          admin=True, restart="Neustart", recommended="desktop", tags=("LATENZ", "FRAMETIME"), why="Vordergrund vor Hintergrund."),
        T("timer_res", "Präzise Zeitgeber", [L], "Konstante 0,5-ms-Zeitgeber für flüssigere Frametimes.",
          "GlobalTimerResolutionRequests=1 (ab Windows 11 relevant). Mehr Timer-Genauigkeit, minimal mehr Stromverbrauch.",
          values=[_dw(r"HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\kernel", "GlobalTimerResolutionRequests", 1)],
          admin=True, restart="Neustart", recommended="desktop", tags=("LATENZ", "FRAMETIME"), why="Gleichmäßigere Frametimes."),
        T("power_throttling_off", "Power Throttling aus", [G], "Windows drosselt keine Hintergrund-Programme auf Sparmodus.",
          "Spiel und Launcher laufen mit voller Leistung. Minimal mehr Verbrauch.",
          values=[_dw(r"HKLM\SYSTEM\CurrentControlSet\Control\Power\PowerThrottling", "PowerThrottlingOff", 1)],
          admin=True, restart="Neustart", recommended="desktop", tags=("FPS",), why="Konstante Taktung."),
        T("ps_pcie_aspm_off", "PCIe-Sparmodus aus", [L], "Die GPU-Verbindung schläft nie ein.",
          "Link State Power Management aus. Vermeidet seltene Aufwach-Verzögerungen der Grafikkarte.",
          kind="powersetting", ps_sub="SUB_PCIE", ps_setting="ASPM", ps_value=0,
          recommended="desktop", tags=("FRAMETIME",), why="Keine GPU-Aufwach-Ruckler."),
        T("msi_gpu", "GPU Interrupts (MSI)", [L], "Effizientere Interrupts für die Grafikkarte.",
          "Aktiviert Message Signaled Interrupts für alle Grafikkarten. Aktuelle RTX-Treiber nutzen das oft schon, dann ändert sich nichts.",
          dynamic=msi_gpu_values, admin=True, restart="Neustart", tags=("LATENZ",), risk="mittel", why="Weniger DPC-Latenz."),
        T("game_mode", "Windows Game Mode", [G], "Windows priorisiert das Spiel.",
          "Spiele-Modus aktivieren. Der Effekt ist je nach System klein, aber sicher.",
          values=[_dw(r"Software\Microsoft\GameBar", "AutoGameModeEnabled", 1), _dw(r"Software\Microsoft\GameBar", "AllowAutoGameMode", 1)],
          recommended="baseline", tags=("FPS",), why="Standard für Spiele."),
        T("game_dvr", "Game DVR aus", [G], "Keine Hintergrundaufnahme.",
          "Schaltet Xbox-Hintergrundaufnahme ab (spart Overhead). Clips über die Game Bar gehen dann nicht mehr.",
          values=[_dw(r"System\GameConfigStore", "GameDVR_Enabled", 0), _dw(r"Software\Microsoft\Windows\CurrentVersion\GameDVR", "AppCaptureEnabled", 0)],
          restart="Neustart des Spiels", recommended="baseline", tags=("FPS",), why="Entfernt Aufnahme-Overhead."),
        T("fso_global", "Echtes Vollbild bevorzugen", [G, L], "Direkter Vollbild-Pfad statt Fenster-Optimierung.",
          "Kann die Eingabelatenz in DirectX-Spielen senken. Alt-Tab ist etwas träger.",
          values=[_dw(r"System\GameConfigStore", "GameDVR_FSEBehaviorMode", 2), _dw(r"System\GameConfigStore", "GameDVR_HonorUserFSEBehaviorMode", 1),
                  _dw(r"System\GameConfigStore", "GameDVR_DXGIHonorFSEWindowsCompatible", 1)],
          restart="nächster Spielstart", recommended="competitive", tags=("LATENZ",), why="Weniger Latenz im Vollbild."),
        T("mouse_accel", "Mausbeschleunigung aus", [G, L], "1:1-Mausbewegung.",
          "Setzt Zeigerbeschleunigung auf 0 und übernimmt sofort.",
          values=[_sz(r"Control Panel\Mouse", "MouseSpeed", "0"), _sz(r"Control Panel\Mouse", "MouseThreshold1", "0"),
                  _sz(r"Control Panel\Mouse", "MouseThreshold2", "0")],
          hook="mouse_live", recommended="baseline", tags=("LATENZ",), why="Gleichmäßige Mausbewegung."),
        T("ps_usb_suspend_off", "USB-Sparmodus aus", [L], "Maus und Tastatur schlafen nie ein.",
          "USB Selective Suspend aus (Netzbetrieb).", kind="powersetting", ps_sub="2a737441-1930-4402-8d77-b2bebba308a3",
          ps_setting="48e6b7a6-50f5-4782-a5d4-53bb8f07e226", ps_value=0, recommended="desktop", tags=("LATENZ",), why="Keine Aufwach-Verzögerung."),
        T("sticky_keys_off", "Tastatur-Popups aus", [G], "Keine 5x-Shift-Fenster mitten im Match.",
          "Schaltet Einrast-, Umschalt- und Anschlagverzögerung-Popups aus.",
          values=[_sz(r"Control Panel\Accessibility\StickyKeys", "Flags", "506"), _sz(r"Control Panel\Accessibility\ToggleKeys", "Flags", "58"),
                  _sz(r"Control Panel\Accessibility\Keyboard Response", "Flags", "122")],
          restart="Neuanmeldung", recommended="baseline", tags=("FPS",), why="Verhindert, dass Fortnite minimiert wird."),
        T("keyboard_fast", "Schnelle Tastaturwiederholung", [G], "Kürzeste Verzögerung, höchste Rate.",
          "KeyboardDelay 0, KeyboardSpeed 31.", values=[_sz(r"Control Panel\Keyboard", "KeyboardDelay", "0"), _sz(r"Control Panel\Keyboard", "KeyboardSpeed", "31")],
          restart="Neuanmeldung", recommended="competitive", tags=("LATENZ",), why="Schnellere Tasten."),
        # ------------------------------------------------------------------ Ping / Netzwerk
        T("net_adapter_stable", "LAN-Adapter ohne Sparmodus", [N], "Stabilerer Ping: keine Energiespar-Pausen im Netzwerkchip.",
          "Schaltet Energy-Efficient-Ethernet, Green Ethernet und Flow Control am verbundenen LAN-Adapter aus. Diese Funktionen verursachen Mikro-Pausen und Ping-Spitzen. Die Verbindung unterbricht dabei 1–3 s.",
          kind="netadapter", adapter_props=LAN_PROPS, admin=True, recommended="desktop", tags=("PING",), why="Weniger Ping-Spitzen."),
        T("net_throttle_off", "Netzwerk-Drosselung aus", [N, G], "Windows bremst Pakete beim Spielen nicht mehr.",
          "NetworkThrottlingIndex aus und Systemreaktionszeit 0 %. Wirkt vor allem bei laufender Musik/Stream.",
          values=[_dw(HKLM_MM, "NetworkThrottlingIndex", 4294967295), _dw(HKLM_MM, "SystemResponsiveness", 0)],
          admin=True, restart="Neustart", recommended="baseline", tags=("PING", "FPS"), why="Keine Paket-Drosselung."),
        T("delivery_opt_off", "Kein Update-Upload", [N], "Dein PC lädt keine Windows-Updates für andere hoch.",
          "Delivery Optimization aus. Verhindert Upload im Hintergrund, der den Ping stören kann.",
          values=[_dw(r"HKLM\SOFTWARE\Policies\Microsoft\Windows\DeliveryOptimization", "DODownloadMode", 0)],
          admin=True, restart="Neustart", tags=("PING",), why="Kein Hintergrund-Upload."),
        # ------------------------------------------------------------------ Fortnite
        T("fn_graphics_perf", "Grafik auf Leistung", [F], "Schatten, Effekte, Post, Laub, GI, Reflexionen auf Niedrig.",
          "Der größte Hebel für FPS und 1%-Lows. Sichtweite und Texturen bleiben unverändert. Fortnite muss beendet sein.",
          kind="ini", ini_section=_FG, ini_values=_GFX, recommended="fortnite", tags=("FPS", "FRAMETIME"), why="Weniger GPU/CPU-Last."),
        T("fn_fps_limit", "FPS-Limit 240", [F], "Kein FPS-Überlauf über deine Monitor-Hz.",
          "FrameRateLimit=240. Glättet die Frametime.", kind="ini", ini_section=_FG, ini_values={"FrameRateLimit": "240.000000"},
          recommended="fortnite", tags=("FRAMETIME",), why="Stabile Frametimes."),
        T("fn_vsync_off", "V-Sync aus", [F], "Weniger Eingabelatenz.",
          "bUseVSync=False. Mit G-SYNC/FreeSync kaum Tearing.", kind="ini", ini_section=_FG, ini_values={"bUseVSync": "False"},
          recommended="fortnite", tags=("LATENZ",), why="V-Sync erhöht Latenz."),
        T("fn_fullscreen", "Echtes Vollbild", [F], "Vollbild statt Fenster-Vollbild.",
          "FullscreenMode=0. Senkt die Eingabelatenz.", kind="ini", ini_section=_FG,
          ini_values={"FullscreenMode": "0", "PreferredFullscreenMode": "0", "LastConfirmedFullscreenMode": "0"},
          recommended="fortnite", tags=("LATENZ",), why="Direkter Pfad."),
        T("fn_motionblur_off", "Bewegungsunschärfe aus", [F], "Klareres Bild beim Drehen.",
          "bMotionBlur=False.", kind="ini", ini_section=_FG, ini_values={"bMotionBlur": "False"},
          recommended="fortnite", tags=("FPS",), why="Klarer und leichter."),
        T("fn_menu_fps", "Lobby auf 60 FPS", [F], "Weniger Wärme und Lärm im Menü.",
          "MenuFrameRateLimit_Unified=60. Kein Einfluss auf Matches.", kind="ini", ini_section=_FG,
          ini_values={"MenuFrameRateLimit_Unified": "60.000000"}, tags=()),
        T("fn_exe_flags", "Vollbild-Optimierung für Fortnite aus", [F], "Windows-Kompatibilitäts-Flag direkt für Fortnite.",
          "Setzt für FortniteClient-Win64-Shipping.exe das Flag 'Vollbildoptimierungen deaktivieren'. Pfad kommt aus dem Epic Launcher.",
          dynamic=fortnite_exe_flag_values, recommended="competitive", tags=("LATENZ",), why="Direkter Vollbild-Pfad."),
        # ------------------------------------------------------------------ System
        T("bg_apps_off", "Hintergrund-Apps aus", [S], "Store-Apps laufen nicht im Hintergrund.",
          "Spart CPU, RAM und Netzwerk.", values=[_dw(r"Software\Microsoft\Windows\CurrentVersion\BackgroundAccessApplications", "GlobalUserDisabled", 1),
                                                  _dw(r"Software\Microsoft\Windows\CurrentVersion\Search", "BackgroundAppGlobalToggle", 0)],
          restart="Neuanmeldung", tags=("FPS",), why="Weniger Hintergrundlast."),
        T("telemetry_policy", "Telemetrie minimal", [S], "Weniger Diagnosedaten-Versand.",
          "AllowTelemetry=0. Home-Editionen nutzen die niedrigste erlaubte Stufe.",
          values=[_dw(r"HKLM\SOFTWARE\Policies\Microsoft\Windows\DataCollection", "AllowTelemetry", 0)], admin=True, restart="Neustart", tags=()),
        T("diagtrack_off", "Telemetrie-Dienst aus", [S], "DiagTrack läuft nicht mehr.",
          "Starttyp 'Deaktiviert' für den Dienst 'Benutzererfahrungen und Telemetrie'.",
          values=[_dw(r"HKLM\SYSTEM\CurrentControlSet\Services\DiagTrack", "Start", 4)], admin=True, restart="Neustart", tags=("FPS",)),
        T("visualfx", "Windows-Effekte: beste Leistung", [S], "Weniger Animationen und Effekte.",
          "VisualFXSetting=2.", values=[_dw(r"Software\Microsoft\Windows\CurrentVersion\Explorer\VisualEffects", "VisualFXSetting", 2)],
          restart="Neuanmeldung", tags=()),
        T("transparency_off", "Transparenz aus", [S], "Weniger DWM-Last.", "EnableTransparency=0.",
          values=[_dw(r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize", "EnableTransparency", 0)], tags=()),
        T("window_anim_off", "Fensteranimationen aus", [S], "Fenster reagieren direkter.", "MinAnimate=0.",
          values=[_sz(r"Control Panel\Desktop\WindowMetrics", "MinAnimate", "0")], restart="Neuanmeldung", tags=()),
    ]


# ---------------------------------------------------------------------------
# Auswahl fuer den Auto-Modus
# ---------------------------------------------------------------------------
PROFILES = {
    "safe": ("Safe", "Nur Basis-Tweaks, minimales Risiko."),
    "competitive": ("Competitive", "Alles Empfohlene für dein System."),
    "maxfps": ("Max FPS", "Competitive plus Effekte, Hintergrund und Telemetrie aus, GPU-MSI."),
}
MAXFPS_EXTRA_IDS = ("visualfx", "transparency_off", "window_anim_off", "bg_apps_off", "telemetry_policy", "diagtrack_off",
                    "delivery_opt_off", "msi_gpu", "fn_menu_fps")


def by_category(tweaks: list[Tweak], category: str) -> list[Tweak]:
    return [t for t in tweaks if category in t.categories]


def applicable(t: Tweak, ctx: dict) -> tuple[bool, str]:
    if t.recommended == "desktop" and not ctx.get("desktop", True):
        return False, "Notebook: Dauer-Hochtakt wird nicht automatisch gesetzt."
    if t.admin and not ctx.get("admin", True):
        return False, "Braucht Administratorrechte."
    if t.kind == "ini":
        if not ctx.get("fortnite_config", False):
            return False, "Fortnite-Config nicht gefunden."
        if ctx.get("fortnite_running", False):
            return False, "Fortnite läuft."
    return True, ""


def recommend(catalog: list[Tweak], engine: TweakEngine, ctx: dict):
    chosen: list[Tweak] = []
    skipped: list[tuple[Tweak, str]] = []
    for t in catalog:
        if t.kind not in TOGGLE_KINDS or not t.recommended:
            continue
        ok, reason = applicable(t, ctx)
        if not ok:
            skipped.append((t, reason))
            continue
        state, _ = engine.status(t)
        if state == STATUS_ACTIVE:
            continue
        if state == STATUS_UNKNOWN and t.kind in ("powersetting", "ini", "netadapter") or (state == STATUS_UNKNOWN and t.dynamic):
            skipped.append((t, "Auf diesem System nicht verfügbar."))
            continue
        chosen.append(t)
    return chosen, skipped


def select_for_profile(catalog: list[Tweak], engine: TweakEngine, ctx: dict, profile: str = "competitive"):
    if profile not in PROFILES:
        profile = "competitive"
    chosen, skipped = recommend(catalog, engine, ctx)
    if profile == "safe":
        skipped = skipped + [(t, "Nicht im Profil Safe.") for t in chosen if t.recommended != "baseline"]
        chosen = [t for t in chosen if t.recommended == "baseline"]
    elif profile == "maxfps":
        have = {t.id for t in chosen}
        for t in catalog:
            if t.id in MAXFPS_EXTRA_IDS and t.id not in have and t.kind in TOGGLE_KINDS:
                ok, reason = applicable(t, ctx)
                if not ok:
                    skipped.append((t, reason))
                    continue
                state = engine.status(t)[0]
                if state not in (STATUS_ACTIVE, STATUS_UNKNOWN):
                    chosen.append(t)
    return chosen, skipped
