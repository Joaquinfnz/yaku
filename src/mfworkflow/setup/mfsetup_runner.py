#!/usr/bin/env python3
"""Motor profesional: construccion de modelos con modflow-setup (stack USGS).

modflow-setup automatiza la construccion de modelos MODFLOW 6 desde datos
geoespaciales nativos (shapefiles, rasters/DEM) mapeados a una grilla, resumidos
en un unico YAML de configuracion. Hace ademas version stamping de los inputs.

Este runner es un wrapper delgado: el usuario provee el YAML de modflow-setup
(plantilla en templates/proyecto_base/datos/gis/setup_mfsetup.yaml) y aqui se
construye, escribe y opcionalmente ejecuta el modelo.

A diferencia del motor simple (CSV -> FloPy), el motor mfsetup es el recomendado
para proyectos reales: grilla desde GIS, parametrizacion espacial y compatibilidad
directa con pyemu pilot points.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger("mfworkflow")


def is_available() -> bool:
    """True si modflow-setup esta instalado."""
    try:
        import mfsetup  # noqa: F401

        return True
    except Exception:
        return False


def build_from_yaml(setup_yaml: Path, run: bool = False):
    """Construye (y opcionalmente ejecuta) un modelo MODFLOW 6 desde un YAML mfsetup.

    Devuelve la instancia MF6model de modflow-setup. Requiere que el YAML referencie
    sus datos fuente (rasters/shapefiles) con rutas validas.
    """
    if not is_available():
        raise RuntimeError(
            "modflow-setup no esta instalado. Instala con: pip install modflow-setup"
        )

    from mfsetup import MF6model

    setup_yaml = Path(setup_yaml)
    if not setup_yaml.exists():
        raise FileNotFoundError(f"No existe el YAML de modflow-setup: {setup_yaml}")

    logger.info("Construyendo modelo con modflow-setup desde %s", setup_yaml)
    model = MF6model.setup_from_yaml(str(setup_yaml))
    model.write_input()
    logger.info("Inputs MODFLOW 6 escritos por modflow-setup (con version stamping)")

    if run:
        success, _ = model.simulation.run_simulation(silent=True)
        if not success:
            raise SystemExit("El modelo (mfsetup) no convergio.")
        logger.info("Simulacion mfsetup completada")
    return model
