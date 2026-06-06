#!/usr/bin/env python3
"""Visualizacion 3D del modelo (estilo gidahatari / Hatari Labs).

Exporta el modelo y las cargas a VTK (.vtu) para abrir en ParaView o PyVista, y
ademas intenta renderizar un PNG 3D off-screen con PyVista. El VTK es la salida
robusta (no depende de display); el PNG es un extra cuando hay OpenGL disponible.
"""

from __future__ import annotations

import logging
from pathlib import Path

import flopy
import numpy as np

from mfworkflow.binaries import resolve_exe

logger = logging.getLogger("mfworkflow")


def _load_gwf(workspace: Path, model_name: str):
    sim = flopy.mf6.MFSimulation.load(sim_ws=str(workspace), exe_name=resolve_exe("mf6") or "mf6",
                                      verbosity_level=0)
    gwf = sim.get_model(model_name) or sim.get_model(list(sim.model_dict.keys())[0])
    return gwf


def _buscar_paquete(gwf, tipo: str):
    """Encuentra un paquete por tipo ('riv','wel','chd') de forma robusta."""
    for nombre in (tipo, f"{tipo}_0", tipo.upper()):
        pkg = gwf.get_package(nombre)
        if pkg is not None:
            return pkg
    for pkg in getattr(gwf, "packagelist", []):
        if getattr(pkg, "package_type", "").lower() == tipo:
            return pkg
    return None


def _marcador_paquete(gwf, nombre_pkg: str, shape) -> "np.ndarray | None":
    """Array (mismo shape del modelo) con 1 en las celdas del paquete, 0 si no."""
    pkg = _buscar_paquete(gwf, nombre_pkg)
    if pkg is None:
        return None
    try:
        periodos = pkg.stress_period_data.get_data()  # dict {periodo: recarray}
    except Exception:  # noqa: BLE001
        return None
    if not periodos:
        return None
    arr = np.zeros(shape)
    encontrado = False
    for spd in periodos.values():               # union de celdas en todos los periodos
        if spd is None:
            continue
        for rec in spd:
            try:
                arr[rec["cellid"]] = 1
                encontrado = True
            except Exception:  # noqa: BLE001
                continue
    return arr if encontrado else None


def _arrays_modelo(gwf) -> dict:
    """Arrays del modelo para colorear el 3D: K (litologia), recarga y marcadores."""
    out: dict = {}
    shape = gwf.modelgrid.shape  # (nlay,nrow,ncol) o (nlay,ncpl)

    # K horizontal por celda = litologia / permeabilidad del modelo
    try:
        k = gwf.npf.k.array
        if k is not None:
            out["K_m_d"] = np.asarray(k, dtype=float)
    except Exception:  # noqa: BLE001
        pass

    # Recarga (lluvia) en la capa superior -> array completo con la capa 0 cargada
    try:
        rch = gwf.rcha.recharge.array
        rch = np.asarray(rch, dtype=float)
        full = np.zeros(shape)
        full[0] = rch.reshape(shape[1:]) if rch.size == np.prod(shape[1:]) else rch.ravel()[: int(np.prod(shape[1:]))].reshape(shape[1:])
        out["recarga_m_d"] = full
    except Exception:  # noqa: BLE001
        pass

    # Marcadores de elementos: rio, pozos y borde de carga
    for nombre_pkg, etiqueta in (("riv", "rio"), ("wel", "pozos"), ("chd", "borde_chd")):
        marca = _marcador_paquete(gwf, nombre_pkg, shape)
        if marca is not None:
            out[etiqueta] = marca
    return out


