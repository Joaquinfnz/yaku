#!/usr/bin/env python3
"""Malla Voronoi / grilla no estructurada (DISV) para MODFLOW 6.

Genera una grilla Voronoi desde el dominio (shapefile) con refinamiento local
alrededor de pozos y rios, al estilo de gidahatari/mf6Voronoi. Usa las utilidades
nativas de FloPy (Triangle + VoronoiGrid) y el binario `triangle` (lo instala
get-modflow). Exporta la malla a shapefile + PNG y los gridprops DISV para el modelo.
"""

from __future__ import annotations

import logging
import pickle
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from yaku.binaries import resolve_exe
from yaku.gis.preprocess import find_vector

logger = logging.getLogger("yaku")


def _domain_coords(domain_path: Path) -> list[tuple[float, float]]:
    import geopandas as gpd

    gdf = gpd.read_file(domain_path)
    geom = gdf.geometry.union_all()
    poly = max(geom.geoms, key=lambda g: g.area) if geom.geom_type == "MultiPolygon" else geom
    coords = list(poly.exterior.coords)
    if coords[0] == coords[-1]:
        coords = coords[:-1]
    return [(float(x), float(y)) for x, y in coords]


def _refine_points(gis_dir: Path) -> list[tuple[float, float, float]]:
    """Puntos de refinamiento (x, y, area_max) desde pozos y rio."""
    import geopandas as gpd

    pts: list[tuple[float, float, float]] = []
    pozos = find_vector(gis_dir, "pozos")
    if pozos is not None:
        for geom in gpd.read_file(pozos).geometry:
            pts.append((float(geom.x), float(geom.y), 0.0))  # area se fija luego
    return pts


def build_voronoi(domain_path: Path, gis_dir: Path, output_dir: Path, *,
                  cell_size: float = 200.0, refine_factor: float = 6.0) -> dict:
    """Construye la malla Voronoi DISV. Devuelve dict con rutas y gridprops.

    cell_size: tamano objetivo de celda (m) en zona gruesa.
    refine_factor: cuanto mas fina la malla cerca de pozos (area / factor^2).
    """
    tri_exe = resolve_exe("triangle")
    if tri_exe is None:
        raise RuntimeError("Binario 'triangle' no encontrado. Instala con: get-modflow :flopy")

    from flopy.utils.triangle import Triangle
    from flopy.utils.voronoi import VoronoiGrid

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    domain = _domain_coords(Path(domain_path))
    base_area = cell_size ** 2 / 2.0  # area maxima de triangulo ~ celda

    tri = Triangle(angle=30, model_ws=str(output_dir), exe_name=tri_exe, maximum_area=base_area)
    tri.add_polygon(domain)

    # Refinamiento local alrededor de pozos (poligono buffer + region con area menor)
    refine_pts = _refine_points(Path(gis_dir))
    fine_area = base_area / (refine_factor ** 2)
    n_refine = 0
    for (x, y, _) in refine_pts:
        r = cell_size  # radio del buffer de refinamiento
        ring = [(x + r * np.cos(t), y + r * np.sin(t)) for t in np.linspace(0, 2 * np.pi, 16, endpoint=False)]
        try:
            tri.add_polygon(ring)
            tri.add_region((x, y), 0, maximum_area=fine_area)
            n_refine += 1
        except Exception as exc:  # si el buffer cae fuera o se solapa, se omite
            logger.debug("refinamiento omitido en (%.1f,%.1f): %s", x, y, exc)

    tri.build(verbose=False)
    vor = VoronoiGrid(tri)
    gridprops = vor.get_disv_gridprops()
    ncpl = gridprops["ncpl"]
    logger.info("Malla Voronoi: %d celdas (ncpl) — %d zonas refinadas", ncpl, n_refine)

    out: dict = {"ncpl": ncpl, "gridprops": gridprops}

    # Guardar gridprops para el modelo
    out["gridprops_file"] = output_dir / "disv_gridprops.pkl"
    with open(out["gridprops_file"], "wb") as fh:
        pickle.dump(gridprops, fh)

    # Figura de la malla
    fig, ax = plt.subplots(figsize=(8, 8))
    vor.plot(ax=ax, facecolor="none", edgecolor="0.4", lw=0.3)
    for (x, y, _) in refine_pts:
        ax.plot(x, y, "ro", ms=5)
    ax.set_title(f"Malla Voronoi DISV — {ncpl} celdas")
    ax.set_aspect("equal")
    fig.tight_layout()
    out["figura"] = output_dir / "malla_voronoi.png"
    fig.savefig(out["figura"], dpi=200, bbox_inches="tight")
    plt.close(fig)

    # Exportar celdas a shapefile
    try:
        import geopandas as gpd
        from shapely.geometry import Polygon

        verts = {iv: (x, y) for iv, x, y in gridprops["vertices"]}
        polys = []
        for cell in gridprops["cell2d"]:
            ivs = cell[4:]
            polys.append(Polygon([verts[iv] for iv in ivs]))
        gdf = gpd.GeoDataFrame({"cellid": list(range(ncpl))}, geometry=polys)
        out["shapefile"] = output_dir / "malla_voronoi.shp"
        gdf.to_file(out["shapefile"])
    except Exception as exc:
        logger.warning("No se pudo exportar shapefile de la malla (%s).", exc)

    return out


