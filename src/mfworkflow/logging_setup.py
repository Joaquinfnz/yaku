"""Configuracion de logging unificada del workflow.

Extraido de run_pipeline.setup_logging. Un unico logger "mfworkflow" con salida a
consola (INFO) y a un archivo con timestamp dentro del directorio de logs del
proyecto (DEBUG).
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path


def setup_logging(log_dir: Path, *, name: str = "mfworkflow") -> logging.Logger:
    """Configura y devuelve el logger del workflow.

    Crea ``log_dir`` si no existe y agrega un FileHandler con timestamp ademas del
    StreamHandler a stdout. Llamadas repetidas reinician los handlers para no
    duplicar lineas.
    """
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"mfworkflow_{datetime.now():%Y%m%d_%H%M%S}.log"

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    if logger.handlers:
        logger.handlers.clear()

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setLevel(logging.INFO)
    stream_handler.setFormatter(fmt)
    logger.addHandler(stream_handler)

    return logger
