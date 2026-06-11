#!/usr/bin/env python3
"""Geometria del modelo (mixin del builder): capas, superficies, K distribuida, idomain.

    Lee top_dem_grid.csv (drapeado al DEM), botm_grid_capa{N}.csv (geometria no plana
    por unidad), k_field_capa{N}.csv (pilot points) y la grilla activa (idomain)."""

from __future__ import annotations

import logging
from pathlib import Path  # noqa: F401  (usado en anotaciones/typing de los metodos)

import numpy as np
import pandas as pd

logger = logging.getLogger("yaku")


class GeometriaMixin:
    def _dem_grid(self, nrow: int, ncol: int) -> "np.ndarray | None":
        """Lee datos/tablas/top_dem_grid.csv (techo = terreno) si calza con la grilla."""
        path = self.data_dir / "top_dem_grid.csv"
        if not path.exists():
            return None
        try:
            dem = pd.read_csv(path, header=None).to_numpy(dtype=float)
        except Exception:  # noqa: BLE001
            return None
        return dem if dem.shape == (nrow, ncol) else None

    def build_layer_config(self, params: dict[str, float], *, drapear: bool = False) -> dict[str, object]:
        frame = self.csv_if_exists("capas_modelo.csv")
        nrow, ncol = int(params["nrow"]), int(params["ncol"])
        if frame is None:
            nlay_p = int(params["nlay"])
            return {
                "nlay": nlay_p,
                "top": params["top"],
                "botm": self._aplicar_superficies(params["top"], params["botm"], nlay_p, nrow, ncol),
                "k": params["k"],
                "k33": params["k"],
                "icelltype": 1,
                "iconvert": 1,
                "sy": 0.1,
                "ss": 1e-5,
            }

        frame = frame.copy().sort_values("layer")
        top_val: object = float(frame.iloc[0]["top_m"])
        botm_val: object = frame["botm_m"].astype(float).tolist()
        # Drapeado: el techo sigue el DEM y las capas conservan su espesor por debajo.
        if drapear:
            dem = self._dem_grid(nrow, ncol)
            if dem is not None:
                espesores = (frame["top_m"].astype(float) - frame["botm_m"].astype(float)).tolist()
                top_val = dem
                acum, botm_arrays = 0.0, []
                for e in espesores:
                    acum += float(e)
                    botm_arrays.append(dem - acum)
                botm_val = botm_arrays
                logger.info("Geometria drapeada al DEM: techo variable (%.0f-%.0f m) y %d capas.",
                            float(dem.min()), float(dem.max()), len(espesores))
        # Superficies de base por capa (geometria no plana), si existen botm_grid_capa{N}.csv
        botm_val = self._aplicar_superficies(top_val, botm_val, len(frame), nrow, ncol)
        return {
            "nlay": len(frame),
            "top": top_val,
            "botm": botm_val,
            "k": frame["kx_m_d"].astype(float).tolist(),
            "k33": frame["kz_m_d"].astype(float).tolist() if "kz_m_d" in frame.columns else frame["kx_m_d"].astype(float).tolist(),
            "icelltype": frame["iconvert"].fillna(0).astype(int).tolist() if "iconvert" in frame.columns else [1] * len(frame),
            "iconvert": frame["iconvert"].fillna(0).astype(int).tolist() if "iconvert" in frame.columns else [1] * len(frame),
            "sy": frame["sy"].fillna(0.1).astype(float).tolist() if "sy" in frame.columns else [0.1] * len(frame),
            "ss": frame["ss"].fillna(1e-5).astype(float).tolist() if "ss" in frame.columns else [1e-5] * len(frame),
        }

    def _k_fields(self, nlay: int, nrow: int, ncol: int) -> "dict[int, np.ndarray]":
        """Campos de K distribuida por capa: datos/tablas/k_field_capa{N}.csv (nrow x ncol).

        Los produce la calibracion por pilot points (yaku.calibration.pilot_points).
        Si existen y calzan con la grilla, reemplazan la K escalar de esa capa en el NPF.
        """
        fields: dict[int, np.ndarray] = {}
        for lay in range(1, nlay + 1):
            path = self.data_dir / f"k_field_capa{lay}.csv"
            if not path.exists():
                continue
            try:
                arr = pd.read_csv(path, header=None).to_numpy(dtype=float)
            except Exception:  # noqa: BLE001
                logger.warning("k_field_capa%d.csv ilegible; se usa la K escalar de la capa.", lay)
                continue
            if arr.shape != (nrow, ncol):
                logger.warning("k_field_capa%d.csv tiene forma %s y la grilla es (%d, %d); ignorado.",
                               lay, arr.shape, nrow, ncol)
                continue
            if not np.all(arr > 0):
                logger.warning("k_field_capa%d.csv contiene valores <= 0; ignorado.", lay)
                continue
            fields[lay - 1] = arr
        return fields

    def _botm_grids(self, nlay: int, nrow: int, ncol: int) -> "dict[int, np.ndarray]":
        """Superficies de base por capa: datos/tablas/botm_grid_capa{N}.csv (nrow x ncol).

        Permiten geometria NO plana por unidad hidrogeologica (las produce `yaku prep`
        al remuestrear rasters base_capa{N}.tif, o el usuario directamente). Devuelve
        {indice_capa_0based: array}.
        """
        grids: dict[int, np.ndarray] = {}
        for lay in range(1, nlay + 1):
            path = self.data_dir / f"botm_grid_capa{lay}.csv"
            if not path.exists():
                continue
            try:
                arr = pd.read_csv(path, header=None).to_numpy(dtype=float)
            except Exception:  # noqa: BLE001
                logger.warning("botm_grid_capa%d.csv ilegible; se usa la base plana de la capa.", lay)
                continue
            if arr.shape != (nrow, ncol):
                logger.warning("botm_grid_capa%d.csv tiene forma %s y la grilla es (%d, %d); ignorado.",
                               lay, arr.shape, nrow, ncol)
                continue
            grids[lay - 1] = arr
        return grids

    def _aplicar_superficies(self, top_val: object, botm_val: object, nlay: int,
                             nrow: int, ncol: int, *, espesor_min: float = 0.5) -> object:
        """Reemplaza bases planas por superficies de capa, garantizando espesor >= espesor_min.

        Cada base se recorta contra la superficie superior (top o base de la capa de
        arriba) para que la geometria sea valida (botm estrictamente decreciente).
        """
        grids = self._botm_grids(nlay, nrow, ncol)
        if not grids:
            return botm_val
        base = list(botm_val) if isinstance(botm_val, list) else [botm_val] * nlay
        arriba = (np.asarray(top_val, dtype=float) if not np.isscalar(top_val)
                  else np.full((nrow, ncol), float(top_val)))
        nuevas: list[np.ndarray] = []
        for i in range(nlay):
            if i in grids:
                b = np.where(np.isfinite(grids[i]), grids[i],
                             np.broadcast_to(np.asarray(base[i], dtype=float), (nrow, ncol)))
            else:
                b = np.broadcast_to(np.asarray(base[i], dtype=float), (nrow, ncol)).astype(float)
            b = np.minimum(b, arriba - espesor_min)
            nuevas.append(b)
            arriba = b
        logger.info("Geometria no plana: superficie de base aplicada en capa(s) %s "
                    "(espesor minimo %.2f m).", ", ".join(str(i + 1) for i in sorted(grids)), espesor_min)
        return nuevas

    def _load_idomain(self, nrow: int, ncol: int) -> "np.ndarray | None":
        """Mascara de celdas activas (idomain) desde resultados/gis/grilla_activa.csv.

        La produce `yaku gis` al intersectar la grilla con el dominio. Si existe, el
        modelo desactiva las celdas fuera del dominio (deja de ser un rectangulo lleno).
        """
        path = self.workspace / "gis" / "grilla_activa.csv"
        if not path.exists():
            return None
        frame = pd.read_csv(path)
        if not {"row", "col", "activo"} <= set(frame.columns):
            return None
        dom = np.zeros((nrow, ncol), dtype=int)
        for _, r in frame.iterrows():
            rr, cc = int(r["row"]), int(r["col"])
            if 0 <= rr < nrow and 0 <= cc < ncol and bool(r["activo"]):
                dom[rr, cc] = 1
        return dom if dom.any() else None

