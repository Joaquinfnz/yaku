#!/usr/bin/env python3
"""Transporte de soluto con MODFLOW 6 GWF + GWT (alternativa moderna a MT3D).

Migrado desde 09_transporte/transporte_gwt.py. Modelo sintetico 1x20x50 con flujo
izquierda->derecha y una fuente de concentracion en el borde izquierdo. El
workspace de salida es parametrizable para integrarse al directorio del proyecto.
"""

from __future__ import annotations

from pathlib import Path

import flopy
import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from yaku.binaries import ensure_flopy_bin_on_path, resolve_exe


def build_simulation(workspace: Path) -> flopy.mf6.MFSimulation:
    workspace = Path(workspace)
    workspace.mkdir(parents=True, exist_ok=True)
    ensure_flopy_bin_on_path()
    sim = flopy.mf6.MFSimulation(sim_name="transporte", sim_ws=str(workspace),
                                 exe_name=resolve_exe("mf6") or "mf6")
    flopy.mf6.ModflowTdis(sim, nper=1, perioddata=[(365.0, 30, 1.0)], time_units="DAYS")

    gwf = flopy.mf6.ModflowGwf(sim, modelname="flujo", save_flows=True)
    gwt = flopy.mf6.ModflowGwt(sim, modelname="transporte", save_flows=True)

    nlay, nrow, ncol = 1, 20, 50
    delr = delc = 100.0
    top, botm = 10.0, 0.0

    flopy.mf6.ModflowGwfdis(gwf, nlay=nlay, nrow=nrow, ncol=ncol, delr=delr, delc=delc, top=top, botm=botm)
    flopy.mf6.ModflowGwfic(gwf, strt=10.0)
    flopy.mf6.ModflowGwfnpf(gwf, icelltype=1, k=10.0, save_specific_discharge=True)

    left = [[(0, r, 0), 10.0, 1.0] for r in range(nrow)]
    right = [[(0, r, ncol - 1), 8.0, 0.0] for r in range(nrow)]
    flopy.mf6.ModflowGwfchd(gwf, auxiliary=["CONCENTRATION"], stress_period_data=left + right, pname="CHD-1")
    flopy.mf6.ModflowGwfoc(
        gwf,
        head_filerecord="transporte.hds",
        budget_filerecord="transporte.cbc",
        saverecord=[("HEAD", "ALL"), ("BUDGET", "ALL")],
    )

    flopy.mf6.ModflowGwtdis(gwt, nlay=nlay, nrow=nrow, ncol=ncol, delr=delr, delc=delc, top=top, botm=botm)
    flopy.mf6.ModflowGwtic(gwt, strt=0.0)
    flopy.mf6.ModflowGwtmst(gwt, porosity=0.30)
    flopy.mf6.ModflowGwtadv(gwt, scheme="UPSTREAM")
    flopy.mf6.ModflowGwtdsp(gwt, alh=10.0, ath1=1.0, diffc=0.0)
    flopy.mf6.ModflowGwtssm(gwt, sources=[["CHD-1", "AUX", "CONCENTRATION"]])
    flopy.mf6.ModflowGwtoc(
        gwt,
        concentration_filerecord="transporte.concentration.ucn",
        budget_filerecord="transporte.transport.cbc",
        saverecord=[("CONCENTRATION", "ALL"), ("BUDGET", "ALL")],
    )

    flopy.mf6.ModflowGwfgwt(sim, exgmnamea="flujo", exgmnameb="transporte")
    ims_gwt = flopy.mf6.ModflowIms(sim, pname="ims_transporte", filename="transporte.ims", complexity="SIMPLE", linear_acceleration="BICGSTAB")
    ims_gwf = flopy.mf6.ModflowIms(sim, pname="ims_flujo", filename="flujo.ims", complexity="SIMPLE")
    sim.register_ims_package(ims_gwt, [gwt.name])
    sim.register_ims_package(ims_gwf, [gwf.name])
    return sim


def _fix_solution_order(workspace: Path) -> None:
    """Asegura que GWF se resuelva antes que GWT (requerido por GWF-GWT)."""
    nam_path = Path(workspace) / "mfsim.nam"
    lines = nam_path.read_text(encoding="utf-8").splitlines()
    fixed: list[str] = []
    inside = False
    for line in lines:
        if line.strip().lower().startswith("begin solutiongroup"):
            fixed.extend([line, "  ims6  flujo.ims  flujo", "  ims6  transporte.ims  transporte"])
            inside = True
            continue
        if inside and line.strip().lower().startswith("end solutiongroup"):
            fixed.append(line)
            inside = False
            continue
        if inside:
            continue
        fixed.append(line)
    nam_path.write_text("\n".join(fixed) + "\n", encoding="utf-8")


def plot_concentration(workspace: Path) -> Path:
    workspace = Path(workspace)
    ucn = flopy.utils.HeadFile(str(workspace / "transporte.concentration.ucn"), text="CONCENTRATION", precision="double")
    times = ucn.get_times()
    conc = ucn.get_data(totim=times[-1]) if times else ucn.get_data()
    arr = np.asarray(conc[0], dtype=float)

    fig, axis = plt.subplots(figsize=(9, 4))
    image = axis.imshow(arr, origin="lower", cmap="magma", vmin=0.0, vmax=max(1.0, float(arr.max())))
    axis.set_title("Concentracion final - GWT")
    axis.set_xlabel("col")
    axis.set_ylabel("row")
    fig.colorbar(image, ax=axis, label="concentracion relativa")
    fig.tight_layout()
    output = workspace / "concentracion_final.png"
    fig.savefig(output, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return output


def run(workspace: Path) -> Path:
    """Construye, ejecuta y grafica el modelo de transporte. Devuelve la figura."""
    sim = build_simulation(workspace)
    sim.write_simulation(silent=True)
    _fix_solution_order(workspace)
    success, _ = sim.run_simulation(silent=True)
    if not success:
        raise SystemExit("El modelo GWT no convergio.")
    return plot_concentration(workspace)
