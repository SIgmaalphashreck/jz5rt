"""Fassade: engine + catalog unter einem Namen (alte Tests nutzen `tl.`)."""
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import catalog  # noqa: E402
import engine  # noqa: E402

tl = types.SimpleNamespace(**{**vars(engine), **{k: v for k, v in vars(catalog).items() if not k.startswith("__")}})
