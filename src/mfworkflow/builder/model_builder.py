#!/usr/bin/env python3
"""Motor simple: construye un modelo MODFLOW 6 a partir de CSV.

Soporta multicapa y regimen transiente. Es el motor "simple/didactico" del
workflow (para casos rapidos); los proyectos reales pueden usar ademas el motor
profesional basado en modflow-setup (ver mfworkflow.setup).

Migrado desde 04_modelo_base/modelo_desde_datos.py. Cambios respecto al original:
- logger "mfworkflow" (antes "modflow_pipeline").
- nombres de salida derivados de model_name (antes fijados a "modelo_datos"),
  para que el motor sea replicable en cualquier proyecto.
"""

from __future__ import annotations

import logging
from pathlib import Path

import flopy
import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from mfworkflow.binaries import ensure_flopy_bin_on_path, resolve_exe

logger = logging.getLogger("mfworkflow")


class ModflowModelBuilder:
    """Construye un modelo MODFLOW 6 desde datos CSV con validaciones."""

    def __init__(self, data_dir: Path, workspace: Path, model_name: str = "modelo",
                 *, drapear_dem: bool = False) -> None:
        self.data_dir = Path(data_dir)
        self.workspace = Path(workspace)
        self.model_name = model_name
        self.sim_name = model_name
        self.drapear_dem = drapear_dem   # techo del modelo siguiendo el DEM (top_dem_grid.csv)
        self.workspace.mkdir(parents=True, exist_ok=True)

    # -----------------------------------------------------------------------
    # Helpers CSV
    # -----------------------------------------------------------------------
    def csv_if_exists(self, filename: str) -> pd.DataFrame | None:
        path = self.data_dir / filename
        if not path.exists():
            return None
        frame = pd.read_csv(path)
        return frame if not frame.empty else None

    def read_parameters(self) -> dict[str, float]:
        frame = pd.read_csv(self.data_dir / "parametros_modelo.csv")
        return {str(row["clave"]): float(row["valor"]) for _, row in frame.iterrows()}

    def validate_input_data(self) -> list[str]:
        """Valida estructura y rangos basicos de los CSV de entrada.

        En la Fase 4 esta validacion se complementa con validacion de unidades y
        coherencia geometrica (ver mfworkflow.builder.validation).
        """
        errors: list[str] = []

        def require_file(filename: str) -> bool:
            if not (self.data_dir / filename).exists():
                errors.append(f"Falta archivo requerido: {filename}")
                return False
            return True

        def require_columns(frame: pd.DataFrame, filename: str, columns: set[str]) -> None:
            missing = sorted(columns - set(frame.columns))
            if missing:
                errors.append(f"{filename}: faltan columnas {', '.join(missing)}")

        if not require_file("parametros_modelo.csv") or not require_file("contornos_carga.csv"):
            return errors

        params = self.read_parameters()
        required_params = {"nrow", "ncol", "delr", "delc", "nlay", "top", "botm", "starting_head", "k", "recharge"}
        missing_params = sorted(required_params - set(params))
        if missing_params:
            errors.append(f"parametros_modelo.csv: faltan claves {', '.join(missing_params)}")
            return errors

        nlay = int(params["nlay"])
        nrow = int(params["nrow"])
        ncol = int(params["ncol"])
        if nlay <= 0 or nrow <= 0 or ncol <= 0:
            errors.append("nlay, nrow y ncol deben ser mayores que 0")
        if params["delr"] <= 0 or params["delc"] <= 0:
            errors.append("delr y delc deben ser mayores que 0")
        if params["k"] <= 0:
            errors.append("k debe ser mayor que 0")
        if params["recharge"] < 0:
            errors.append("recharge no puede ser negativa")

        stress_periods = self.read_stress_periods()
        require_columns(stress_periods, "stress_periods.csv", {"stress_period", "perlen_d", "nstp", "tsmult", "steady_state"})
        periods = stress_periods["stress_period"].astype(int).tolist()
        if sorted(periods) != periods:
            errors.append("stress_periods.csv: stress_period debe estar ordenado de menor a mayor")
        if (stress_periods["perlen_d"].astype(float) <= 0).any():
            errors.append("stress_periods.csv: perlen_d debe ser mayor que 0")
        if (stress_periods["nstp"].astype(int) <= 0).any():
            errors.append("stress_periods.csv: nstp debe ser mayor que 0")
        if not set(stress_periods["steady_state"].astype(int)).issubset({0, 1}):
            errors.append("stress_periods.csv: steady_state solo admite 0 o 1")

        layers = self.csv_if_exists("capas_modelo.csv")
        if layers is None and nlay > 1:
            errors.append(f"parametros_modelo.csv define nlay={nlay} pero falta capas_modelo.csv "
                          "(geometria y K por capa son obligatorias con mas de una capa).")
        if layers is not None:
            require_columns(layers, "capas_modelo.csv", {"layer", "top_m", "botm_m", "kx_m_d"})
            if len(layers) != nlay:
                errors.append(f"capas_modelo.csv: contiene {len(layers)} capas, pero parametros_modelo.csv define nlay={nlay}")
            if (layers["kx_m_d"].astype(float) <= 0).any():
                errors.append("capas_modelo.csv: kx_m_d debe ser mayor que 0")
            if "kz_m_d" in layers.columns and (layers["kz_m_d"].astype(float) <= 0).any():
                errors.append("capas_modelo.csv: kz_m_d debe ser mayor que 0")

        def validate_period(value: object, filename: str) -> None:
            for period in self.stress_period_targets(value, periods):
                if period not in periods:
                    errors.append(f"{filename}: stress_period {period} no existe en stress_periods.csv")

        def validate_cell(row: pd.Series, filename: str) -> None:
            layer = self.layer_target(row.get("layer", 1))
            row_index = int(row["row"])
            col_index = int(row["col"])
            if not 0 <= layer < nlay:
                errors.append(f"{filename}: layer {layer + 1} fuera de rango 1-{nlay}")
            if not 0 <= row_index < nrow:
                errors.append(f"{filename}: row {row_index} fuera de rango 0-{nrow - 1}")
            if not 0 <= col_index < ncol:
                errors.append(f"{filename}: col {col_index} fuera de rango 0-{ncol - 1}")

        chd = pd.read_csv(self.data_dir / "contornos_carga.csv")
        require_columns(chd, "contornos_carga.csv", {"lado", "carga_m"})
        valid_sides = {"izquierdo", "derecho", "superior", "inferior"}
        for _, row in chd.iterrows():
            if str(row["lado"]).strip().lower() not in valid_sides:
                errors.append(f"contornos_carga.csv: lado no soportado '{row['lado']}'")
            if "layer" in chd.columns and not pd.isna(row.get("layer")) \
                    and str(row.get("layer")).strip().lower() not in {"all", "*", "todas"}:
                layer = self.layer_target(row.get("layer"))
                if not 0 <= layer < nlay:
                    errors.append(f"contornos_carga.csv: layer {layer + 1} fuera de rango 1-{nlay}")
            if "stress_period" in chd.columns:
                validate_period(row.get("stress_period"), "contornos_carga.csv")

        wells = self.csv_if_exists("pozos.csv")
        if wells is not None:
            require_columns(wells, "pozos.csv", {"row", "col", "rate_m3_dia"})
            for _, row in wells.iterrows():
                validate_cell(row, "pozos.csv")
                if "stress_period" in wells.columns:
                    validate_period(row.get("stress_period"), "pozos.csv")

        rivers = self.csv_if_exists("rio.csv")
        if rivers is not None:
            require_columns(rivers, "rio.csv", {"row", "col", "stage_m", "cond_m2_d", "river_bottom_m"})
            for _, row in rivers.iterrows():
                validate_cell(row, "rio.csv")
                if float(row["cond_m2_d"]) <= 0:
                    errors.append("rio.csv: cond_m2_d debe ser mayor que 0")
                if float(row["river_bottom_m"]) > float(row["stage_m"]):
                    errors.append("rio.csv: river_bottom_m no puede ser mayor que stage_m")
                if "stress_period" in rivers.columns:
                    validate_period(row.get("stress_period"), "rio.csv")

        recharge = self.csv_if_exists("recarga_periodos.csv")
        if recharge is not None:
            require_columns(recharge, "recarga_periodos.csv", {"stress_period", "recharge_m_d"})
            for _, row in recharge.iterrows():
                validate_period(row.get("stress_period"), "recarga_periodos.csv")
                if float(row["recharge_m_d"]) < 0:
                    errors.append("recarga_periodos.csv: recharge_m_d no puede ser negativa")

        return errors

    @staticmethod
    def stress_period_targets(value: object, periods: list[int]) -> list[int]:
        if pd.isna(value):
            return periods
        text = str(value).strip().lower()
        if text in {"", "all", "*"}:
            return periods
        return [int(float(text))]

    @staticmethod
    def layer_target(value: object, default_layer: int = 1) -> int:
        if pd.isna(value):
            return default_layer - 1
        return int(float(value)) - 1

    def read_stress_periods(self) -> pd.DataFrame:
        frame = self.csv_if_exists("stress_periods.csv")
        if frame is None:
            return pd.DataFrame(
                [{"stress_period": 0, "perlen_d": 1.0, "nstp": 1, "tsmult": 1.0, "steady_state": 1}]
            )
        frame = frame.copy()
        frame["stress_period"] = frame["stress_period"].astype(int)
        frame = frame.sort_values("stress_period").reset_index(drop=True)
        return frame

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
        if frame is None:
            return {
                "nlay": int(params["nlay"]),
                "top": params["top"],
                "botm": params["botm"],
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
            dem = self._dem_grid(int(params["nrow"]), int(params["ncol"]))
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

    def _load_idomain(self, nrow: int, ncol: int) -> "np.ndarray | None":
        """Mascara de celdas activas (idomain) desde resultados/gis/grilla_activa.csv.

        La produce `mfw gis` al intersectar la grilla con el dominio. Si existe, el
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

    def build_chd_data(self, frame: pd.DataFrame, nrow: int, ncol: int, periods: list[int],
                       active: "np.ndarray | None" = None, nlay: int = 1) -> dict[int, list[list[object]]]:
        def on(r: int, c: int) -> bool:
            return active is None or active[r, c] == 1

        # Convencion de filas: row 0 = primera fila del arreglo (sur, y=miny; los plots
        # usan origin='lower'). Por eso 'superior' = row 0 e 'inferior' = ultima fila.
        # Es consistente en todo el stack (prep, gis, plots); se documenta para evitar
        # confusion al leer 'superior/inferior'. Recomendado usar izquierdo/derecho.
        chd_spd = {period: [] for period in periods}
        for _, row in frame.iterrows():
            side = str(row["lado"]).strip().lower()
            head = float(row["carga_m"])
            # 'layer = all' aplica la carga de borde a TODAS las capas (borde lateral
            # completo); si no, a la capa indicada (por defecto la 1).
            raw = str(row.get("layer", 1)).strip().lower()
            target_layers = list(range(nlay)) if raw in {"all", "*", "todas"} else [self.layer_target(row.get("layer", 1))]
            cells: list[list[object]] = []
            for layer in target_layers:
                if side == "izquierdo":
                    cells += [[(layer, r, 0), head] for r in range(nrow) if on(r, 0)]
                elif side == "derecho":
                    cells += [[(layer, r, ncol - 1), head] for r in range(nrow) if on(r, ncol - 1)]
                elif side == "superior":
                    cells += [[(layer, 0, c), head] for c in range(1, ncol - 1) if on(0, c)]
                elif side == "inferior":
                    cells += [[(layer, nrow - 1, c), head] for c in range(1, ncol - 1) if on(nrow - 1, c)]
                else:
                    raise ValueError(f"Lado no soportado en contornos_carga.csv: {side}")

            for period in self.stress_period_targets(row.get("stress_period"), periods):
                chd_spd[period].extend(cells)
        return chd_spd

    def build_wel_data(self, frame: pd.DataFrame | None, periods: list[int],
                       active: "np.ndarray | None" = None) -> dict[int, list[list[object]]]:
        wel_spd = {period: [] for period in periods}
        if frame is None:
            return wel_spd

        for _, row in frame.iterrows():
            r, c = int(row["row"]), int(row["col"])
            if active is not None and active[r, c] == 0:
                logger.warning("pozos.csv: pozo en celda inactiva (row=%d, col=%d) omitido.", r, c)
                continue
            entry = [(self.layer_target(row.get("layer", 1)), r, c), float(row["rate_m3_dia"])]
            for period in self.stress_period_targets(row.get("stress_period"), periods):
                wel_spd[period].append(entry)
        return wel_spd

    def build_riv_data(self, frame: pd.DataFrame | None, periods: list[int],
                       active: "np.ndarray | None" = None) -> dict[int, list[list[object]]]:
        riv_spd = {period: [] for period in periods}
        if frame is None:
            return riv_spd

        for _, row in frame.iterrows():
            r, c = int(row["row"]), int(row["col"])
            if active is not None and active[r, c] == 0:
                continue
            entry = [
                (self.layer_target(row.get("layer", 1)), r, c),
                float(row["stage_m"]),
                float(row["cond_m2_d"]),
                float(row["river_bottom_m"]),
            ]
            for period in self.stress_period_targets(row.get("stress_period"), periods):
                riv_spd[period].append(entry)
        return riv_spd

    def build_drn_data(self, frame: pd.DataFrame | None, periods: list[int],
                       active: "np.ndarray | None" = None) -> dict[int, list[list[object]]]:
        """Drenes (DRN): drenan agua solo cuando la napa supera la cota del dren.

        drn.csv: row, col, [layer], elev_m (cota del dren), cond_m2_d, [stress_period].
        Util para manantiales, drenes de mina, afloramientos y rebose de vegas/humedales.
        """
        drn_spd: dict[int, list] = {period: [] for period in periods}
        if frame is None:
            return drn_spd
        for _, row in frame.iterrows():
            r, c = int(row["row"]), int(row["col"])
            if active is not None and active[r, c] == 0:
                continue
            entry = [(self.layer_target(row.get("layer", 1)), r, c),
                     float(row["elev_m"]), float(row["cond_m2_d"])]
            for period in self.stress_period_targets(row.get("stress_period"), periods):
                drn_spd[period].append(entry)
        return drn_spd

    def build_ghb_data(self, frame: pd.DataFrame | None, periods: list[int],
                       active: "np.ndarray | None" = None) -> dict[int, list[list[object]]]:
        """Borde de carga general (GHB): borde regional con conductancia (semi-permeable).

        ghb.csv: row, col, [layer], head_m (carga externa), cond_m2_d, [stress_period].
        Mas realista que CHD para representar el aporte/salida del acuifero regional.
        """
        ghb_spd: dict[int, list] = {period: [] for period in periods}
        if frame is None:
            return ghb_spd
        for _, row in frame.iterrows():
            r, c = int(row["row"]), int(row["col"])
            if active is not None and active[r, c] == 0:
                continue
            entry = [(self.layer_target(row.get("layer", 1)), r, c),
                     float(row["head_m"]), float(row["cond_m2_d"])]
            for period in self.stress_period_targets(row.get("stress_period"), periods):
                ghb_spd[period].append(entry)
        return ghb_spd

    def add_evt(self, gwf, params: dict, periods: list[int], nrow: int, ncol: int) -> bool:
        """Evapotranspiracion freatica (EVT): descarga del acuifero cuando la napa es somera.

        evt_periodos.csv: stress_period, rate_m_d (ET maxima), extinction_depth_m. La superficie
        es el terreno (top_dem_grid o top). Es el mecanismo fisico de las vegas/bofedales/GDE:
        cuando la napa esta cerca de la superficie, el acuifero pierde agua por evapotranspiracion.
        Opt-in: solo si existe evt_periodos.csv.
        """
        frame = self.csv_if_exists("evt_periodos.csv")
        if frame is None:
            return False
        surface = self._dem_grid(nrow, ncol)
        surf_obj: object = surface if surface is not None else float(params["top"])
        rate = {period: 0.0 for period in periods}
        depth = {period: 2.0 for period in periods}
        for _, row in frame.iterrows():
            for period in self.stress_period_targets(row.get("stress_period"), periods):
                rate[period] = float(row["rate_m_d"])
                depth[period] = float(row.get("extinction_depth_m", 2.0))
        flopy.mf6.ModflowGwfevta(gwf, surface=surf_obj, rate=rate, depth=depth)
        logger.info("EVT (evapotranspiracion freatica) activada: ET maxima %.2g m/d, "
                    "profundidad de extincion %.1f m.", max(rate.values()), max(depth.values()))
        return True

    def _recarga_multiplicador(self, nrow: int, ncol: int) -> "np.ndarray | None":
        """Multiplicador de recarga por celda desde recarga_zonas.csv (coef. de infiltración).

        Distribuye la recarga segun el coeficiente de infiltracion de cada unidad geologica
        (rasterizado por `prep`). Se normaliza a media 1 sobre las celdas con dato, de modo que
        la recarga MEDIA de la cuenca se conserva y solo cambia su reparto espacial. Celdas sin
        unidad reciben la recarga media (multiplicador 1).
        """
        path = self.data_dir / "recarga_zonas.csv"
        if not path.exists():
            return None
        try:
            coef = pd.read_csv(path, header=None).to_numpy(dtype=float)
        except Exception:  # noqa: BLE001
            return None
        if coef.shape != (nrow, ncol):
            logger.warning("recarga_zonas.csv no calza con la grilla (%s vs %dx%d); recarga uniforme.",
                           coef.shape, nrow, ncol)
            return None
        valido = np.isfinite(coef) & (coef > 0)
        if not valido.any():
            return None
        media = float(coef[valido].mean())
        if media <= 0:
            return None
        return np.where(valido, coef / media, 1.0)

    def build_recharge_data(self, params: dict[str, float], periods: list[int]):
        frame = self.csv_if_exists("recarga_periodos.csv")
        mult = self._recarga_multiplicador(int(params["nrow"]), int(params["ncol"]))

        # Valor base (escalar) por periodo
        base = {period: float(params["recharge"]) for period in periods}
        if frame is not None:
            for _, row in frame.iterrows():
                for period in self.stress_period_targets(row.get("stress_period"), periods):
                    base[period] = float(row["recharge_m_d"])

        if mult is not None:                       # recarga distribuida por coef. de infiltracion
            logger.info("Recarga distribuida espacialmente por coef. de infiltracion (recarga_zonas.csv).")
            return {period: float(valor) * mult for period, valor in base.items()}
        if frame is None:                          # comportamiento previo: escalar uniforme
            return float(params["recharge"])
        return base                                # dict de escalares uniformes por periodo

    @staticmethod
    def build_storage_package(gwf: flopy.mf6.ModflowGwf, layers: dict[str, object], stress_periods: pd.DataFrame) -> bool:
        has_transient = not stress_periods["steady_state"].astype(int).all()
        if not has_transient:
            return False

        steady_state = {
            int(row["stress_period"]): True
            for _, row in stress_periods.iterrows()
            if int(row["steady_state"]) == 1
        }
        transient = {
            int(row["stress_period"]): True
            for _, row in stress_periods.iterrows()
            if int(row["steady_state"]) == 0
        }
        flopy.mf6.ModflowGwfsto(
            gwf,
            iconvert=layers["iconvert"],
            ss=layers["ss"],
            sy=layers["sy"],
            steady_state=steady_state,
            transient=transient,
        )
        return True

    def plot_outputs(self, head_file: flopy.utils.HeadFile, wells_frame: pd.DataFrame | None, stress_periods: pd.DataFrame) -> list[Path]:
        outputs: list[Path] = []
        times = head_file.get_times()
        head = head_file.get_data(totim=times[-1]) if times else head_file.get_data()

        fig, axis = plt.subplots(figsize=(8, 6))
        image = axis.imshow(head[0, :, :], origin="lower", cmap="viridis")
        axis.set_title(f"{self.model_name} - carga hidraulica final")
        axis.set_xlabel("col")
        axis.set_ylabel("row")
        if wells_frame is not None:
            for _, row in wells_frame.drop_duplicates(subset=["row", "col"]).iterrows():
                axis.plot(int(row["col"]), int(row["row"]), "wo", markeredgecolor="black")
        fig.colorbar(image, ax=axis, label="m")
        fig.tight_layout()
        figure_path = self.workspace / f"{self.model_name}_heads.png"
        fig.savefig(figure_path, dpi=200, bbox_inches="tight")
        plt.close(fig)
        outputs.append(figure_path)

        if len(times) > 1 and wells_frame is not None and not wells_frame.empty:
            first_well = wells_frame.iloc[0]
            layer = self.layer_target(first_well.get("layer", 1))
            row = int(first_well["row"])
            col = int(first_well["col"])
            heads = [float(head_file.get_data(totim=time)[layer, row, col]) for time in times]
            fig2, axis2 = plt.subplots(figsize=(8, 4))
            axis2.plot(times, heads, marker="o")
            axis2.set_title(f"Evolucion temporal en {first_well.get('nombre', 'pozo')}")
            axis2.set_xlabel("tiempo acumulado")
            axis2.set_ylabel("carga (m)")
            axis2.grid(alpha=0.3)
            fig2.tight_layout()
            timeseries_path = self.workspace / f"{self.model_name}_timeseries.png"
            fig2.savefig(timeseries_path, dpi=200, bbox_inches="tight")
            plt.close(fig2)
            outputs.append(timeseries_path)

        return outputs

    def build_simulation(self) -> flopy.mf6.MFSimulation:
        """Construye el modelo completo sin ejecutarlo."""
        ensure_flopy_bin_on_path()  # asegura que mf6 este en PATH (conda run / get-modflow)
        params = self.read_parameters()
        heads_frame = pd.read_csv(self.data_dir / "contornos_carga.csv")
        wells_frame = self.csv_if_exists("pozos.csv")
        river_frame = self.csv_if_exists("rio.csv")
        stress_periods = self.read_stress_periods()
        layers = self.build_layer_config(params, drapear=self.drapear_dem)

        nlay = int(layers["nlay"])
        nrow = int(params["nrow"])
        ncol = int(params["ncol"])
        periods = stress_periods["stress_period"].astype(int).tolist()
        perioddata = [
            (float(row["perlen_d"]), int(row["nstp"]), float(row["tsmult"]))
            for _, row in stress_periods.iterrows()
        ]

        active = self._load_idomain(nrow, ncol)

        sim = flopy.mf6.MFSimulation(sim_name=self.sim_name, sim_ws=str(self.workspace),
                                     exe_name=resolve_exe("mf6") or "mf6")
        flopy.mf6.ModflowTdis(sim, nper=len(perioddata), perioddata=perioddata, time_units="DAYS")
        # Con geometría drapeada (acuífero libre que sigue el terreno) se activa la
        # formulación Newton-Raphson, que maneja el secado/rehumedecimiento de celdas.
        gwf_kwargs: dict[str, object] = {}
        if self.drapear_dem:
            gwf_kwargs["newtonoptions"] = "NEWTON UNDER_RELAXATION"
        gwf = flopy.mf6.ModflowGwf(sim, modelname=self.model_name, save_flows=True, **gwf_kwargs)
        dis_kwargs: dict[str, object] = {}
        if active is not None:
            dis_kwargs["idomain"] = np.broadcast_to(active, (nlay, nrow, ncol)).copy()
            logger.info("idomain aplicado: %d/%d celdas activas (dominio recortado).",
                        int(active.sum()), nrow * ncol)
        flopy.mf6.ModflowGwfdis(
            gwf,
            length_units="METERS",   # todo el modelo trabaja en metros (coherente con time_units=DAYS)
            nlay=nlay,
            nrow=nrow,
            ncol=ncol,
            delr=params["delr"],
            delc=params["delc"],
            top=layers["top"],
            botm=layers["botm"],
            **dis_kwargs,
        )
        # Con drapeado, arrancar en el terreno (estabiliza Newton en acuífero libre).
        if self.drapear_dem and not np.isscalar(layers["top"]):
            strt = np.broadcast_to(np.asarray(layers["top"], dtype=float), (nlay, nrow, ncol)).copy()
        else:
            strt = params["starting_head"]
        flopy.mf6.ModflowGwfic(gwf, strt=strt)
        flopy.mf6.ModflowGwfnpf(gwf, icelltype=layers["icelltype"], k=layers["k"], k33=layers["k33"],
                                save_specific_discharge=True)

        recharge = self.build_recharge_data(params, periods)
        flopy.mf6.ModflowGwfrcha(gwf, recharge=recharge)
        flopy.mf6.ModflowGwfchd(gwf, stress_period_data=self.build_chd_data(heads_frame, nrow, ncol, periods, active, nlay))

        wel_data = self.build_wel_data(wells_frame, periods, active)
        if any(wel_data.values()):
            flopy.mf6.ModflowGwfwel(gwf, stress_period_data=wel_data)

        riv_data = self.build_riv_data(river_frame, periods, active)
        if any(riv_data.values()):
            flopy.mf6.ModflowGwfriv(gwf, stress_period_data=riv_data)

        # Paquetes de borde opcionales (data-driven: solo si existe el CSV) ---------------
        drn_data = self.build_drn_data(self.csv_if_exists("drn.csv"), periods, active)
        if any(drn_data.values()):
            flopy.mf6.ModflowGwfdrn(gwf, stress_period_data=drn_data)
        ghb_data = self.build_ghb_data(self.csv_if_exists("ghb.csv"), periods, active)
        if any(ghb_data.values()):
            flopy.mf6.ModflowGwfghb(gwf, stress_period_data=ghb_data)
        self.add_evt(gwf, params, periods, nrow, ncol)

        self.build_storage_package(gwf, layers, stress_periods)
        flopy.mf6.ModflowGwfoc(
            gwf,
            head_filerecord=f"{self.model_name}.hds",
            budget_filerecord=f"{self.model_name}.cbc",
            saverecord=[("HEAD", "ALL"), ("BUDGET", "ALL")],
        )
        if self.drapear_dem:
            # Solver robusto para acuífero libre drapeado (Newton): under-relaxation DBD +
            # backtracking + BICGSTAB y más iteraciones, para tolerar el secado de celdas.
            flopy.mf6.ModflowIms(
                sim, complexity="COMPLEX", linear_acceleration="BICGSTAB",
                outer_maximum=500, inner_maximum=200,
                outer_dvclose=1e-3, inner_dvclose=1e-4,
                under_relaxation="DBD", under_relaxation_theta=0.7,
                under_relaxation_kappa=0.1, under_relaxation_gamma=0.0,
                backtracking_number=20, backtracking_tolerance=2.0,
                backtracking_reduction_factor=0.6, backtracking_residual_limit=100.0,
            )
        else:
            flopy.mf6.ModflowIms(sim, complexity="MODERATE")

        sim.write_simulation(silent=True)
        return sim

    def run_simulation(self, sim: flopy.mf6.MFSimulation) -> None:
        """Ejecuta una simulacion MODFLOW ya construida."""
        success, _ = sim.run_simulation(silent=True)
        if not success:
            raise SystemExit(f"El modelo '{self.model_name}' no convergio.")

    def postprocess(self) -> list[Path]:
        """Genera figuras 2D y resumen de resultados."""
        hds_path = self.workspace / f"{self.model_name}.hds"
        hds = flopy.utils.HeadFile(str(hds_path), precision="double")
        wells_frame = self.csv_if_exists("pozos.csv")
        stress_periods = self.read_stress_periods()
        outputs = self.plot_outputs(hds, wells_frame, stress_periods)
        final_head = hds.get_data(totim=hds.get_times()[-1]) if hds.get_times() else hds.get_data()

        summary_lines = [
            f"Modelo: {self.model_name}",
            f"Archivo HDS: {hds_path.name}",
            f"Numero de capas: {final_head.shape[0]}",
            f"Numero de periodos guardados: {len(hds.get_times())}",
            f"Carga minima final: {final_head.min():.2f} m",
            f"Carga maxima final: {final_head.max():.2f} m",
            f"Carga media final: {final_head.mean():.2f} m",
        ]
        summary_lines.extend([f"Salida: {path.name}" for path in outputs])
        (self.workspace / f"resumen_{self.model_name}.txt").write_text("\n".join(summary_lines), encoding="utf-8")

        return outputs

    def build_and_run(self, postprocess: bool = True) -> flopy.mf6.MFSimulation:
        """Construye, ejecuta y opcionalmente postprocesa el modelo completo."""
        sim = self.build_simulation()
        self.run_simulation(sim)
        if postprocess:
            self.postprocess()

        return sim
