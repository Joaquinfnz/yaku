"""Version stamping de los inputs del modelo (reproducibilidad).

Replica el comportamiento de modflow-setup: registra las versiones del stack y un
hash del config + datos junto a los resultados, para que cualquier salida sea
trazable a las versiones y entradas exactas que la produjeron.
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def _safe_version(modname: str) -> str:
    try:
        mod = __import__(modname)
        return getattr(mod, "__version__", "desconocida")
    except Exception:
        return "no instalado"


def _hash_paths(paths: list[Path]) -> str:
    """Hash SHA256 estable del contenido de una lista de archivos existentes."""
    h = hashlib.sha256()
    for path in sorted(paths, key=lambda p: str(p)):
        if path.is_file():
            h.update(path.name.encode("utf-8"))
            h.update(path.read_bytes())
    return h.hexdigest()


def stamp_inputs(
    resultados_dir: Path,
    *,
    config_path: Path | None = None,
    datos_dir: Path | None = None,
    model_name: str = "",
    motor: str = "",
) -> Path:
    """Escribe resultados_dir/inputs_metadata.json y devuelve su ruta."""
    resultados_dir = Path(resultados_dir)
    resultados_dir.mkdir(parents=True, exist_ok=True)

    hashed: list[Path] = []
    if config_path and Path(config_path).is_file():
        hashed.append(Path(config_path))
    if datos_dir and Path(datos_dir).is_dir():
        hashed.extend(sorted(Path(datos_dir).glob("*.csv")))

    metadata = {
        "generado": datetime.now(timezone.utc).isoformat(),
        "modelo": model_name,
        "motor": motor,
        "versiones": {
            "python": sys.version.split()[0],
            "yaku": _safe_version("yaku"),
            "flopy": _safe_version("flopy"),
            "numpy": _safe_version("numpy"),
            "pandas": _safe_version("pandas"),
            "pyemu": _safe_version("pyemu"),
            "modflow_setup": _safe_version("mfsetup"),
        },
        "hash_entradas_sha256": _hash_paths(hashed) if hashed else None,
        "archivos_entrada": [p.name for p in hashed],
    }

    out = resultados_dir / "inputs_metadata.json"
    out.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    return out
