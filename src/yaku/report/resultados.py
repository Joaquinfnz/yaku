#!/usr/bin/env python3
"""Recolección de resultados reales de un proyecto, para el informe data-driven.

Lee del proyecto ya corrido (cargas, calibración, balance hídrico, parámetros,
predicción y trazabilidad) y los empaqueta en un objeto `Resultados` que el informe
(`report/pdf.py`) usa para escribir contenido real en cada sección, en vez de solo
una frase guía.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

import flopy
import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt

logger = logging.getLogger("yaku")

_INACTIVO = 1e29  # MODFLOW marca celdas secas/inactivas con |valor| ~ 1e30


@dataclass
class Resultados:
    """Bloques de resultados reales de un proyecto (lo que el informe escribe)."""

    model_name: str
    head: np.ndarray | None = None
    times: list = field(default_factory=list)
    stats_por_capa: list[dict] = field(default_factory=list)
    mapas_carga: list[Path] = field(default_factory=list)
    calibracion: dict | None = None     # {metricas: df, residuos: df|None, scatter: Path|None}
    balance: dict | None = None         # {df, discrepancia_pct, csv}
    parametros: dict | None = None      # {globales: df|None, capas: df|None}
    prediccion: dict | None = None      # {descenso, descenso_png, incertidumbre, incert_png}
    trazabilidad: dict | None = None    # contenido de inputs_metadata.json
    napa: dict | None = None            # {png, stats} profundidad del nivel freatico
    caudal_base: dict | None = None     # intercambio rio-acuifero (m3/dia)
    balance_por_capa: "pd.DataFrame | None" = None   # balance por capa/sector (m3/dia)
    seccion_vertical: Path | None = None  # corte vertical (estratos + carga)
    sensibilidad: "pd.DataFrame | None" = None  # sensibilidad OAT de parametros
    criterio_calibracion: dict | None = None  # MAE/RMSE/sesgo vs criterio SEA (5% dif. max.)
    residuos_figs: dict | None = None   # {histograma: Path, mapa: Path} de residuos de calibracion
    balance_barras: Path | None = None  # grafico de barras entrada/salida del balance
    series_tiempo: Path | None = None   # series de tiempo de carga simulada por pozo (transiente)
    mapa_conceptual: Path | None = None  # planta del modelo conceptual (dominio, rio, pozos, obs)
    malla_voronoi: Path | None = None    # planta de la malla Voronoi no estructurada (DISV)
    malla_3d: Path | None = None         # vista 3D de la malla Voronoi (bloque coloreado por carga)
    unidades_geologicas: "pd.DataFrame | None" = None  # geologia.shp: K horizontal y coef. infiltracion por unidad
    recarga: dict | None = None          # {tabla, total_mm, metodo} de la recarga aplicada
    recarga_mapa: Path | None = None     # mapa de recarga distribuida por celda (mm/ano)
    qa: "pd.DataFrame | None" = None      # chequeos automaticos de calidad del modelo (verificacion)
    indices_clima: dict | None = None     # indices clima-hidrogeologia (SPI/SPEI, flujo base, memoria)
    napa_animacion: Path | None = None    # GIF de la evolucion temporal de la napa (transiente)


def _capas(head: np.ndarray) -> list[np.ndarray]:
    arr = np.asarray(head)
    if arr.ndim == 3:                     # (nlay, nrow, ncol) estructurado
        return [arr[k] for k in range(arr.shape[0])]
    if arr.ndim == 2:                     # (nlay, ncpl) DISV
        return [arr[k] for k in range(arr.shape[0])]
    return [arr]


def _validos(lay: np.ndarray) -> np.ndarray:
    v = np.asarray(lay, dtype=float).ravel()
    return v[np.isfinite(v) & (np.abs(v) < _INACTIVO)]


def stats_por_capa(head: np.ndarray) -> list[dict]:
    """Estadísticos de carga por capa (ignora celdas secas/inactivas)."""
    stats = []
    for k, lay in enumerate(_capas(head), 1):
        v = _validos(lay)
        if v.size == 0:
            continue
        stats.append({
            "capa": k,
            "min_m": float(v.min()), "max_m": float(v.max()),
            "media_m": float(v.mean()), "desv_m": float(v.std()),
        })
    return stats


def cargar_modelgrid(resultados_dir: Path, model_name: str):
    """Carga la `modelgrid` de la simulación MF6 (offset/rotación/CRS si los tiene).

    Sirve para dibujar mapas georreferenciados en coordenadas reales. Devuelve la
    modelgrid de flopy o None si no se puede cargar.
    """
    from yaku.binaries import resolve_exe
    try:
        sim = flopy.mf6.MFSimulation.load(
            sim_ws=str(resultados_dir), exe_name=resolve_exe("mf6") or "mf6",
            verbosity_level=0, load_only=[])
        gwf = sim.get_model(model_name) or sim.get_model(list(sim.model_dict.keys())[0])
        return gwf.modelgrid
    except Exception as exc:  # noqa: BLE001
        logger.warning("No se pudo cargar la grilla para los mapas georreferenciados: %s", exc)
        return None


def vectores_flujo(resultados_dir: Path, model_name: str):
    """Caudal específico (qx, qy) por capa desde DATA-SPDIS del .cbc, para vectores de flujo.

    Devuelve (qx, qy) con forma (nlay, nrow, ncol) o None si no hay specific discharge guardado.
    """
    from yaku.binaries import resolve_exe
    try:
        from flopy.utils.postprocessing import get_specific_discharge
        resultados_dir = Path(resultados_dir)
        sim = flopy.mf6.MFSimulation.load(
            sim_ws=str(resultados_dir), exe_name=resolve_exe("mf6") or "mf6", verbosity_level=0)
        gwf = sim.get_model(model_name) or sim.get_model(list(sim.model_dict.keys())[0])
        cbc = flopy.utils.CellBudgetFile(str(resultados_dir / f"{model_name}.cbc"), precision="double")
        spdis = cbc.get_data(text="DATA-SPDIS")[-1]
        qx, qy, _qz = get_specific_discharge(spdis, gwf)
        return np.asarray(qx), np.asarray(qy)
    except Exception as exc:  # noqa: BLE001
        logger.warning("No se pudieron calcular los vectores de flujo: %s", exc)
        return None


def _paso_redondo(rango: float, divisiones: int = 8) -> float:
    """Paso 'redondo' (1/2/5·10ⁿ) para curvas de nivel o barras de escala."""
    if rango <= 0:
        return 1.0
    objetivo = rango / divisiones
    for paso in (0.5, 1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500, 1000, 2000, 5000):
        if paso >= objetivo:
            return float(paso)
    return float(paso)


def _niveles_isopiezas(data: np.ndarray):
    """Niveles 'redondos' para isopiezas (~8 contornos; la Guía SEA pide 10–20 m)."""
    v = data.compressed() if isinstance(data, np.ma.MaskedArray) else np.asarray(data, float).ravel()
    v = v[np.isfinite(v)]
    if v.size < 4 or v.max() <= v.min():
        return None
    paso = _paso_redondo(float(v.max() - v.min()))
    lo = np.floor(v.min() / paso) * paso
    hi = np.ceil(v.max() / paso) * paso
    niveles = np.arange(lo, hi + paso, paso)
    return niveles if niveles.size >= 2 else None


def _norte_y_escala(ax, grid) -> None:
    """Flecha de norte (arriba-derecha) y barra de escala en metros (abajo-izquierda)."""
    ax.annotate("N", xy=(0.95, 0.95), xytext=(0.95, 0.80), xycoords="axes fraction",
                ha="center", va="center", fontsize=11, fontweight="bold",
                arrowprops=dict(arrowstyle="-|>", color="k", lw=1.6))
    try:
        xmin, xmax, ymin, ymax = grid.extent
    except Exception:  # noqa: BLE001
        return
    ancho, alto = xmax - xmin, ymax - ymin
    if ancho <= 0:
        return
    largo = _paso_redondo(ancho, divisiones=4)
    if largo > ancho / 2.0:
        largo = _paso_redondo(ancho, divisiones=8)
    x0 = xmin + 0.06 * ancho
    y0 = ymin + 0.06 * alto
    ax.plot([x0, x0 + largo], [y0, y0], color="k", lw=3, solid_capstyle="butt", zorder=5)
    etiqueta = f"{largo / 1000:.0f} km" if largo >= 1000 else f"{largo:.0f} m"
    ax.text(x0 + largo / 2, y0 + 0.02 * alto, etiqueta, ha="center", va="bottom",
            fontsize=8, zorder=5)


def _dibujar_mapa(data, grid, png: Path, *, titulo: str, cbar_label: str,
                  cmap: str = "viridis", isopiezas: bool = False, vectores=None) -> Path:
    """Dibuja un mapa en planta. Con grilla estructurada va georreferenciado (UTM):
    isopiezas etiquetadas, flecha de norte y barra de escala. Sin grilla cae a fila/columna.
    `vectores=(qx, qy)` (2D) superpone vectores de flujo (direccion del agua subterranea).
    """
    png.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(6.5, 5.5))
    if grid is not None and getattr(grid, "grid_type", "") == "structured":
        pmv = flopy.plot.PlotMapView(modelgrid=grid, ax=ax)
        quad = pmv.plot_array(data, cmap=cmap)
        if isopiezas:
            try:
                cs = pmv.contour_array(data, levels=_niveles_isopiezas(data),
                                       colors="0.15", linewidths=0.6)
                if cs is not None and cs.levels.size:
                    ax.clabel(cs, fmt="%.0f", fontsize=7, inline=True)
            except Exception:  # noqa: BLE001
                pass
        if vectores is not None:
            try:
                qx, qy = vectores
                paso = max(1, min(grid.nrow, grid.ncol) // 18)   # ralea los vectores
                pmv.plot_vector(qx, qy, normalize=True, istep=paso, jstep=paso,
                                color="0.2", scale=35, width=0.0025, headwidth=3)
            except Exception:  # noqa: BLE001
                pass
        ax.set_xlabel("Este (m)")
        ax.set_ylabel("Norte (m)")
        ax.set_aspect("equal")
        ax.ticklabel_format(style="plain", useOffset=False)
        _norte_y_escala(ax, grid)
        fig.colorbar(quad, ax=ax, label=cbar_label, shrink=0.85)
    else:
        im = ax.imshow(data, origin="lower", cmap=cmap)
        ax.set_xlabel("columna")
        ax.set_ylabel("fila")
        fig.colorbar(im, ax=ax, label=cbar_label)
    ax.set_title(titulo)
    fig.tight_layout()
    fig.savefig(png, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return png


def mapas_carga_por_capa(head: np.ndarray, out_dir: Path, model_name: str,
                         grid=None, vectores=None) -> list[Path]:
    """Una figura de carga (isopiezas + vectores de flujo) por capa (grilla estructurada)."""
    arr = np.asarray(head)
    if arr.ndim != 3:                     # DISV (nlay, ncpl): el mapa lo da viz/plots_3d
        return []
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for k in range(arr.shape[0]):
        capa = arr[k]
        data = np.ma.masked_where(~np.isfinite(capa) | (np.abs(capa) >= _INACTIVO), capa)
        vec = None
        if vectores is not None:
            qx, qy = vectores
            if np.ndim(qx) == 3 and k < qx.shape[0]:
                vec = (qx[k], qy[k])
        p = out_dir / f"{model_name}_carga_capa{k + 1}.png"
        _dibujar_mapa(data, grid, p, titulo=f"Carga hidráulica, isopiezas y flujo — capa {k + 1}",
                      cbar_label="carga (m)", cmap="viridis", isopiezas=True, vectores=vec)
        paths.append(p)
    return paths


def profundidad_napa(head: np.ndarray, top, out_dir: Path, model_name: str,
                     *, umbral_m: float = 2.5, grid=None) -> dict | None:
    """Profundidad del nivel freatico = top - carga (capa superior).

    Indicador clave para el SEIA: cuenta las celdas con napa somera (<= umbral_m),
    asociadas a ecosistemas dependientes del agua subterranea (vegas/bofedales).
    Solo para grilla estructurada (nrow x ncol).
    """
    arr = np.asarray(head)
    if arr.ndim != 3:
        return None
    wt = np.asarray(arr[0], dtype=float)
    valido = np.isfinite(wt) & (np.abs(wt) < _INACTIVO)
    top_arr = np.broadcast_to(np.asarray(top, dtype=float), wt.shape) if np.ndim(top) else \
        np.full(wt.shape, float(top))
    depth = np.full(wt.shape, np.nan)
    depth[valido] = top_arr[valido] - wt[valido]

    out_dir.mkdir(parents=True, exist_ok=True)
    data = np.ma.masked_invalid(depth)
    png = out_dir / f"{model_name}_profundidad_napa.png"
    _dibujar_mapa(data, grid, png, titulo="Profundidad del nivel freático (m)",
                  cbar_label="profundidad (m)", cmap="viridis_r", isopiezas=False)

    d = depth[np.isfinite(depth)]
    if d.size == 0:
        return None
    stats = {
        "min_m": float(d.min()), "max_m": float(d.max()), "media_m": float(d.mean()),
        "umbral_m": umbral_m,
        "celdas_someras": int((d <= umbral_m).sum()),
        "frac_someras": float((d <= umbral_m).mean()),
    }
    return {"png": png, "stats": stats}


def leer_balance(lst_path: Path, out_csv: Path | None = None) -> dict | None:
    """Lee el balance hídrico del .lst de MODFLOW 6 (entradas/salidas por paquete)."""
    lst_path = Path(lst_path)
    if not lst_path.exists():
        return None
    try:
        mf = flopy.utils.Mf6ListBudget(str(lst_path))
        flux, _vol = mf.get_dataframes()
    except Exception as exc:  # noqa: BLE001
        logger.warning("No se pudo leer el balance del .lst (%s): %s", lst_path.name, exc)
        return None
    if flux is None or flux.empty:
        return None

    ult = flux.iloc[-1]
    comps: dict[str, dict] = {}
    discrepancia = None
    for col, val in ult.items():
        if col in ("TOTAL_IN", "TOTAL_OUT", "IN-OUT"):
            continue
        if col == "PERCENT_DISCREPANCY":
            discrepancia = float(val)
            continue
        if col.endswith("_IN"):
            comps.setdefault(col[:-3], {})["entrada_m3d"] = float(val)
        elif col.endswith("_OUT"):
            comps.setdefault(col[:-4], {})["salida_m3d"] = float(val)

    filas = []
    for comp in sorted(comps):
        ent = comps[comp].get("entrada_m3d", 0.0)
        sal = comps[comp].get("salida_m3d", 0.0)
        filas.append({"componente": comp, "entrada_m3d": ent, "salida_m3d": sal, "neto_m3d": ent - sal})
    df = pd.DataFrame(filas)
    df.loc[len(df)] = {
        "componente": "TOTAL",
        "entrada_m3d": float(ult.get("TOTAL_IN", 0.0)),
        "salida_m3d": float(ult.get("TOTAL_OUT", 0.0)),
        "neto_m3d": float(ult.get("IN-OUT", 0.0)),
    }
    if out_csv is not None:
        Path(out_csv).parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(out_csv, index=False)
    return {"df": df, "discrepancia_pct": discrepancia, "csv": Path(out_csv) if out_csv else None}


def balance_por_capa(cbc_path: Path, head: np.ndarray) -> "pd.DataFrame | None":
    """Balance por capa (sector) desde el .cbc: entrada/salida por paquete y capa.

    El SEA suele pedir el balance por sector; aqui cada capa hidrogeologica es un sector.
    Se calcula sumando los flujos de cada paquete de borde por capa (node -> capa), sin
    depender del binario zbud6.
    """
    cbc_path = Path(cbc_path)
    if not cbc_path.exists():
        return None
    arr = np.asarray(head)
    if arr.ndim == 3:
        nlay, ncpl = arr.shape[0], arr.shape[1] * arr.shape[2]
    elif arr.ndim == 2:
        nlay, ncpl = arr.shape[0], arr.shape[1]
    else:
        return None
    cbc = None
    for kwargs in ({}, {"precision": "double"}):   # default (single) y, si falla, doble precisión
        try:
            cbc = flopy.utils.CellBudgetFile(str(cbc_path), **kwargs)
            nombres = [x.strip().decode() if isinstance(x, bytes) else str(x).strip()
                       for x in cbc.get_unique_record_names()]
            break
        except Exception:  # noqa: BLE001
            cbc = None
    if cbc is None:
        logger.warning("No se pudo leer el .cbc para el balance por capa (precisión single/double).")
        return None

    filas = []
    for nombre in nombres:
        if "FLOW-JA-FACE" in nombre:   # flujo interno entre celdas, no es un borde
            continue
        try:
            data = cbc.get_data(text=nombre)[-1]
        except Exception:  # noqa: BLE001
            continue
        if not hasattr(data, "dtype") or data.dtype.names is None or "node" not in data.dtype.names:
            continue
        nodes = np.asarray(data["node"], dtype=int)
        q = np.asarray(data["q"], dtype=float)
        capa = (nodes - 1) // max(ncpl, 1)
        for L in range(nlay):
            m = capa == L
            if not m.any():
                continue
            qe = q[m]
            ent = float(qe[qe > 0].sum())
            sal = float(-qe[qe < 0].sum())
            if ent == 0 and sal == 0:
                continue
            filas.append({"componente": nombre, "capa": L + 1,
                          "entrada_m3d": ent, "salida_m3d": sal, "neto_m3d": ent - sal})
    if not filas:
        return None
    return pd.DataFrame(filas).sort_values(["capa", "componente"]).reset_index(drop=True)


def corte_vertical(resultados_dir: Path, model_name: str, out_dir: Path) -> Path | None:
    """Sección vertical del modelo (estratos + carga) con flopy PlotCrossSection.

    Carga la simulación, toma una fila central y dibuja el corte coloreado por carga
    con las capas. Solo para grilla estructurada (DIS). Devuelve el PNG o None.
    """
    from yaku.binaries import resolve_exe

    resultados_dir = Path(resultados_dir)
    try:
        sim = flopy.mf6.MFSimulation.load(sim_ws=str(resultados_dir),
                                          exe_name=resolve_exe("mf6") or "mf6", verbosity_level=0)
        gwf = sim.get_model(model_name) or sim.get_model(list(sim.model_dict.keys())[0])
        hf = flopy.utils.HeadFile(str(resultados_dir / f"{model_name}.hds"), precision="double")
        head = hf.get_data(totim=hf.get_times()[-1]) if hf.get_times() else hf.get_data()
    except Exception as exc:  # noqa: BLE001
        logger.warning("No se pudo construir la sección vertical: %s", exc)
        return None

    if getattr(gwf.modelgrid, "grid_type", "") != "structured":
        return None  # el corte por fila aplica a DIS; en DISV se usa la vista 3D

    out_dir.mkdir(parents=True, exist_ok=True)
    fila = max(0, gwf.modelgrid.nrow // 2)
    try:
        fig, ax = plt.subplots(figsize=(9, 4))
        xs = flopy.plot.PlotCrossSection(model=gwf, ax=ax, line={"row": fila})
        arr = xs.plot_array(head, head=head, cmap="viridis")
        xs.plot_grid(lw=0.3, color="0.5")
        try:
            xs.plot_surface(head[0], color="blue", lw=1.0)  # nivel freático
        except Exception:  # noqa: BLE001
            pass
        fig.colorbar(arr, ax=ax, label="carga (m)")
        ax.set_title(f"Sección vertical (fila {fila}) — estratos y carga")
        ax.set_xlabel("distancia (m)")
        ax.set_ylabel("elevación (m)")
        fig.tight_layout()
        png = out_dir / f"{model_name}_seccion_vertical.png"
        fig.savefig(png, dpi=150, bbox_inches="tight")
        plt.close(fig)
        return png
    except Exception as exc:  # noqa: BLE001
        logger.warning("Falló el dibujo de la sección vertical: %s", exc)
        plt.close("all")
        return None


def animacion_napa(resultados_dir: Path, model_name: str, grid, out_dir: Path) -> Path | None:
    """GIF de la evolución temporal del nivel freático (solo régimen transiente).

    Muestra cómo la napa sube con las lluvias y baja en las sequías a lo largo de la serie.
    Devuelve el .gif o None si el modelo no es transiente / no hay grilla estructurada.
    """
    if grid is None or getattr(grid, "grid_type", "") != "structured":
        return None
    hds = Path(resultados_dir) / f"{model_name}.hds"
    if not hds.exists():
        return None
    gif = Path(out_dir) / f"{model_name}_napa_animacion.gif"
    if gif.exists() and gif.stat().st_mtime >= hds.stat().st_mtime:
        return gif                                # cache: no regenerar si ya esta al dia
    try:
        from matplotlib.animation import FuncAnimation, PillowWriter
        hf = flopy.utils.HeadFile(str(hds), precision="double")
        tiempos = hf.get_times()
        if len(tiempos) < 3:                      # solo tiene sentido en transiente
            return None
        capas = [np.asarray(hf.get_data(totim=t))[0] for t in tiempos]
        masked = [np.ma.masked_where(~np.isfinite(c) | (np.abs(c) >= _INACTIVO), c) for c in capas]
        finitos = np.concatenate([c.compressed() for c in masked if c.count()])
        if finitos.size == 0:
            return None
        vmin, vmax = np.percentile(finitos, [2, 98])
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        fig, ax = plt.subplots(figsize=(6.5, 5.0))
        quad0 = flopy.plot.PlotMapView(modelgrid=grid, ax=ax).plot_array(
            masked[0], cmap="viridis", vmin=vmin, vmax=vmax)
        fig.colorbar(quad0, ax=ax, label="carga (m)", shrink=0.85)

        def _frame(i):
            ax.clear()
            pmv = flopy.plot.PlotMapView(modelgrid=grid, ax=ax)
            pmv.plot_array(masked[i], cmap="viridis", vmin=vmin, vmax=vmax)
            ax.set_xlabel("Este (m)"); ax.set_ylabel("Norte (m)"); ax.set_aspect("equal")
            ax.set_title(f"Nivel freático — periodo {i + 1}/{len(masked)}")

        anim = FuncAnimation(fig, _frame, frames=len(masked), blit=False)
        gif = out_dir / f"{model_name}_napa_animacion.gif"
        anim.save(str(gif), writer=PillowWriter(fps=4))
        plt.close(fig)
        return gif if gif.exists() else None
    except Exception as exc:  # noqa: BLE001
        logger.warning("No se pudo generar la animacion de la napa: %s", exc)
        plt.close("all")
        return None


def mapa_conceptual(cfg, resultados_dir: Path, model_name: str, out_dir: Path) -> Path | None:
    """Mapa de planta del modelo conceptual: unidades hidrogeológicas (K), dominio activo,
    río, pozos de bombeo y de observación. La Guía SEA 2012 lo exige en el modelo conceptual.
    """
    from yaku.binaries import resolve_exe

    resultados_dir = Path(resultados_dir)
    try:
        sim = flopy.mf6.MFSimulation.load(sim_ws=str(resultados_dir),
                                          exe_name=resolve_exe("mf6") or "mf6", verbosity_level=0)
        gwf = sim.get_model(model_name) or sim.get_model(list(sim.model_dict.keys())[0])
        grid = gwf.modelgrid
    except Exception as exc:  # noqa: BLE001
        logger.warning("No se pudo cargar el modelo para el mapa conceptual: %s", exc)
        return None
    if getattr(grid, "grid_type", "") != "structured":
        return None

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    xc = np.asarray(grid.xcellcenters)
    yc = np.asarray(grid.ycellcenters)
    fig, ax = plt.subplots(figsize=(7, 6))
    pmv = flopy.plot.PlotMapView(modelgrid=grid, ax=ax)

    # Fondo: conductividad hidráulica de la capa superior (unidades hidrogeológicas),
    # solo si K varía horizontalmente (si es uniforme, el fondo no aporta y confunde).
    try:
        k = np.asarray(gwf.npf.k.array, dtype=float)
        k0 = k[0] if k.ndim == 3 else k
        kv = k0[np.isfinite(k0) & (k0 > 0)]
        if kv.size and np.ptp(kv) > 1e-6 * float(np.median(kv)):
            quad = pmv.plot_array(np.log10(np.where(k0 > 0, k0, np.nan)), cmap="Pastel1")
            fig.colorbar(quad, ax=ax, label="log₁₀ K (m/d) — unidad hidrogeológica", shrink=0.8)
    except Exception:  # noqa: BLE001
        pass
    try:
        pmv.plot_inactive(color_noflow="0.8")
    except Exception:  # noqa: BLE001
        pass
    pmv.plot_grid(lw=0.15, color="0.85")

    # Río (paquete RIV)
    try:
        riv = gwf.get_package("riv_0") or gwf.get_package("riv")
        if riv is not None:
            spd = riv.stress_period_data.get_data(0)
            rr = np.array([c["cellid"][-2] for c in spd])
            cc = np.array([c["cellid"][-1] for c in spd])
            ax.scatter(xc[rr, cc], yc[rr, cc], c="#2c7fb8", s=14, marker="s",
                       label="Río (RIV)", zorder=4)
    except Exception:  # noqa: BLE001
        pass

    # Pozos de bombeo y observación, desde las tablas preparadas
    def _puntos(csv_name, **kw):
        p = cfg.datos_dir / csv_name
        if not p.exists():
            return
        df = pd.read_csv(p)
        if not {"row", "col"}.issubset(df.columns):
            return
        rr = df["row"].astype(int).to_numpy()
        cc = df["col"].astype(int).to_numpy()
        ax.scatter(xc[rr, cc], yc[rr, cc], zorder=5, **kw)

    _puntos("pozos.csv", c="#d7301f", marker="v", s=80, edgecolor="k", label="Pozos de bombeo")
    _puntos("observaciones_nivel.csv", c="#2171b5", marker="^", s=60, edgecolor="k",
            label="Pozos de observación")

    ax.set_xlabel("Este (m)")
    ax.set_ylabel("Norte (m)")
    ax.set_aspect("equal")
    ax.ticklabel_format(style="plain", useOffset=False)
    ax.set_title("Modelo conceptual — planta (dominio, río y red de pozos)")
    _norte_y_escala(ax, grid)
    handles, labels = ax.get_legend_handles_labels()
    if handles:
        ax.legend(loc="upper left", fontsize=8, framealpha=0.9)
    fig.tight_layout()
    png = out_dir / f"{model_name}_mapa_conceptual.png"
    fig.savefig(png, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return png


def unidades_geologicas(cfg) -> "pd.DataFrame | None":
    """Unidades geológicas en planta (K horizontal y coef. de infiltración) desde geologia.shp.

    Es la zonificación hidrogeológica horizontal del modelo conceptual; complementa la tabla de
    capas (estratificación vertical). Devuelve la tabla sin geometría o None si no hay geologia.shp.
    """
    try:
        shp = cfg.datos_dir.parent / "fuente" / "geologia.shp"
        if not shp.exists():
            return None
        import geopandas as gpd
        g = gpd.read_file(shp)
        cols = [c for c in g.columns if c.lower() != "geometry"]
        return g[cols].drop_duplicates().reset_index(drop=True)
    except Exception as exc:  # noqa: BLE001
        logger.warning("No se pudo leer geologia.shp para la tabla de unidades: %s", exc)
        return None


def mapa_recarga(cfg, grid, out_dir: Path, model_name: str) -> Path | None:
    """Mapa de la recarga distribuida por celda (mm/año), desde recarga_zonas.csv (coef_inf).

    Hace visible el reparto espacial de la recarga por unidad geológica. Devuelve None si no
    hay zonificación (recarga uniforme) o no hay grilla estructurada.
    """
    zonas = cfg.datos_dir / "recarga_zonas.csv"
    if not zonas.exists() or grid is None or getattr(grid, "grid_type", "") != "structured":
        return None
    try:
        coef = pd.read_csv(zonas, header=None).to_numpy(dtype=float)
        valido = np.isfinite(coef) & (coef > 0)
        if not valido.any():
            return None
        mult = np.where(valido, coef / float(coef[valido].mean()), np.nan)
        # Recarga media del periodo 0 (m/d): de recarga_periodos.csv o de parametros_modelo.csv
        r_md = None
        rp = cfg.datos_dir / "recarga_periodos.csv"
        if rp.exists():
            df = pd.read_csv(rp)
            col = next((c for c in df.columns if "recharge" in c.lower()), None)
            if col is not None and len(df):
                r_md = float(df[col].iloc[0])
        if r_md is None:
            pm = cfg.datos_dir / "parametros_modelo.csv"
            if pm.exists():
                d0 = {str(x.clave): x.valor for x in pd.read_csv(pm).itertuples(index=False)}
                r_md = float(d0.get("recharge", 0.0))
        if not r_md:
            return None
        recarga_mm_ano = np.ma.masked_invalid(mult * r_md * 1000.0 * 365.0)
        png = Path(out_dir) / f"{model_name}_recarga_distribuida.png"
        _dibujar_mapa(recarga_mm_ano, grid, png, titulo="Recarga distribuida (mm/año)",
                      cbar_label="recarga (mm/año)", cmap="YlGnBu", isopiezas=False)
        return png
    except Exception as exc:  # noqa: BLE001
        logger.warning("No se pudo generar el mapa de recarga distribuida: %s", exc)
        return None


def resumen_recarga(cfg) -> dict | None:
    """Resumen de la recarga aplicada (tabla por periodo, total anual y método) desde recarga_periodos.csv."""
    p = cfg.datos_dir / "recarga_periodos.csv"
    if not p.exists():
        return None
    try:
        tabla = pd.read_csv(p)
        col = next((c for c in tabla.columns if "recharge" in c.lower() or "recarga" in c.lower()), None)
        total_mm = None
        if col is not None and "dias" not in tabla.columns:
            # recarga media (m/d) -> mm/año aproximado
            total_mm = float(tabla[col].mean()) * 1000.0 * 365.0
        return {"tabla": tabla, "total_mm": total_mm}
    except Exception as exc:  # noqa: BLE001
        logger.warning("No se pudo leer recarga_periodos.csv: %s", exc)
        return None


def criterio_calibracion(residuos: "pd.DataFrame", metricas: "pd.DataFrame") -> dict | None:
    """Evalua el ajuste contra el criterio cuantitativo de la Guia SEA 2012 (3.4.2).

    Criterio de error ACEPTABLE: MAE <= 5 % de la diferencia maxima de niveles observados
    en la zona. Devuelve MAE/RMSE/sesgo, el umbral y si cumple.
    """
    if residuos is None or residuos.empty or "observado_m" not in residuos.columns:
        return None
    met = {str(r["metrica"]): float(r["valor"]) for _, r in metricas.iterrows()} if metricas is not None else {}
    obs = residuos["observado_m"].astype(float)
    dif_max = float(obs.max() - obs.min())
    umbral = 0.05 * dif_max
    mae = met.get("mae_m")
    if mae is None:
        mae = float(residuos["residual_m"].abs().mean())
    rmse = met.get("rmse_m", float((residuos["residual_m"].astype(float) ** 2).mean() ** 0.5))
    sesgo = met.get("sesgo_m", float(residuos["residual_m"].astype(float).mean()))
    return {
        "mae_m": mae, "rmse_m": rmse, "sesgo_m": sesgo,
        "dif_max_obs_m": dif_max, "umbral_aceptable_m": umbral,
        "cumple": bool(mae <= umbral) if umbral > 0 else None,
        "n_obs": int(len(residuos)),
    }


def figuras_residuos(residuos: "pd.DataFrame", out_dir: Path, model_name: str,
                     grid=None) -> dict | None:
    """Histograma de residuos (simetrico, centrado en cero) + mapa espacial de residuos.

    Outputs estadisticos exigidos por la Guia SEA 2012 (Fig. 11 y mapa de residuos): el
    histograma deberia ser simetrico y centrado en cero; el mapa muestra sesgo espacial.
    """
    if residuos is None or residuos.empty or "residual_m" not in residuos.columns:
        return None
    out_dir.mkdir(parents=True, exist_ok=True)
    r = residuos["residual_m"].astype(float).to_numpy()
    figs: dict[str, Path] = {}

    # Histograma
    fig, ax = plt.subplots(figsize=(6, 4))
    lim = float(np.abs(r).max()) or 1.0
    ax.hist(r, bins=min(20, max(5, len(r))), range=(-lim, lim), color="#3a7bd5", edgecolor="white")
    ax.axvline(0, color="0.3", lw=1.0)
    ax.axvline(float(r.mean()), color="#d54a3a", lw=1.2, ls="--", label=f"media = {r.mean():.2f} m")
    ax.set_title("Histograma de residuos (observado - simulado)")
    ax.set_xlabel("residual (m)")
    ax.set_ylabel("frecuencia")
    ax.legend(fontsize=8)
    fig.tight_layout()
    p_hist = out_dir / f"{model_name}_residuos_histograma.png"
    fig.savefig(p_hist, dpi=150, bbox_inches="tight")
    plt.close(fig)
    figs["histograma"] = p_hist

    # Mapa espacial (si hay row/col). Con grilla va en coordenadas reales (UTM).
    if {"row", "col"}.issubset(residuos.columns):
        fig, ax = plt.subplots(figsize=(6, 5))
        rows = residuos["row"].astype(int).to_numpy()
        cols = residuos["col"].astype(int).to_numpy()
        georef = False
        if grid is not None and getattr(grid, "grid_type", "") == "structured":
            try:
                xc = np.asarray(grid.xcellcenters)
                yc = np.asarray(grid.ycellcenters)
                px, py = xc[rows, cols], yc[rows, cols]
                georef = True
            except Exception:  # noqa: BLE001
                georef = False
        if georef:
            sc = ax.scatter(px, py, c=r, cmap="RdBu", vmin=-lim, vmax=lim, s=60, edgecolor="0.3")
            ax.set_xlabel("Este (m)")
            ax.set_ylabel("Norte (m)")
            ax.set_aspect("equal")
            ax.ticklabel_format(style="plain", useOffset=False)
            _norte_y_escala(ax, grid)
        else:
            sc = ax.scatter(cols, rows, c=r, cmap="RdBu", vmin=-lim, vmax=lim, s=60, edgecolor="0.3")
            ax.set_xlabel("columna")
            ax.set_ylabel("fila")
            ax.invert_yaxis()
        ax.set_title("Distribucion espacial de residuos")
        fig.colorbar(sc, ax=ax, label="residual (m)")
        fig.tight_layout()
        p_map = out_dir / f"{model_name}_residuos_mapa.png"
        fig.savefig(p_map, dpi=150, bbox_inches="tight")
        plt.close(fig)
        figs["mapa"] = p_map
    return figs


def figura_balance_barras(balance_df: "pd.DataFrame", out_dir: Path, model_name: str) -> Path | None:
    """Grafico de barras del balance: entradas (verde) y salidas (rojo) por componente.

    Presentacion exigida por la Guia SEA 2012 (Fig. 18/22), con el error de cierre visible.
    """
    if balance_df is None or balance_df.empty:
        return None
    df = balance_df[balance_df["componente"] != "TOTAL"].copy()
    if df.empty:
        return None
    out_dir.mkdir(parents=True, exist_ok=True)
    comp = df["componente"].tolist()
    x = np.arange(len(comp))
    fig, ax = plt.subplots(figsize=(max(6, len(comp) * 1.1), 4))
    ax.bar(x - 0.2, df["entrada_m3d"], width=0.4, color="#2e8b57", label="entrada")
    ax.bar(x + 0.2, df["salida_m3d"], width=0.4, color="#c0392b", label="salida")
    ax.set_xticks(x)
    ax.set_xticklabels(comp, rotation=30, ha="right", fontsize=8)
    ax.set_ylabel("caudal (m3/dia)")
    ax.set_title("Balance hidrico: entradas y salidas por componente")
    ax.legend(fontsize=8)
    fig.tight_layout()
    p = out_dir / f"{model_name}_balance_barras.png"
    fig.savefig(p, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return p


def series_tiempo_observaciones(hds_path: Path, observaciones: "pd.DataFrame",
                                out_dir: Path, model_name: str) -> Path | None:
    """Series de tiempo de carga simulada en cada pozo de observacion (regimen transiente).

    La Guia SEA 2012 (4.1.2 y Fig. 16) pide caracterizar el comportamiento temporal por pozo.
    Solo aplica a grilla estructurada con mas de un tiempo simulado.
    """
    hds_path = Path(hds_path)
    if not hds_path.exists() or observaciones is None or observaciones.empty:
        return None
    try:
        hf = flopy.utils.HeadFile(str(hds_path), precision="double")
        times = hf.get_times()
    except Exception:  # noqa: BLE001
        return None
    if not times or len(times) < 2:
        return None
    out_dir.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(7, 4))
    n = 0
    for _, o in observaciones.iterrows():
        try:
            L, row, col = int(o["layer"]) - 1, int(o["row"]), int(o["col"])
        except Exception:  # noqa: BLE001
            continue
        serie = []
        for t in times:
            h = np.asarray(hf.get_data(totim=t))
            if h.ndim != 3:
                return None
            v = float(h[L, row, col])
            serie.append(v if np.isfinite(v) and abs(v) < _INACTIVO else np.nan)
        ax.plot(times, serie, marker=".", lw=1.0, label=str(o.get("nombre", f"obs{n+1}")))
        n += 1
    if n == 0:
        plt.close(fig)
        return None
    ax.set_title("Series de tiempo de carga simulada por pozo")
    ax.set_xlabel("tiempo (dias)")
    ax.set_ylabel("carga (m)")
    if n <= 12:
        ax.legend(fontsize=7, ncol=2)
    fig.tight_layout()
    p = out_dir / f"{model_name}_series_tiempo.png"
    fig.savefig(p, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return p


def chequeos_qa(cfg, r: "Resultados") -> "pd.DataFrame | None":
    """Chequeos automaticos de calidad del modelo (verificacion estilo herramienta comercial).

    Reune indicadores de credibilidad que un revisor (SEA/ASTM) espera: cierre de balance,
    convergencia, celdas secas, rangos de carga y de conductividad plausibles. Devuelve una
    tabla chequeo/valor/criterio/estado.
    """
    filas: list[dict] = []

    def add(chequeo, valor, criterio, ok):
        filas.append({"chequeo": chequeo, "valor": valor, "criterio": criterio,
                      "estado": ("OK" if ok else "REVISAR") if ok is not None else "info"})

    # 1) Convergencia (mfsim.lst)
    mfsim = cfg.resultados_dir / "mfsim.lst"
    if mfsim.exists():
        txt = mfsim.read_text(errors="ignore")
        conv = "Normal termination" in txt
        add("Convergencia de la simulacion", "Normal termination" if conv else "NO converge",
            "terminacion normal de MODFLOW 6", conv)

    # 2) Discrepancia de balance (criterio ASTM/USGS <= 1%)
    if r.balance is not None and r.balance.get("discrepancia_pct") is not None:
        disc = float(r.balance["discrepancia_pct"])
        add("Cierre del balance hidrico", f"{disc:.3g} %", "|discrepancia| <= 1 %", abs(disc) <= 1.0)

    # 3) Carga dentro de rangos fisicos + celdas secas
    if r.head is not None:
        arr = np.asarray(r.head)
        v = arr[np.isfinite(arr) & (np.abs(arr) < _INACTIVO)]
        if v.size:
            add("Rango de carga simulada", f"{v.min():.1f} a {v.max():.1f} m",
                "sin valores extremos no fisicos", None)
        # celdas secas: carga por debajo de la base de su capa (desde capas_modelo)
        cm = cfg.datos_dir / "capas_modelo.csv"
        if cm.exists() and arr.ndim == 3:
            botm = pd.read_csv(cm).sort_values("layer")["botm_m"].astype(float).tolist()
            secas = 0
            activas = 0
            for k in range(min(arr.shape[0], len(botm))):
                capa = arr[k]
                val = np.isfinite(capa) & (np.abs(capa) < _INACTIVO)
                activas += int(val.sum())
                secas += int((capa[val] <= botm[k]).sum())
            frac = (secas / activas) if activas else 0.0
            add("Celdas secas (carga bajo la base)", f"{secas} ({100 * frac:.1f} %)",
                "baja proporcion de celdas secas", frac <= 0.10)

    # 4) Conductividad K dentro de rangos de literatura (1e-4 a 1e3 m/d)
    if r.parametros and r.parametros.get("capas") is not None:
        cap = r.parametros["capas"]
        ks = []
        for c in ("kx_m_d", "kz_m_d"):
            if c in cap.columns:
                ks += [float(x) for x in cap[c] if pd.notna(x)]
        if ks:
            dentro = all(1e-4 <= k <= 1e3 for k in ks)
            add("Conductividad K en rango de literatura", f"{min(ks):.3g} a {max(ks):.3g} m/d",
                "1e-4 a 1e3 m/d (arcilla a grava)", dentro)

    # 5) Criterio de calibracion (si hay)
    if r.criterio_calibracion and r.criterio_calibracion.get("cumple") is not None:
        c = r.criterio_calibracion
        add("Calibracion (criterio SEA)", f"MAE {c['mae_m']:.2f} m vs umbral {c['umbral_aceptable_m']:.2f} m",
            "MAE <= 5 % de la dif. maxima observada", bool(c["cumple"]))

    if not filas:
        return None
    return pd.DataFrame(filas)


def recolectar_resultados(cfg, figuras_dir: Path | None = None) -> Resultados:
    """Recolecta todos los bloques de resultados disponibles del proyecto `cfg`."""
    res_dir = cfg.resultados_dir
    model = cfg.model_name
    figuras_dir = Path(figuras_dir) if figuras_dir else (res_dir / "informe_figuras")
    figuras_dir.mkdir(parents=True, exist_ok=True)

    r = Resultados(model_name=model)
    grid = None  # modelgrid para mapas georreferenciados (se carga si hay simulación)

    # --- Cargas por capa ---
    hds = res_dir / f"{model}.hds"
    if hds.exists():
        try:
            hf = flopy.utils.HeadFile(str(hds), precision="double")
            times = hf.get_times()
            r.head = hf.get_data(totim=times[-1]) if times else hf.get_data()
            r.times = list(times)
            r.stats_por_capa = stats_por_capa(r.head)
            grid = cargar_modelgrid(res_dir, model)   # coordenadas reales para los mapas (de aquí en más)
            vectores = vectores_flujo(res_dir, model)  # qx, qy para los vectores de flujo
            r.mapas_carga = mapas_carga_por_capa(r.head, figuras_dir, model, grid=grid, vectores=vectores)
            # Profundidad de napa: top desde top_dem_grid.csv o el escalar de parametros
            top_grid = cfg.datos_dir / "top_dem_grid.csv"
            top_val = None
            if top_grid.exists():
                top_val = pd.read_csv(top_grid, header=None).to_numpy()
            else:
                pm0 = cfg.datos_dir / "parametros_modelo.csv"
                if pm0.exists():
                    d0 = {str(x.clave): x.valor for x in pd.read_csv(pm0).itertuples(index=False)}
                    if "top" in d0:
                        top_val = float(d0["top"])
            if top_val is not None:
                r.napa = profundidad_napa(r.head, top_val, figuras_dir, model, grid=grid)
        except Exception as exc:  # noqa: BLE001
            logger.warning("No se pudo leer %s: %s", hds.name, exc)

    # --- Calibración ---
    cal = res_dir / "calibracion"
    met = cal / "metricas_ajuste.csv"
    if met.exists():
        resi = cal / "residuales_observaciones.csv"
        scatter = cal / "grafico_observado_vs_simulado.png"
        metricas_df = pd.read_csv(met)
        residuos_df = pd.read_csv(resi) if resi.exists() else None
        r.calibracion = {
            "metricas": metricas_df,
            "residuos": residuos_df,
            "scatter": scatter if scatter.exists() else None,
        }
        # Criterio SEA (MAE <= 5% dif. max.) + histograma/mapa de residuos
        r.criterio_calibracion = criterio_calibracion(residuos_df, metricas_df)
        r.residuos_figs = figuras_residuos(residuos_df, figuras_dir, model, grid=grid)

    # --- Balance hídrico ---
    r.balance = leer_balance(res_dir / f"{model}.lst", figuras_dir / "balance_hidrico.csv")
    if r.balance is not None:
        r.balance_barras = figura_balance_barras(r.balance["df"], figuras_dir, model)

    # --- Caudal base (intercambio río-acuífero) desde el balance ---
    if r.balance is not None:
        riv = r.balance["df"][r.balance["df"]["componente"] == "RIV"]
        if not riv.empty:
            ent = float(riv["entrada_m3d"].iloc[0])   # río -> acuífero
            sal = float(riv["salida_m3d"].iloc[0])     # acuífero -> río (caudal base)
            r.caudal_base = {"rio_a_acuifero_m3d": ent, "acuifero_a_rio_m3d": sal, "neto_m3d": ent - sal}

    # --- Balance por capa / sector (desde el .cbc) ---
    if r.head is not None:
        r.balance_por_capa = balance_por_capa(res_dir / f"{model}.cbc", r.head)

    # --- Mapa de planta del modelo conceptual (dominio, río, pozos, observaciones) ---
    if hds.exists():
        r.mapa_conceptual = mapa_conceptual(cfg, res_dir, model, figuras_dir)
        r.recarga_mapa = mapa_recarga(cfg, grid, figuras_dir, model)
        r.napa_animacion = animacion_napa(res_dir, model, grid, figuras_dir)

    # --- Malla Voronoi no estructurada (DISV), si se corrió 'mfw mesh --run' ---
    malla = res_dir / "malla"
    plano_malla = malla / "malla_voronoi.png"
    vista3d_malla = malla / "vista_3d" / "voronoi_3d.png"
    if plano_malla.exists():
        r.malla_voronoi = plano_malla
    if vista3d_malla.exists():
        r.malla_3d = vista3d_malla

    # --- Sección vertical (estratos + carga) ---
    if r.head is not None and np.asarray(r.head).ndim == 3:
        r.seccion_vertical = corte_vertical(res_dir, model, figuras_dir)

    # --- Series de tiempo por pozo de observación (regimen transiente) ---
    obs_csv = cfg.datos_dir / "observaciones_nivel.csv"
    if hds.exists() and obs_csv.exists() and len(r.times) > 1:
        try:
            r.series_tiempo = series_tiempo_observaciones(hds, pd.read_csv(obs_csv), figuras_dir, model)
        except Exception as exc:  # noqa: BLE001
            logger.warning("No se pudieron generar las series de tiempo: %s", exc)

    # --- Sensibilidad (si se corrió 'mfw sensibilidad') ---
    sens = res_dir / "sensibilidad" / "sensibilidad.csv"
    if sens.exists():
        r.sensibilidad = pd.read_csv(sens)

    # --- Parámetros del modelo ---
    pm = cfg.datos_dir / "parametros_modelo.csv"
    cm = cfg.datos_dir / "capas_modelo.csv"
    if pm.exists() or cm.exists():
        r.parametros = {
            "globales": pd.read_csv(pm) if pm.exists() else None,
            "capas": pd.read_csv(cm) if cm.exists() else None,
        }

    # --- Unidades geológicas (K horizontal + coef. infiltración) y recarga aplicada ---
    r.unidades_geologicas = unidades_geologicas(cfg)
    r.recarga = resumen_recarga(cfg)

    # --- Predicción / incertidumbre ---
    pred = res_dir / "prediccion"
    desc = pred / "descenso_resumen.csv"
    incert = pred / "incertidumbre_resumen.csv"
    if desc.exists() or incert.exists():
        def _png(name):
            p = pred / name
            return p if p.exists() else None
        r.prediccion = {
            "descenso": pd.read_csv(desc) if desc.exists() else None,
            "descenso_png": _png("descenso_escenario.png"),
            "incertidumbre": pd.read_csv(incert) if incert.exists() else None,
            "incert_png": _png("incertidumbre_montecarlo.png"),
        }

    # --- Trazabilidad ---
    meta = res_dir / "inputs_metadata.json"
    if meta.exists():
        try:
            r.trazabilidad = json.loads(meta.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            pass

    # --- Chequeos de calidad (verificacion del modelo) ---
    r.qa = chequeos_qa(cfg, r)

    # --- Índices clima-hidrogeología (si hay clima.csv) ---
    try:
        from yaku.report.indices_clima import calcular_indices
        r.indices_clima = calcular_indices(cfg)
    except Exception as exc:  # noqa: BLE001
        logger.warning("No se pudieron calcular los indices clima-hidrogeologia: %s", exc)

    return r
