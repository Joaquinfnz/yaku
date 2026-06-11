#!/usr/bin/env python3
"""Motor simple: construye un modelo MODFLOW 6 a partir de CSV.

Soporta multicapa y regimen transiente. Es el motor "simple/didactico" del
workflow (para casos rapidos); los proyectos reales pueden usar ademas el motor
profesional basado en modflow-setup (ver yaku.setup).

Migrado desde 04_modelo_base/modelo_desde_datos.py. Cambios respecto al original:
- logger "yaku" (antes "modflow_pipeline").
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

from yaku.binaries import ensure_flopy_bin_on_path, resolve_exe
from yaku.builder.bordes import BordesMixin
from yaku.builder.geometria import GeometriaMixin

logger = logging.getLogger("yaku")


class ModflowModelBuilder(GeometriaMixin, BordesMixin):
    """Construye un modelo MODFLOW 6 desde datos CSV con validaciones."""

    def __init__(self, data_dir: Path, workspace: Path, model_name: str = "modelo",
                 *, drapear_dem: bool = False, newton: bool | None = None) -> None:
        self.data_dir = Path(data_dir)
        self.workspace = Path(workspace)
        self.model_name = model_name
        self.sim_name = model_name
        self.drapear_dem = drapear_dem
        self.newton = newton  # True=forzar, False=desactivar, None=auto-detectar
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
        coherencia geometrica (ver yaku.builder.validation).
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
            row_index = self.row_target(row.get("row", 1))
            col_index = self.col_target(row.get("col", 1))
            if not 0 <= layer < nlay:
                errors.append(f"{filename}: layer {layer + 1} fuera de rango 1-{nlay}")
            if not 0 <= row_index < nrow:
                errors.append(f"{filename}: row {row_index + 1} fuera de rango 1-{nrow}")
            if not 0 <= col_index < ncol:
                errors.append(f"{filename}: col {col_index + 1} fuera de rango 1-{ncol}")

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

        sfr = self.csv_if_exists("sfr.csv")
        if sfr is not None:
            require_columns(sfr, "sfr.csv", {"row", "col"})
            for _, row in sfr.iterrows():
                validate_cell(row, "sfr.csv")
                if "slope" in sfr.columns and float(row.get("slope", 0)) < 0:
                    errors.append("sfr.csv: slope no puede ser negativa")
                if "mannings_n" in sfr.columns and float(row.get("mannings_n", 0)) <= 0:
                    errors.append("sfr.csv: mannings_n debe ser positivo")

        uzf = self.csv_if_exists("uzf.csv")
        if uzf is not None:
            require_columns(uzf, "uzf.csv", {"row", "col"})
            for _, row in uzf.iterrows():
                validate_cell(row, "uzf.csv")
                if "vks_m_d" in uzf.columns and float(row.get("vks_m_d", 0)) <= 0:
                    errors.append("uzf.csv: vks_m_d debe ser positivo")

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

    @staticmethod
    def row_target(value: object, default: int = 1) -> int:
        """Convierte indice de fila 1-based (usuario) a 0-based (MODFLOW)."""
        if pd.isna(value):
            return default - 1
        return int(float(value)) - 1

    @staticmethod
    def col_target(value: object, default: int = 1) -> int:
        """Convierte indice de columna 1-based (usuario) a 0-based (MODFLOW)."""
        if pd.isna(value):
            return default - 1
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

        # Newton-Raphson: se activa si (a) el usuario lo pide, (b) hay celdas convertibles
        # (icelltype > 0), o (c) el modelo esta drapeado al DEM. Se desactiva solo si el
        # usuario lo pide explicitamente (newton=False).
        has_convertible = any(ic != 0 for ic in layers["icelltype"]) if isinstance(layers["icelltype"], list) else False
        use_newton = (
            self.newton is True
            or (self.newton is None and (self.drapear_dem or has_convertible))
        )

        sim = flopy.mf6.MFSimulation(sim_name=self.sim_name, sim_ws=str(self.workspace),
                                     exe_name=resolve_exe("mf6") or "mf6")
        flopy.mf6.ModflowTdis(sim, nper=len(perioddata), perioddata=perioddata, time_units="DAYS")
        gwf_kwargs: dict[str, object] = {}
        if use_newton:
            gwf_kwargs["newtonoptions"] = "NEWTON UNDER_RELAXATION"
            logger.info("Newton-Raphson activado (under_relaxation) para celdas convertibles.")
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
        # K por capa: escalar (parametros/capas_modelo) o campo distribuido si hay
        # k_field_capa{N}.csv (producto de la calibracion por pilot points).
        k_vals: object = layers["k"]
        k_fields = self._k_fields(nlay, nrow, ncol)
        if k_fields:
            base = list(k_vals) if isinstance(k_vals, list) else [k_vals] * nlay
            k_vals = [k_fields.get(i, base[i]) for i in range(nlay)]
            logger.info("K distribuida (pilot points) aplicada en capa(s): %s.",
                        ", ".join(str(i + 1) for i in sorted(k_fields)))
        flopy.mf6.ModflowGwfnpf(gwf, icelltype=layers["icelltype"], k=k_vals, k33=layers["k33"],
                                save_specific_discharge=True)

        # UZF (zona vadosa) reemplaza la recarga (RCH) y la ET (EVT) simples:
        # cuando esta presente, UZF aporta la infiltracion y la evapotranspiracion,
        # de modo que agregar RCH/EVT ademas duplicaria la recarga.
        uzf_present = self.csv_if_exists("uzf.csv") is not None
        if not uzf_present:
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
        if not uzf_present:
            self.add_evt(gwf, params, periods, nrow, ncol)

        # SFR (Streamflow Routing): data-driven, solo si existe sfr.csv
        sfr_frame = self.csv_if_exists("sfr.csv")
        if sfr_frame is not None:
            sfr_data = self.build_sfr_data(sfr_frame, params, periods, nrow, ncol, active)
            if sfr_data is not None:
                flopy.mf6.ModflowGwfsfr(
                    gwf,
                    nreaches=sfr_data["nreaches"],
                    packagedata=sfr_data["package_data"],
                    connectiondata=sfr_data["connection_data"],
                    perioddata=sfr_data["stress_period_data"],
                )

        # UZF (Unsaturated Zone Flow): data-driven, solo si existe uzf.csv
        self.add_uzf(gwf, params, periods, nrow, ncol, nlay)

        self.build_storage_package(gwf, layers, stress_periods)
        flopy.mf6.ModflowGwfoc(
            gwf,
            head_filerecord=f"{self.model_name}.hds",
            budget_filerecord=f"{self.model_name}.cbc",
            saverecord=[("HEAD", "ALL"), ("BUDGET", "ALL")],
        )
        if use_newton:
            # Solver robusto para celdas convertibles (Newton): under-relaxation DBD +
            # backtracking + BICGSTAB y mas iteraciones, para tolerar el secado de celdas.
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