def sample_dem_centroids(dem_path: Path, gridprops: dict) -> np.ndarray:
    """Muestrea el DEM en el centroide de cada celda Voronoi -> array (ncpl)."""
    import rasterio

    cell2d = gridprops["cell2d"]
    xy = [(float(c[1]), float(c[2])) for c in cell2d]  # c = [icpl, xc, yc, nv, *iverts]
    with rasterio.open(dem_path) as src:
        nodata = src.nodata
        vals = np.array([v[0] for v in src.sample(xy)], dtype=float)
    if nodata is not None:
        vals[vals == nodata] = np.nan
    if np.isnan(vals).any():
        vals[np.isnan(vals)] = np.nanmean(vals) if np.isfinite(vals).any() else 0.0
    return vals


def zonas_geologicas(geologia_path: Path, gridprops: dict, *,
                     campo_k: str = "K_md", campo_inf: str = "coef_inf") -> dict:
    """Asigna K y coef. de infiltracion por celda segun la unidad geologica.

    Devuelve {'k': array(ncpl)|None, 'coef_inf': array(ncpl)|None}. Si el shapefile no
    trae los campos, asigna valores plausibles por unidad (documentados) y rellena los
    huecos con la mediana.
    """
    import geopandas as gpd
    from shapely.geometry import Point

    gdf = gpd.read_file(geologia_path).reset_index(drop=True)
    cell2d = gridprops["cell2d"]
    pts = gpd.GeoDataFrame(geometry=[Point(c[1], c[2]) for c in cell2d], crs=gdf.crs)
    joined = gpd.sjoin(pts, gdf, how="left", predicate="within")
    joined = joined[~joined.index.duplicated(keep="first")].sort_index()

    # K por unidad: del campo si existe; si no, valor plausible por indice de unidad.
    k = np.full(len(cell2d), np.nan)
    inf = np.full(len(cell2d), np.nan)
    if campo_k in joined.columns:
        k = joined[campo_k].to_numpy(dtype=float)
    elif "index_right" in joined.columns:
        plausibles = [1.0, 0.1, 5.0, 0.01]  # m/dia por unidad (relleno/roca/...)
        logger.warning("geologia.shp no trae el campo '%s'; asigno K plausible por unidad "
                       "(%s m/dia por indice). Agrega '%s' al shapefile para K trazable.",
                       campo_k, plausibles, campo_k)
        k = joined["index_right"].map(
            lambda i: plausibles[int(i) % len(plausibles)] if np.isfinite(i) else np.nan).to_numpy(dtype=float)
    if campo_inf in joined.columns:
        inf = joined[campo_inf].to_numpy(dtype=float)

    def _rellenar(a):
        if not np.isfinite(a).any():
            return None
        a = a.copy()
        a[~np.isfinite(a)] = np.nanmedian(a)
        return a

    return {"k": _rellenar(k), "coef_inf": _rellenar(inf)}


