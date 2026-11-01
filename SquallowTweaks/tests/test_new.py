import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _tl import tl  # noqa: E402


class FakeNic:
    """Simuliert PowerShell fuer Get-NetAdapter / Get-NetAdapterAdvancedProperty / Set-NetAdapterAdvancedProperty."""

    def __init__(self):
        self.props = {"*EEE": "1", "*FlowControl": "3", "GreenEthernet": "1", "*SpeedDuplex": "0"}
        self.fail_set = False

    def __call__(self, args, timeout=12):
        script = args[-1]
        if "Get-NetAdapter -Physical" in script:
            return 0, json.dumps({"Name": "Ethernet"})
        if "Get-NetAdapterAdvancedProperty" in script:
            return 0, json.dumps([{"K": k, "V": v} for k, v in self.props.items()])
        if "Set-NetAdapterAdvancedProperty" in script:
            if self.fail_set:
                return 1, "denied"
            kw = re.search(r"-RegistryKeyword '([^']+)'", script).group(1)
            val = re.search(r"-RegistryValue '([^']*)'", script).group(1)
            self.props[kw] = val
            return 0, ""
        return 1, "?"


class NetAdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.nic = FakeNic()
        self.eng = tl.TweakEngine(tl.MemoryBackend(), Path(self.tmp.name) / "s.json", runner=self.nic, admin_check=lambda: True)
        self.t = {t.id: t for t in tl.build_catalog()}["net_adapter_stable"]

    def tearDown(self):
        self.tmp.cleanup()

    def test_roundtrip_only_existing_keywords(self):
        self.assertEqual(self.eng.status(self.t)[0], tl.STATUS_INACTIVE)
        r = self.eng.apply(self.t)
        self.assertTrue(r.ok and r.verified, r.message)
        self.assertEqual(self.nic.props["*EEE"], "0")
        self.assertEqual(self.nic.props["*FlowControl"], "0")
        self.assertEqual(self.nic.props["*SpeedDuplex"], "0")      # unberuehrt
        self.assertNotIn("PowerSavingMode", self.nic.props)         # nicht vorhandene Keywords werden nicht angelegt
        self.assertEqual(self.eng.status(self.t)[0], tl.STATUS_ACTIVE)
        self.assertTrue(self.eng.undo(self.t).ok)
        self.assertEqual((self.nic.props["*EEE"], self.nic.props["*FlowControl"], self.nic.props["GreenEthernet"]), ("1", "3", "1"))

    def test_failure_rolls_back(self):
        self.nic.fail_set = True
        r = self.eng.apply(self.t)
        self.assertFalse(r.ok)
        self.assertEqual(self.nic.props["*EEE"], "1")

    def test_no_adapter(self):
        self.eng.runner = lambda a, timeout=12: (0, "")
        self.assertEqual(self.eng.status(self.t)[0], tl.STATUS_UNKNOWN)
        self.assertFalse(self.eng.apply(self.t).ok)


class CatalogQuality(unittest.TestCase):
    def test_texts_are_short(self):
        for t in tl.build_catalog():
            self.assertLessEqual(len(t.name), 40, t.id)
            self.assertLessEqual(len(t.description), 90, t.id)
            for tag in t.tags:
                self.assertIn(tag, ("FPS", "LATENZ", "PING", "FRAMETIME"), t.id)

    def test_fortnite_exe_flag_uses_epic_install(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "Epic" / "UnrealEngineLauncher"
            f.mkdir(parents=True)
            (f / "LauncherInstalled.dat").write_text(json.dumps(
                {"InstallationList": [{"AppName": "Fortnite", "InstallLocation": r"D:\Games\Fortnite"}]}))
            os.environ["ProgramData"] = d
            try:
                vals = tl.fortnite_exe_flag_values(None)
            finally:
                del os.environ["ProgramData"]
        self.assertEqual(len(vals), 1)
        self.assertTrue(vals[0].name.endswith("FortniteClient-Win64-Shipping.exe"))
        self.assertIn("DISABLEDXMAXIMIZEDWINDOWEDMODE", vals[0].value)

    def test_timer_and_parking_present(self):
        ids = {t.id for t in tl.build_catalog()}
        for must in ("timer_res", "ps_core_parking_off", "net_adapter_stable", "fn_exe_flags", "games_task", "msi_gpu"):
            self.assertIn(must, ids)


if __name__ == "__main__":
    unittest.main()
