#!/usr/bin/env python3
"""Intrusion salina con MODFLOW 6 GWT + BUY (densidad variable; equivalente SEAWAT).

Migrado desde 11_intrusion_salina/intrusion_gwt_buy.py. Seccion vertical 20x1x40
con agua dulce continental (izquierda) y agua marina salina (derecha). Workspace
parametrizable.
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
    sim = flopy.mf6.MFSimulation(sim_name="intrusion", sim_ws=str(workspace),
                                 exe_name=resolve_exe("mf6") or "mf6")
    flopy.mf6.ModflowTdis(sim, nper=1, perioddata=[(3650.0, 80, 1.0)], time_units="DAYS")

    gwf = flopy.mf6.ModflowGwf(sim, modelname="flujo", save_flows=True)
    gwt = flopy.mf6.ModflowGwt(sim, modelname="salinidad", save_flows=True)

    nlay, nrow, ncol = 20, 1, 40
    delr, delc = 50.0, 1.0
    top = 0.0
    botm = np.linspace(-2.5, -50.0, nlay)

    flopy.mf6.ModflowGwfdis(gwf, nlay=nlay, nrow=nrow, ncol=ncol, delr=delr, delc=delc, top=top, botm=botm)
    flopy.mf6.ModflowGwfic(gwf, strt=0.5)
    flopy.mf6.ModflowGwfnpf(gwf, icelltype=1, k=20.0, k33=2.0, save_specific_discharge=True)

    chd = []
    for k in range(nlay):
        chd.append([(k, 0, 0), 0.8, 0.0])
        chd.append([(k, 0, ncol - 1), 0.0, 35.0])
    flopy.mf6.ModflowGwfchd(gwf, auxiliary=["SALINITY"], stress_period_data=chd, pname="CHD-1")
    flopy.mf6.ModflowGwfbuy(
        gwf,
        denseref=1000.0,
        density_filerecord="intrusion.density.bin",
        nrhospecies=1,
        packagedata=[(0, 0.7, 0.0, "salinidad", "SALINITY")],
        hhformulation_rhs=True,
    )
    flopy.mf6.ModflowGwfoc(
        gwf,
        head_filerecord="intrusion.hds",
        budget_filerecord="intrusion.cbc",
        saverecord=[("HEAD", "ALL"), ("BUDGET", "ALL")],
    )

    flopy.mf6.ModflowGwtdis(gwt, nlay=nlay, nrow=nrow, ncol=ncol, delr=delr, delc=delc, top=top, botm=botm)
    flopy.mf6.ModflowGwtic(gwt, strt=0.0)
    flopy.mf6.ModflowGwtmst(gwt, porosity=0.30)
    flopy.mf6.ModflowGwtadv(gwt, scheme="UPSTREAM")
    flopy.mf6.ModflowGwtdsp(gwt, alh=10.0, ath1=1.0, atv=0.1, diffc=0.0)
    flopy.mf6.ModflowGwtssm(gwt, sources=[["CHD-1", "AUX", "SALINITY"]])
    flopy.mf6.ModflowGwtoc(
        gwt,
        concentration_filerecord="intrusion.salinidad.ucn",
        budget_filerecord="intrusion.transport.cbc",
        saverecord=[("CONCENTRATION", "ALL"), ("BUDGET", "ALL")],
    )

    flopy.mf6.ModflowGwfgwt(sim, exgmnamea="flujo", exgmnameb="salinidad")
    ims_gwt = flopy.mf6.ModflowIms(sim, pname="ims_salinidad", filename="salinidad.ims", complexity="SIMPLE", linear_acceleration="BICGSTAB")
    ims_gwf = flopy.mf6.ModflowIms(sim, pname="ims_flujo", filename="flujo.ims", complexity="SIMPLE", linear_acceleration="BICGSTAB")
    sim.register_ims_package(ims_gwt, [gwt.name])
    sim.register_ims_package(ims_gwf, [gwf.name])
    return sim


def _fix_solution_order(workspace: Path) -> None:
    nam_path = Path(workspace) / "mfsim.nam"
    lines = nam_path.read_text(encoding="utf-8").splitlines()
    fixed: list[str] = []
    inside = False
    for line in lines:
        if line.strip().lower().startswith("begin solutiongroup"):
            fixed.extend([line, "  ims6  flujo.ims  flujo", "  ims6  salinidad.ims  salinidad"])
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


def plot_salinity(workspace: Path) -> Path:
    workspace = Path(workspace)
    ucn = flopy.utils.HeadFile(str(workspace / "intrusion.salinidad.ucn"), text="CONCENTRATION", precision="double")
    times = ucn.get_times()
    conc = ucn.get_data(totim=times[-1]) if times else ucn.get_data()
    section = np.asarray(conc[:, 0, :], dtype=float)

    fig, axis = plt.subplots(figsize=(10, 5))
    image = axis.imshow(section, origin="upper", aspect="auto", cmap="viridis", vmin=0, vmax=35)
    axis.set_title("Seccion conceptual de salinidad - GWT + BUY")
    axis.set_xlabel("columna del modelo")
    axis.set_ylabel("capa")
    fig.colorbar(image, ax=axis, label="salinidad relativa")
    fig.tight_layout()
    output = workspace / "seccion_salinidad.png"
    fig.savefig(output, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return output


def run(workspace: Path) -> Path:
    """Construye, ejecuta y grafica la intrusion salina. Devuelve la figura."""
    sim = build_simulation(workspace)
    sim.write_simulation(silent=True)
    _fix_solution_order(workspace)
    success, _ = sim.run_simulation(silent=True)
    if not success:
        raise SystemExit("El modelo de intrusion salina no convergio.")
    return plot_salinity(workspace)