def _centroides(gridprops: dict) -> np.ndarray:
    return np.array([(float(c[1]), float(c[2])) for c in gridprops["cell2d"]])


def _celdas_de_pozos(pozos_path: Path, gridprops: dict) -> list[int]:
    """Indice de celda Voronoi (icpl) mas cercano a cada pozo."""
    import geopandas as gpd

    cents = _centroides(gridprops)
    icpls: list[int] = []
    for geom in gpd.read_file(pozos_path).geometry:
        d = (cents[:, 0] - geom.x) ** 2 + (cents[:, 1] - geom.y) ** 2
        icpls.append(int(d.argmin()))
    return sorted(set(icpls))


def _celdas_de_rio(rio_path: Path, gridprops: dict) -> list[int]:
    """Celdas Voronoi que cruza el rio (muestreando la linea)."""
    import geopandas as gpd

    cents = _centroides(gridprops)
    icpls: set[int] = set()
    geom = gpd.read_file(rio_path).geometry.union_all()
    lineas = list(geom.geoms) if geom.geom_type == "MultiLineString" else [geom]
    for ln in lineas:
        n = max(2, int(ln.length / 100))  # un punto cada ~100 m
        for i in range(n + 1):
            p = ln.interpolate(i / n, normalized=True)
            d = (cents[:, 0] - p.x) ** 2 + (cents[:, 1] - p.y) ** 2
            icpls.add(int(d.argmin()))
    return sorted(icpls)


