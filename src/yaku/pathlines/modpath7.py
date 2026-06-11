#!/usr/bin/env python3
"""Trayectorias reales con MODPATH 7 (particle tracking sobre MODFLOW 6).

Reemplaza la aproximacion por gradiente cuando el binario mp7 esta disponible
(get-modflow lo instala en ~/.local/share/flopy/bin, tambien en Apple Silicon).

Capacidades:
- Backward tracking desde pozos -> zonas de captura y tiempos de viaje.
- Forward tracking desde recarga -> hacia donde va el agua.
Exporta pathlines y endpoints a CSV + figura.
"""

from __future__ import annotations

from pathlib import Path

import flopy
import matplotlib
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from yaku.binaries import ensure_flopy_bin_on_path, resolve_exe


def _load_gwf(workspace: Path, model_name: str):
    sim = flopy.mf6.MFSimulation.load(sim_ws=str(workspace), exe_name=resolve_exe("mf6") or "mf6", verbosity_level=0)
    gwf = sim.get_model(model_name)
    if gwf is None:
        # toma el primer modelo GWF disponible
        gwf = sim.get_model(list(sim.model_dict.keys())[0])
    return sim, gwf


def _well_nodes(gwf, data_dir: Path) -> list[int]:
    """Node numbers (0-based) de las celdas de pozo, para sembrar particulas."""
    nrow, ncol = gwf.modelgrid.nrow, gwf.modelgrid.ncol
    pozos = data_dir / "pozos.csv"
    nodes: list[int] = []
    if pozos.exists():
        df = pd.read_csv(pozos).drop_duplicates(subset=["layer", "row", "col"])
        for _, r in df.iterrows():
            lay = int(r.get("layer", 1)) - 1
            row = int(r["row"])
            col = int(r["col"])
            nodes.append(lay * nrow * ncol + row * ncol + col)
    return nodes


def run(workspace: Path, data_dir: Path, output_dir: Path, model_name: str = "modelo",
        direction: str = "backward") -> dict[str, Path]:
    """Corre MODPATH 7 y exporta pathlines, endpoints y figura.

    direction: 'backward' (zonas de captura desde pozos) | 'forward'.
    """
    ensure_flopy_bin_on_path()
    mp7_exe = resolve_exe("mp7")
    if mp7_exe is None:
        raise RuntimeError("mp7 (MODPATH 7) no encontrado. Instala con: get-modflow :flopy")

    workspace = Path(workspace)
    data_dir = Path(data_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    sim, gwf = _load_gwf(workspace, model_name)
    nodes = _well_nodes(gwf, data_dir)
    mp_name = f"{model_name}_mp7"

    # Particulas: en los pozos si hay (zona de captura); si no, en toda la grilla.
    kwargs = dict(
        modelname=mp_name,
        trackdir=direction,
        flowmodel=gwf,
        model_ws=str(workspace),
        exe_name=mp7_exe,
    )
    if nodes:
        kwargs["nodes"] = nodes
    mp = flopy.modpath.Modpath7.create_mp7(**kwargs)
    mp.write_input()
    success, buff = mp.run_model(silent=True)
    if not success:
        raise SystemExit("MODPATH 7 no completo la simulacion (revisa el .mplst).")

    # Leer salidas
    out: dict[str, Path] = {}
    pth_file = workspace / f"{mp_name}.mppth"
    end_file = workspace / f"{mp_name}.mpend"

    head = None
    try:
        hds = flopy.utils.HeadFile(str(workspace / f"{model_name}.hds"), precision="double")
        times = hds.get_times()
        head = hds.get_data(totim=times[-1]) if times else hds.get_data()
    except Exception:
        pass

    fig, ax = plt.subplots(figsize=(9, 7))
    pmv = flopy.plot.PlotMapView(model=gwf, ax=ax, layer=0)
    if head is not None:
        pmv.plot_array(head[0], cmap="viridis", alpha=0.7)
    pmv.plot_grid(linewidth=0.2, color="0.7")

    pathlines = []
    if pth_file.exists():
        pthobj = flopy.utils.PathlineFile(str(pth_file))
        pdata = pthobj.get_alldata()
        pmv.plot_pathline(pdata, layer="all", color="white", lw=0.6)
        for i, p in enumerate(pdata):
            for rec in p:
                pathlines.append({"particula": i, "x": float(rec["x"]), "y": float(rec["y"]),
                                  "z": float(rec["z"]), "tiempo": float(rec["time"])})
    endpoints = []
    if end_file.exists():
        epobj = flopy.utils.EndpointFile(str(end_file))
        ep = epobj.get_alldata()
        try:
            pmv.plot_endpoint(ep, direction="ending", colorbar=False, s=20, color="red")
        except Exception:
            pass
        for rec in ep:
            endpoints.append({
                "x0": float(rec["x0"]), "y0": float(rec["y0"]),
                "x": float(rec["x"]), "y": float(rec["y"]),
                "tiempo_viaje_dias": float(rec["time"]),
            })

    ax.set_title(f"MODPATH 7 - trayectorias ({direction})")
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    fig.tight_layout()
    out["figura"] = output_dir / "trayectorias_modpath7.png"
    fig.savefig(out["figura"], dpi=200, bbox_inches="tight")
    plt.close(fig)

    if pathlines:
        out["pathlines"] = output_dir / "pathlines_modpath7.csv"
        pd.DataFrame(pathlines).to_csv(out["pathlines"], index=False)
    if endpoints:
        out["endpoints"] = output_dir / "endpoints_modpath7.csv"
        ep_df = pd.DataFrame(endpoints)
        ep_df.to_csv(out["endpoints"], index=False)
        # Resumen de tiempos de viaje (zonas de captura)
        out["resumen"] = output_dir / "tiempos_viaje_resumen.csv"
        ep_df["tiempo_viaje_anos"] = ep_df["tiempo_viaje_dias"] / 365.25
        ep_df[["tiempo_viaje_dias", "tiempo_viaje_anos"]].describe().to_csv(out["resumen"])

    return out
