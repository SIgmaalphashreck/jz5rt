"""UI-Smoke-Test: baut das komplette Fenster unsichtbar und rendert jede Seite."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
_tmp = tempfile.mkdtemp()
os.environ["LOCALAPPDATA"] = _tmp          # Testdaten nicht in den echten Benutzerordner schreiben
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    from PySide6.QtWidgets import QApplication
    HAVE_QT = True
except Exception:  # noqa: BLE001
    HAVE_QT = False


@unittest.skipUnless(HAVE_QT, "PySide6 nicht installiert")
class UiSmoke(unittest.TestCase):
    def test_all_pages_render_and_filters_work(self):
        import service as svc
        svc.IS_WINDOWS = False                 # Fake-Registry statt echter Registry
        import app as appmod
        from main import make_app
        qt = make_app()
        win = appmod.MainWindow()
        win.show()
        for name in win.pages:
            win.go(name)
            qt.processEvents()
            self.assertGreater(win.grab().width(), 800, name)
        tw = win.pages["Tweaks"].list
        for f in ("Empfohlen", "FPS", "Latenz", "Ping", "Aktiv", "Alle"):
            tw._f(f)
        tw._q("vollbild")
        visible = [r.tweak.id for r in tw.rows.values() if not r.isHidden()]
        self.assertTrue(visible and all("vollbild" in (r.tweak.name + r.tweak.description + " ".join(r.tweak.tags)).lower()
                                        for r in tw.rows.values() if not r.isHidden()))
        win.close()


if __name__ == "__main__":
    unittest.main()