def build_disv_model(gridprops: dict, output_dir: Path, *, dem_path: Path | None = None,
                     capas: list[dict] | None = None, recharge: float = 5e-4,
                     k_por_celda: np.ndarray | None = None,
                     recarga_por_celda: np.ndarray | None = None,
                     pozos_path: Path | None = None, rio_path: Path | None = None,
                     model_name: str = "voronoi") -> dict:
    """Modelo MODFLOW 6 DISV **multicapa** con estratos drapeados bajo el DEM.

    - `top` (ncpl) = DEM en los centroides (si hay dem_path); si no, escalar.
    - `capas`: lista [{espesor, k}] por estrato (de capas_modelo.csv). botm por capa se
      obtiene restando el espesor acumulado al top, con guarda de espesor minimo.
    - K por capa: `k_por_celda` (zonas geologicas) si viene; si no, el k de cada capa.
    - RCHA en la capa superior (por celda si `recarga_por_celda`, si no escalar).
    - CHD en las celdas de borde (extremos en x) con carga = su top (napa drapeada).
    Devuelve {png, hds, nlay, ncpl}.
    """
    import flopy

    from yaku.binaries import ensure_flopy_bin_on_path

    ensure_flopy_bin_on_path()
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    ncpl = gridprops["ncpl"]

    capas = capas or [{"espesor": 50.0, "k": 8.0}]
    nlay = len(capas)

    # --- Top drapeado (DEM) ---
    if dem_path is not None and Path(dem_path).exists():
        top = sample_dem_centroids(Path(dem_path), gridprops)
    else:
        top = np.full(ncpl, float(capas[0].get("top_m", 60.0)))

    # --- Botm por capa, drapeado, con espesor minimo ---
    min_thick = 1.0
    botm = np.zeros((nlay, ncpl), dtype=float)
    acum = np.zeros(ncpl)
    for L, capa in enumerate(capas):
        esp = max(float(capa.get("espesor", 50.0)), min_thick)
        acum = acum + esp
        botm[L] = top - acum

    # --- K por capa (zonas geologicas o escalar de la capa), forma (nlay, ncpl) ---
    k_arrays = np.zeros((nlay, ncpl), dtype=float)
    for L, capa in enumerate(capas):
        if k_por_celda is not None:
            k_arrays[L] = np.asarray(k_por_celda, dtype=float)
        else:
            k_arrays[L] = float(capa.get("k", 8.0))

    # --- Recarga (por celda o escalar) ---
    rcha = np.asarray(recarga_por_celda, dtype=float) if recarga_por_celda is not None \
        else np.full(ncpl, float(recharge))

    # --- Bordes (extremos en x) con carga = top del DEM ---
    xc = np.array([c[1] for c in gridprops["cell2d"]])
    tol = (xc.max() - xc.min()) * 0.03
    borde = np.where((xc <= xc.min() + tol) | (xc >= xc.max() - tol))[0]
    chd = [[(0, int(c)), float(top[c])] for c in borde]

    sim = flopy.mf6.MFSimulation(sim_name=model_name, sim_ws=str(output_dir),
                                 exe_name=resolve_exe("mf6") or "mf6")
    flopy.mf6.ModflowTdis(sim, nper=1, perioddata=[(1.0, 1, 1.0)], time_units="DAYS")
    # Newton-Raphson: maneja la no linealidad de acuifero libre bajo topografia
    # empinada (estratos drapeados), que con formulacion estandar no converge.
    gwf = flopy.mf6.ModflowGwf(sim, modelname=model_name, save_flows=True,
                               newtonoptions="NEWTON UNDER_RELAXATION")
    flopy.mf6.ModflowGwfdisv(gwf, nlay=nlay, top=top, botm=botm, length_units="METERS",
                             **{k_: gridprops[k_] for k_ in ("ncpl", "nvert", "vertices", "cell2d")})
    flopy.mf6.ModflowGwfic(gwf, strt=np.tile(top, (nlay, 1)))
    flopy.mf6.ModflowGwfnpf(gwf, icelltype=1, k=k_arrays, save_specific_discharge=True)
    flopy.mf6.ModflowGwfchd(gwf, stress_period_data=chd)
    flopy.mf6.ModflowGwfrcha(gwf, recharge=rcha)

    # Pozos (capa profunda) y rio (capa superior), mapeados a celdas Voronoi -> visibles en 3D
    if pozos_path is not None and Path(pozos_path).exists():
        try:
            wel = [[(nlay - 1, c), -50.0] for c in _celdas_de_pozos(Path(pozos_path), gridprops)]
            if wel:
                flopy.mf6.ModflowGwfwel(gwf, stress_period_data=wel)
                logger.info("Pozos en la malla: %d celdas WEL", len(wel))
        except Exception as exc:  # noqa: BLE001
            logger.warning("No se pudieron mapear pozos a la malla: %s", exc)
    if rio_path is not None and Path(rio_path).exists():
        try:
            riv = [[(0, c), float(top[c]) - 1.0, 100.0, float(top[c]) - 3.0]
                   for c in _celdas_de_rio(Path(rio_path), gridprops)]
            if riv:
                flopy.mf6.ModflowGwfriv(gwf, stress_period_data=riv)
                logger.info("Rio en la malla: %d celdas RIV", len(riv))
        except Exception as exc:  # noqa: BLE001
            logger.warning("No se pudo mapear el rio a la malla: %s", exc)

    flopy.mf6.ModflowGwfoc(gwf, head_filerecord=f"{model_name}.hds", saverecord=[("HEAD", "ALL")])
    # Solver robusto para Newton: complexity COMPLEX trae la under-relaxation
    # apropiada; dejamos iteraciones holgadas y un dvclose acorde a un modelo regional.
    flopy.mf6.ModflowIms(
        sim, complexity="COMPLEX", linear_acceleration="BICGSTAB",
        outer_maximum=500, inner_maximum=200, outer_dvclose=1e-2,
    )
    sim.write_simulation(silent=True)
    ok, _ = sim.run_simulation(silent=True)
    if not ok:
        # No fatal: el modelo regional de demo puede requerir mas afinamiento del solver.
        # Igual dejamos lo que MODFLOW alcanzo a escribir y avisamos.
        logger.warning("El DISV multicapa no convergio del todo; se usa la ultima solucion escrita.")

    hds_path = output_dir / f"{model_name}.hds"
    if not hds_path.exists():
        raise SystemExit("El modelo DISV multicapa no produjo cargas (.hds).")
    head = flopy.utils.HeadFile(str(hds_path), precision="double").get_data()
    fig, ax = plt.subplots(figsize=(8, 8))
    pmv = flopy.plot.PlotMapView(model=gwf, ax=ax, layer=0)
    arr = pmv.plot_array(head[0].ravel(), cmap="viridis")
    pmv.plot_grid(lw=0.2, color="0.6")
    fig.colorbar(arr, ax=ax, label="carga (m)")
    disclaimer = "" if ok else "  [NO CONVERGIO - solucion preliminar]"
    ax.set_title(f"DISV multicapa drapeado ({nlay} capas, {ncpl} celdas) — capa 1{disclaimer}")
    ax.set_aspect("equal")
    fig.tight_layout()
    png = output_dir / "voronoi_cargas.png"
    fig.savefig(png, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return {"png": png, "hds": output_dir / f"{model_name}.hds", "nlay": nlay, "ncpl": ncpl}


def run_disv_flow(gridprops: dict, output_dir: Path, *, top: float = 60.0, botm: float = 0.0,
                  k: float = 8.0, h_left: float = 60.0, h_right: float = 45.0,
                  model_name: str = "voronoi") -> Path:
    """Construye y corre un modelo MODFLOW 6 DISV sobre la malla (verificacion).

    Asigna carga constante en las celdas del borde izquierdo y derecho (por x) y
    resuelve el flujo. Devuelve el PNG de cargas. Prueba que la malla es valida.
    """
    import flopy

    from yaku.binaries import ensure_flopy_bin_on_path

    ensure_flopy_bin_on_path()
    output_dir = Path(output_dir)
    ncpl = gridprops["ncpl"]
    xc = np.array([c[1] for c in gridprops["cell2d"]])
    xmin, xmax = xc.min(), xc.max()
    tol = (xmax - xmin) * 0.03
    left = np.where(xc <= xmin + tol)[0]
    right = np.where(xc >= xmax - tol)[0]

    sim = flopy.mf6.MFSimulation(sim_name=model_name, sim_ws=str(output_dir),
                                 exe_name=resolve_exe("mf6") or "mf6")
    flopy.mf6.ModflowTdis(sim, nper=1, perioddata=[(1.0, 1, 1.0)], time_units="DAYS")
    gwf = flopy.mf6.ModflowGwf(sim, modelname=model_name, save_flows=True)
    flopy.mf6.ModflowGwfdisv(gwf, nlay=1, top=top, botm=[botm], length_units="METERS",
                             **{k_: gridprops[k_] for k_ in ("ncpl", "nvert", "vertices", "cell2d")})
    flopy.mf6.ModflowGwfic(gwf, strt=h_left)
    # Confinado (icelltype=0): la verificacion de la malla evita celdas secas en
    # dominios grandes e irregulares y converge de forma robusta.
    flopy.mf6.ModflowGwfnpf(gwf, icelltype=0, k=k, save_specific_discharge=True)
    chd = [[(0, c), h_left] for c in left] + [[(0, c), h_right] for c in right]
    flopy.mf6.ModflowGwfchd(gwf, stress_period_data=chd)
    flopy.mf6.ModflowGwfoc(gwf, head_filerecord=f"{model_name}.hds",
                           saverecord=[("HEAD", "ALL")])
    flopy.mf6.ModflowIms(sim, complexity="COMPLEX", linear_acceleration="BICGSTAB")
    sim.write_simulation(silent=True)
    ok, _ = sim.run_simulation(silent=True)
    if not ok:
        raise SystemExit("El modelo DISV (Voronoi) no convergio.")

    head = flopy.utils.HeadFile(str(output_dir / f"{model_name}.hds"), precision="double").get_data()
    fig, ax = plt.subplots(figsize=(8, 8))
    pmv = flopy.plot.PlotMapView(model=gwf, ax=ax)
    arr = pmv.plot_array(head[0].ravel(), cmap="viridis")
    pmv.plot_grid(lw=0.2, color="0.6")
    fig.colorbar(arr, ax=ax, label="carga (m)")
    ax.set_title(f"Flujo en malla Voronoi DISV ({ncpl} celdas)")
    ax.set_aspect("equal")
    fig.tight_layout()
    png = output_dir / "voronoi_cargas.png"
    fig.savefig(png, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return png