def escena_hidrogeologica(vtk_path: Path, output_dir: Path, model_name: str) -> "Path | None":
    """Render PNG de una escena 3D con actores diferenciados (estilo Visual MODFLOW Flex).

    A partir del VTK del modelo (que ya trae los arrays K_m_d, carga_m y marcadores
    rio/pozos/borde_chd) arma una escena con: la litologia como volumen coloreado por K,
    la napa (carga) como superficie superior semitransparente, el rio como celdas azules,
    los pozos como tubos verticales rojos y ejes con exageracion vertical. Off-screen;
    devuelve el PNG o None si no hay OpenGL disponible.
    """
    try:
        import numpy as _np
        import pyvista as pv
    except Exception:  # noqa: BLE001
        return None
    try:
        pv.OFF_SCREEN = True
        mesh = pv.read(str(vtk_path))
        nombres = list(mesh.array_names)
        plotter = pv.Plotter(off_screen=True, window_size=(1200, 850))

        # --- Litología: volumen coloreado por K (escala log) ---
        if "K_m_d" in nombres:
            litho = mesh.copy()
            k = _np.asarray(litho.get_array("K_m_d"), dtype=float)
            with _np.errstate(divide="ignore"):
                litho["log10_K"] = _np.where(k > 0, _np.log10(k), _np.nan)
            plotter.add_mesh(litho, scalars="log10_K", cmap="turbo", opacity=0.55,
                             show_edges=True, edge_color="gray", line_width=0.2,
                             scalar_bar_args={"title": "log10 K (m/d)"}, nan_opacity=0.0)
        else:
            plotter.add_mesh(mesh, scalars="carga_m" if "carga_m" in nombres else None,
                             cmap="viridis", opacity=0.6, show_edges=True, edge_color="gray")

        # --- Napa: superficie superior coloreada por carga, semitransparente ---
        if "carga_m" in nombres:
            try:
                sup = mesh.extract_surface()
                plotter.add_mesh(sup, scalars="carga_m", cmap="Blues", opacity=0.25,
                                 show_scalar_bar=False)
            except Exception:  # noqa: BLE001
                pass

        # --- Río: celdas marcadas, en azul ---
        if "rio" in nombres:
            try:
                rio = mesh.threshold(0.5, scalars="rio")
                if rio.n_cells:
                    plotter.add_mesh(rio, color="#1f6fd6", show_scalar_bar=False,
                                     render_lines_as_tubes=True, line_width=4)
            except Exception:  # noqa: BLE001
                pass

        # --- Pozos: tubos verticales rojos que abarcan todo el espesor en cada (x,y) ---
        if "pozos" in nombres:
            try:
                pozos = mesh.threshold(0.5, scalars="pozos")
                if pozos.n_cells:
                    plotter.add_mesh(pozos, color="#c0392b", show_scalar_bar=False)
                    zmin, zmax = mesh.bounds[4], mesh.bounds[5]
                    dz = zmax - zmin
                    centros = pozos.cell_centers().points
                    vistos = set()
                    radio = max(mesh.length / 120.0, 1e-6)
                    for x, y, _z in centros:
                        clave = (round(float(x), 2), round(float(y), 2))
                        if clave in vistos:
                            continue
                        vistos.add(clave)
                        linea = pv.Line((x, y, zmin - 0.02 * dz), (x, y, zmax + 0.05 * dz))
                        plotter.add_mesh(linea.tube(radius=radio), color="#7b241c",
                                         show_scalar_bar=False)
            except Exception:  # noqa: BLE001
                pass

        plotter.add_axes()
        plotter.show_bounds(xtitle="Este", ytitle="Norte", ztitle="Cota (m, exagerada)",
                            grid="back", location="outer", ticks="outside", font_size=9)
        plotter.add_text(f"{model_name} — escena hidrogeologica 3D", font_size=11)
        plotter.camera_position = "iso"
        png = output_dir / f"{model_name}_escena_3d.png"
        plotter.screenshot(str(png))
        plotter.close()
        return png if png.exists() else None
    except Exception as exc:  # noqa: BLE001
        logger.warning("No se pudo renderizar la escena 3D enriquecida (%s).", exc)
        return None


def run(workspace: Path, model_name: str, output_dir: Path, *,
        vertical_exageration: float = 20.0) -> dict[str, Path]:
    """Exporta VTK 3D con la carga y (si se puede) un PNG 3D. Devuelve rutas."""
    workspace = Path(workspace)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    gwf = _load_gwf(workspace, model_name)
    hds = flopy.utils.HeadFile(str(workspace / f"{model_name}.hds"), precision="double")
    times = hds.get_times()
    head = hds.get_data(totim=times[-1]) if times else hds.get_data()

    out: dict[str, Path] = {}

    # --- Exportar a VTK (.vtu) ---
    from flopy.export.vtk import Vtk

    vtk = Vtk(model=gwf, vertical_exageration=vertical_exageration, binary=True, smooth=False)
    vtk.add_array(head, "carga_m")
    # Litologia y elementos del modelo como arrays coloreables en ParaView:
    # K (permeabilidad/litologia), recarga (lluvia) y marcadores de rio/pozos/borde.
    for nombre, arr in _arrays_modelo(gwf).items():
        try:
            vtk.add_array(arr, nombre)
        except Exception as exc:  # noqa: BLE001
            logger.debug("No se pudo agregar el array %s al VTK: %s", nombre, exc)
    vtk_base = output_dir / f"{model_name}_3d"
    vtk.write(str(vtk_base))
    # Vtk.write puede producir .vtu o un nombre con sufijo; localizar el archivo real.
    producidos = sorted(output_dir.glob(f"{model_name}_3d*.vt*"))
    if producidos:
        out["vtk"] = producidos[0]
        logger.info("VTK 3D escrito: %s (abrible en ParaView/PyVista)", out["vtk"].name)

    # --- Intentar PNG 3D con PyVista (off-screen) ---
    if "vtk" in out:
        try:
            import pyvista as pv

            pv.OFF_SCREEN = True
            mesh = pv.read(str(out["vtk"]))
            plotter = pv.Plotter(off_screen=True, window_size=(1100, 800))
            scalars = "carga_m" if "carga_m" in mesh.array_names else None
            plotter.add_mesh(mesh, scalars=scalars, cmap="viridis", show_edges=True,
                             edge_color="gray", line_width=0.3, scalar_bar_args={"title": "carga (m)"})
            plotter.add_axes()
            plotter.camera_position = "iso"
            png = output_dir / f"{model_name}_3d.png"
            plotter.screenshot(str(png))
            plotter.close()
            if png.exists():
                out["png"] = png
                logger.info("PNG 3D generado: %s", png.name)
        except Exception as exc:
            logger.warning("No se pudo renderizar PNG 3D (%s). El VTK queda disponible.", exc)

        # Escena enriquecida con actores diferenciados (litologia/napa/rio/pozos)
        escena = escena_hidrogeologica(out["vtk"], output_dir, model_name)
        if escena is not None:
            out["escena"] = escena
            logger.info("Escena 3D hidrogeologica generada: %s", escena.name)

    return out
