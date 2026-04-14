"""Load FMU-related defaults from the packaged Synarius-Library descriptor (JSON)."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from synarius_core.model.elementary import DEFAULT_FMU_LIBRARY_TYPE_KEY as _FALLBACK_TYPE_KEY

_DESCRIPTOR_NAME = "fmu_library_descriptor.json"


def _descriptor_path() -> Path:
    here = Path(__file__).resolve().parent
    return (here.parent / "standard_library" / _DESCRIPTOR_NAME).resolve()


@lru_cache(maxsize=1)
def _load_descriptor_raw() -> dict[str, object]:
    path = _descriptor_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError:
        return {}
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def default_fmu_library_type_key() -> str:
    """Default ``type_key`` for FMU-backed elementaries (from descriptor, else model fallback)."""
    raw = _load_descriptor_raw()
    v = raw.get("default_fmu_type_key")
    if isinstance(v, str) and v.strip():
        return v.strip()
    return _FALLBACK_TYPE_KEY
