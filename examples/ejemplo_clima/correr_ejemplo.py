#!/usr/bin/env python3
"""Corre el ejemplo INTEGRADO clima-hidrogeologia de punta a punta (TRANSIENTE).

Flujo: construir datos -> prep -> recarga DIARIA y TRANSIENTE (3 anios) -> bordes que siguen
la topografia (drapeado) -> observaciones (experimento gemelo) -> rio -> build -> run
(transiente) -> indices clima-hidrogeologia -> calibrate -> predict -> report -> entregables.

Uso:  conda run -n modflow-workflow python examples/ejemplo_clima/correr_ejemplo.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

PROJ = Path(__file__).resolve().parent
RESULT = PROJ / "resultados"
CELLSIZE = 100.0
ESPESOR = 60.0
_log: list[str] = []


def log(msg: str = "") -> None:
    print(msg)
    _log.append(msg)


def run(args: list[str]) -> None:
    log("\n$ " + " ".join(args))
    res = subprocess.run(args, cwd=str(PROJ.parent.parent), capture_output=True, text=True)
    for line in ((res.stdout or "") + (res.stderr or "")).splitlines():
        low = line.lower()
        if any(k in low for k in ("deprecat", "warnings.warn", "userwarning", "ogr_write", "geographic crs")):
            continue
        log("  " + line)
    if res.returncode != 0:
        log(f"  [aviso] retorno {res.returncode}")


def construir_bordes() -> None:
    """Bordes de carga que siguen la topografia suave del valle (compatibles con drapeado)."""
    tablas = PROJ / "datos" / "tablas"
    pd.DataFrame([
        {"lado": "izquierdo", "carga_m": 815, "layer": "all", "stress_period": "all"},
        {"lado": "derecho", "carga_m": 801, "layer": "all", "stress_period": "all"},
    ]).to_csv(tablas / "contornos_carga.csv", index=False)
    pm = pd.read_csv(tablas / "parametros_modelo.csv").set_index("clave")
    pm.loc["starting_head", "valor"] = 818
    pm.reset_index().to_csv(tablas / "parametros_modelo.csv", index=False)
    log("  bordes que siguen la topografia (815->801 m), arranque humedo (818 m)")


def construir_observaciones() -> None:
    """Mapea observaciones.shp a row/col -> observaciones_nivel.csv + parametros de calibracion."""
    fuente, tablas = PROJ / "datos" / "fuente", PROJ / "datos" / "tablas"
    params = pd.read_csv(tablas / "parametros_modelo.csv").set_index("clave")["valor"]
    nrow, ncol = int(params["nrow"]), int(params["ncol"])
    minx, miny, _, _ = gpd.read_file(fuente / "dominio.shp").total_bounds
    piezo = gpd.read_file(fuente / "observaciones.shp")
    filas = []
    for i, r in piezo.iterrows():
        g = r.geometry
        col = min(max(int((g.x - minx) // CELLSIZE), 0), ncol - 1)
        row = min(max(int((g.y - miny) // CELLSIZE), 0), nrow - 1)
        grupo = "validacion" if i % 3 == 0 else "niveles"
        filas.append({"nombre": r.get("Name", f"PZ-{i + 1:02d}"), "layer": 1, "row": row, "col": col,
                      "stress_period": 0, "head_observado_m": round(float(r["waterHead"]), 2),
                      "peso": 1.0, "grupo": grupo})
    pd.DataFrame(filas).to_csv(tablas / "observaciones_nivel.csv", index=False)
    pd.DataFrame([
        {"nombre": "kx_layer_1", "tipo": "valor_capa", "archivo": "capas_modelo.csv", "campo": "kx_m_d",
         "selector": "layer=1", "valor_inicial": 12.0, "limite_inferior": 1.0, "limite_superior": 30.0,
         "transformacion": "log", "descripcion": "K horizontal acuifero libre (capa 1)"},
        {"nombre": "rch_mult", "tipo": "multiplicador", "archivo": "recarga_periodos.csv",
         "campo": "recharge_m_d", "selector": "all", "valor_inicial": 1.0, "limite_inferior": 0.3,
         "limite_superior": 3.0, "transformacion": "log", "descripcion": "Multiplicador de recarga"},
    ]).to_csv(tablas / "parametros_calibracion.csv", index=False)
    log(f"  observaciones: {len(filas)} piezometros")


def construir_rio() -> None:
    """Mapea rio.shp + DEM a rio.csv (en relacion con el acuifero)."""
    fuente, tablas = PROJ / "datos" / "fuente", PROJ / "datos" / "tablas"
    params = pd.read_csv(tablas / "parametros_modelo.csv").set_index("clave")["valor"]
    nrow, ncol = int(params["nrow"]), int(params["ncol"])
    minx, miny, _, _ = gpd.read_file(fuente / "dominio.shp").total_bounds
    dem = pd.read_csv(tablas / "top_dem_grid.csv", header=None).to_numpy()
    linea = gpd.read_file(fuente / "rio.shp").geometry.iloc[0]
    vistos, filas = set(), []
    for d in np.arange(0, linea.length, CELLSIZE / 2.0):
        p = linea.interpolate(d)
        col = min(max(int((p.x - minx) // CELLSIZE), 0), ncol - 1)
        row = min(max(int((p.y - miny) // CELLSIZE), 0), nrow - 1)
        if (row, col) in vistos:
            continue
        vistos.add((row, col))
        cota = float(dem[row, col])
        filas.append({"layer": 1, "row": row, "col": col, "stage_m": round(cota - 1.0, 2),
                      "cond_m2_d": 120.0, "river_bottom_m": round(cota - 3.0, 2), "stress_period": "all"})
    pd.DataFrame(filas).to_csv(tablas / "rio.csv", index=False)
    log(f"  rio.csv: {len(filas)} celdas de rio")


def twin() -> None:
    """Experimento gemelo: observaciones consistentes desde las cargas simuladas + ruido."""
    import flopy
    from yaku.config import load_config
    cfg = load_config(PROJ / "config.yaml")
    obs_csv = cfg.datos_dir / "observaciones_nivel.csv"
    hds = cfg.resultados_dir / f"{cfg.model_name}.hds"
    if not (obs_csv.exists() and hds.exists()):
        return
    hf = flopy.utils.HeadFile(str(hds), precision="double")
    t = hf.get_times()
    head = hf.get_data(totim=t[-1]) if t else hf.get_data()
    df = pd.read_csv(obs_csv)
    rng = np.random.default_rng(2026)
    nuevos = []
    for _, r in df.iterrows():
        k, i, j = int(r["layer"]) - 1, int(r["row"]), int(r["col"])
        sim = float(head[k, i, j])
        nuevos.append(round(sim + float(rng.normal(0, 0.25)), 2) if np.isfinite(sim) and abs(sim) < 1e29
                      else float(r["head_observado_m"]))
    df["head_observado_m"] = nuevos
    df.to_csv(obs_csv, index=False)
    log(f"  [twin] {len(df)} observaciones regeneradas (experimento gemelo)")


def main() -> int:
    RESULT.mkdir(parents=True, exist_ok=True)
    if not (PROJ / "datos" / "fuente" / "dem.tif").exists():
        log("Generando datos sinteticos...")
        subprocess.run([sys.executable, str(PROJ / "construir_datos.py")], check=False)

    proj = str(PROJ)
    log("=" * 70 + "\nEJEMPLO INTEGRADO clima-hidrogeologia (transiente, 3 anios)\n" + "=" * 70)

    run(["mfw", "prep", "--project", proj, "--cellsize", str(CELLSIZE), "--nlay", "3", "--espesor", str(ESPESOR)])
    # Recarga DIARIA -> mensual, TRANSIENTE (escribe stress_periods alineados)
    run(["mfw", "recarga", "--project", proj, "--metodo", "balance", "--transiente", "--k-percolacion", "0.05"])
    construir_bordes()
    construir_observaciones()
    construir_rio()
    run(["mfw", "check", "--project", proj])
    run(["mfw", "gis", "--project", proj])
    run(["mfw", "build", "--project", proj])
    run(["mfw", "run", "--project", proj])
    twin()                                   # obs consistentes con la corrida transiente
    run(["mfw", "indices", "--project", proj])     # SPI/SPEI, aridez, recarga, flujo base, desfase napa-clima
    run(["mfw", "calibrate", "--project", proj])
    run(["mfw", "predict", "--project", proj, "--uncertainty", "10"])
    run(["mfw", "report", "--project", proj, "--perfil", "sea"])
    run(["mfw", "entregables", "--project", proj, "--perfil", "sea"])

    log("\n" + "=" * 70 + "\nLISTO. Revisa informe/ y resultados/indices/.")
    (RESULT / "log_ejemplo.txt").write_text("\n".join(_log), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
