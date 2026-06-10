"""Resolucion de binarios MODFLOW/MODPATH/Triangle/PEST++.

get-modflow instala los ejecutables en ~/.local/share/flopy/bin, que no siempre
esta en el PATH (sobre todo bajo `conda run`). Este helper los encuentra ahi
ademas del PATH, para que MODPATH 7, Triangle y el solver funcionen siempre.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path


def _flopy_bindirs() -> list[Path]:
    dirs: list[Path] = []
    # Ubicacion por defecto de get-modflow (:flopy)
    default = Path.home() / ".local" / "share" / "flopy" / "bin"
    if default.is_dir():
        dirs.append(default)
    # Metadata de get-modflow puede registrar otro bindir
    meta = Path.home() / ".local" / "share" / "flopy" / "get_modflow.json"
    if meta.is_file():
        try:
            data = json.loads(meta.read_text(encoding="utf-8"))
            bindir = data.get("bindir")
            if bindir and Path(bindir).is_dir():
                dirs.append(Path(bindir))
        except Exception:
            pass
    return dirs


def resolve_exe(name: str) -> str | None:
    """Devuelve la ruta a un ejecutable buscando en PATH y en los bin de flopy."""
    found = shutil.which(name)
    if found:
        return found
    exe_name = name + (".exe" if os.name == "nt" else "")
    for d in _flopy_bindirs():
        candidate = d / exe_name
        if candidate.is_file():
            return str(candidate)
    return None


def ensure_flopy_bin_on_path() -> None:
    """Agrega los bin de flopy al PATH del proceso (idempotente)."""
    extra = [str(d) for d in _flopy_bindirs()]
    if not extra:
        return
    current = os.environ.get("PATH", "")
    parts = current.split(os.pathsep)
    nuevos = [d for d in extra if d not in parts]
    if nuevos:
        os.environ["PATH"] = os.pathsep.join(nuevos + parts)
