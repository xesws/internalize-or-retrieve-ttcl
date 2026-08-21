"""Test bootstrap: make the vendored HoReN backend importable (CPU-only —
none of the ported modules here require CUDA)."""
import sys
from pathlib import Path

_HOREN_ROOT = Path(__file__).resolve().parents[1] / "third_party" / "horen"
if str(_HOREN_ROOT) not in sys.path:
    sys.path.insert(0, str(_HOREN_ROOT))
