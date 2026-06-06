#!/usr/bin/env python3
"""Prediccion + incertidumbre (Etapa 6 ASTM / escenarios SEIA).

Dos analisis complementarios:

1. Escenario con/sin proyecto (drawdown): corre un escenario con el bombeo escalado
   por un factor y calcula el descenso de niveles respecto a la linea base. Es el
   "efecto del proyecto" tipico de un EIA/DIA.

2. Incertidumbre por Monte Carlo: muestrea los parametros dentro de sus rangos de
   calibracion (parametros_calibracion.csv) y propaga la incertidumbre a las cargas
   (mapas de media y desviacion estandar + bandas en las observaciones).
"""

from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path

import flopy
import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from mfworkflow.builder import ModflowModelBuilder
from mfworkflow.report.resultados import _dibujar_mapa, cargar_modelgrid

logger = logging.getLogger("mfworkflow")


def _final_head(workspace: Path, model_name: str) -> np.ndarray:
    hds = flopy.utils.HeadFile(str(Path(workspace) / f"{model_name}.hds"), precision="double")
    times = hds.get_times()
    return hds.get_data(totim=times[-1]) if times else hds.get_data()


def _copy_data(data_dir: Path, dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    for csv in Path(data_dir).glob("*.csv"):
        shutil.copy(csv, dest / csv.name)
    return dest


def scenario_drawdown(data_dir: Path, output_dir: Path, *, factor: float = 1.5,
                      model_name: str = "modelo", drapear_dem: bool = False) -> dict[str, Path]:
    """Descenso de niveles al escalar el bombeo por `factor` (con vs sin proyecto)."""
    data_dir = Path(data_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="mfw_pred_") as tmp:
        tmp = Path(tmp)
        base_ws = tmp / "base"
        scen_ws = tmp / "scen"

        # Linea base
        ModflowModelBuilder(data_dir, base_ws, model_name=model_name,
                            drapear_dem=drapear_dem).build_and_run(postprocess=False)
        h_base = _final_head(base_ws, model_name)

        # Escenario: bombeo escalado
        scen_data = _copy_data(data_dir, tmp / "datos")
        pozos = scen_data / "pozos.csv"
        if pozos.exists():
            df = pd.read_csv(pozos)
            df["rate_m3_dia"] = df["rate_m3_dia"].astype(float) * factor
            df.to_csv(pozos, index=False)
        ModflowModelBuilder(scen_data, scen_ws, model_name=model_name,
                            drapear_dem=drapear_dem).build_and_run(postprocess=False)
        h_scen = _final_head(scen_ws, model_name)
        grid = cargar_modelgrid(base_ws, model_name)  # coordenadas reales (antes de borrar el tmp)

    inact = (np.abs(h_base[0]) >= 1e29) | (np.abs(h_scen[0]) >= 1e29)
    drawdown = np.ma.masked_where(inact, h_base[0] - h_scen[0])  # descenso (m), capa superior

    out: dict[str, Path] = {}
    out["mapa"] = output_dir / "descenso_escenario.png"
    _dibujar_mapa(drawdown, grid, out["mapa"],
                  titulo=f"Descenso de niveles (factor bombeo x{factor})",
                  cbar_label="descenso (m)", cmap="RdBu_r", isopiezas=True)

    out["resumen"] = output_dir / "descenso_resumen.csv"
    pd.DataFrame([{
        "factor_bombeo": factor,
        "descenso_max_m": float(np.nanmax(drawdown)),
        "descenso_medio_m": float(np.nanmean(drawdown)),
        "descenso_min_m": float(np.nanmin(drawdown)),
    }]).to_csv(out["resumen"], index=False)
    return out


def _apply_multiplier(frame: pd.DataFrame, field: str, mask, value: float) -> None:
    frame.loc[mask, field] = frame.loc[mask, field].astype(float) * value


def monte_carlo(data_dir: Path, calib_params: Path, output_dir: Path, *, n: int = 30,
                seed: int = 42, model_name: str = "modelo", drapear_dem: bool = False) -> dict[str, Path]:
    """Propaga incertidumbre muestreando los parametros de calibracion (log-uniforme)."""
    data_dir = Path(data_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)

    defs = pd.read_csv(calib_params)
    # Avisa una sola vez si algun parametro apunta a un archivo que no existe
    # (multiplicador inerte): el usuario debe saber por que no tiene efecto.
    for archivo in defs["archivo"].astype(str).unique():
        if not (data_dir / archivo).exists():
            logger.warning("Parametro de calibracion apunta a '%s' que no existe en %s; "
                           "ese parametro no tendra efecto.", archivo, data_dir)
    heads = []
    with tempfile.TemporaryDirectory(prefix="mfw_mc_") as tmp:
        tmp = Path(tmp)
        for i in range(n):
            di = _copy_data(data_dir, tmp / f"d{i}")
            for _, d in defs.iterrows():
                lo, hi = float(d["limite_inferior"]), float(d["limite_superior"])
                if str(d.get("transformacion", "")).lower() == "log":
                    val = float(np.exp(rng.uniform(np.log(lo), np.log(hi))))
                else:
                    val = float(rng.uniform(lo, hi))
                path = di / str(d["archivo"])
                if not path.exists():
                    continue
                frame = pd.read_csv(path)
                field, selector, kind = str(d["campo"]), str(d["selector"]), str(d["tipo"])
                mask = pd.Series(True, index=frame.index)
                if "=" in selector:
                    k, raw = selector.split("=", 1)
                    mask = frame[k.strip()].astype(str) == raw.strip()
                if kind == "multiplicador":
                    _apply_multiplier(frame, field, mask, val)
                else:
                    frame.loc[mask, field] = val
                frame.to_csv(path, index=False)
            ws = tmp / f"w{i}"
            try:
                ModflowModelBuilder(di, ws, model_name=model_name,
                                    drapear_dem=drapear_dem).build_and_run(postprocess=False)
                heads.append(_final_head(ws, model_name)[0])
            except SystemExit:
                continue  # no convergio: esperable en algunas realizaciones
            except Exception as exc:  # noqa: BLE001 - bug real (datos/import): que se vea
                logger.warning("Realizacion %d fallo (no por convergencia): %s", i, exc)
                continue

    if not heads:
        raise SystemExit("Monte Carlo: ninguna realizacion produjo resultados "
                         "(revisa los warnings: puede ser un error de datos, no de convergencia).")
    stack = np.array(heads)
    mean_h = stack.mean(axis=0)
    std_h = stack.std(axis=0)

    out: dict[str, Path] = {}
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    im0 = axes[0].imshow(mean_h, origin="lower", cmap="viridis")
    axes[0].set_title("Carga media (n=%d)" % len(heads))
    fig.colorbar(im0, ax=axes[0], label="m")
    im1 = axes[1].imshow(std_h, origin="lower", cmap="magma")
    axes[1].set_title("Incertidumbre (desv. estandar)")
    fig.colorbar(im1, ax=axes[1], label="m")
    fig.tight_layout()
    out["mapa"] = output_dir / "incertidumbre_montecarlo.png"
    fig.savefig(out["mapa"], dpi=200, bbox_inches="tight")
    plt.close(fig)

    out["resumen"] = output_dir / "incertidumbre_resumen.csv"
    pd.DataFrame([{
        "realizaciones": len(heads),
        "incertidumbre_media_m": float(std_h.mean()),
        "incertidumbre_max_m": float(std_h.max()),
    }]).to_csv(out["resumen"], index=False)
    return out
