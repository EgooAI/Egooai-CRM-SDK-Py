from __future__ import annotations

import sys
from pathlib import Path


_SDK_ROOT = Path(__file__).resolve().parent
_SDK_ROOT_STR = str(_SDK_ROOT)

if _SDK_ROOT_STR not in sys.path:
    sys.path.insert(0, _SDK_ROOT_STR)

import core  # type: ignore[import-not-found]
import models  # type: ignore[import-not-found]

__all__ = ["core", "models"]
