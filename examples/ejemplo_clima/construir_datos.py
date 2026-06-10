#!/usr/bin/env python3
"""Genera los datos del ejemplo INTEGRADO clima-hidrogeologia (ejemplo_clima).

Cuenca de valle semiárido (estilo Chile central) con:
  - geometría suave que drapea al DEM y converge en régimen TRANSIENTE,
  - geología en 3 unidades (K horizontal + coef. de infiltración),
  - serie climática DIARIA de 3 años (con un año seco para que se vea la sequía en el SPI),
  - caudal del río MEDIDO diario (caudal_rio.csv) para validar la recarga por flujo base.

Demuestra todo el flujo: clima -> recarga (balance diario) -> modelo transiente -> índices
clima-hidrogeología (SPI/SPEI, aridez, recarga, flujo base, memoria napa-clima).

Ejecutar una vez:  conda run -n modflow-workflow python examples/ejemplo_clima/construir_datos.py
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

FUENTE = Path(__file__).resolve().parent / "datos" / "fuente"
CRS = "EPSG:32719"                       # UTM 19S, metros
X0, Y0 = 330_000.0, 6_300_000.0
NROW, NCOL = 26, 38
CELL = 100.0
WIDTH, HEIGHT = NCOL * CELL, NROW * CELL
ANIOS = 3


def _dem() -> np.ndarray:
    """Valle transversal de relieve suave (eje E-O): baja ~14 m de O a E, laderas N-S."""
    xs = np.linspace(0, WIDTH, NCOL)
    ys = np.linspace(0, HEIGHT, NROW)
    xx, yy = np.meshgrid(xs, ys)
    plano = 820 - (xx / WIDTH) * 14
    dist = np.abs(yy - HEIGHT / 2) / (HEIGHT / 2)
    return (plano + 35 * dist ** 2).astype("float32")


def _clima_diario():
    """Serie diaria de precip y ET0 (mm), 3 años; clima mediterráneo semiárido.

    Inviernos lluviosos (may-ago), veranos secos; el 2.º año es seco (sequía) para que el
    SPI lo capture. Devuelve (fechas, precip_mm, et0_mm).
    """
    import pandas as pd
    rng = np.random.default_rng(2026)
    fechas = pd.date_range("2021-01-01", periods=ANIOS * 365, freq="D")
    doy = fechas.dayofyear.to_numpy()
    anio = (fechas.year.to_numpy() - 2021)
    # probabilidad y magnitud de lluvia, concentrada en invierno austral (jun-ago ~ doy 150-240)
    estacion = np.exp(-((doy - 195) ** 2) / (2 * 55 ** 2))      # campana en invierno
    factor_anual = np.where(anio == 1, 0.45, 1.0)               # año 2 = seco
    p_lluvia = 0.55 * estacion * factor_anual
    llueve = rng.random(len(doy)) < p_lluvia
    precip = np.where(llueve, rng.gamma(2.0, 9.0, len(doy)) * (0.3 + estacion), 0.0)
    precip = np.round(precip * factor_anual, 1)
    # ET0: alta en verano (doy ~ 0/365), baja en invierno
    et0 = np.round(3.2 + 2.6 * np.cos(2 * np.pi * (doy - 15) / 365), 2).clip(0.2, None)
    return fechas, precip, et0


def _caudal_rio(fechas, precip, et0):
    """Caudal del río medido (m³/día): flujo base lento + crecidas rápidas por lluvia.

    El flujo base sigue un reservorio alimentado por la recarga (memoria), y las crecidas son
    proporcionales a la lluvia del día con recesión rápida. Permite separar el flujo base y
    validar la recarga del modelo.
    """
    from yaku.hidrologia import balance_suelo_diario
    rec = balance_suelo_diario(precip, et0, cc_mm=70, coef_escorrentia=0.15, k_percolacion=0.04)
    # reservorio de flujo base (descarga lenta de la recarga)
    base = np.zeros(len(precip))
    s = 1500.0
    for i in range(len(precip)):
        s += rec[i] * 90.0                     # recarga -> almacenamiento (factor de area/escala)
        q = 0.02 * s                            # descarga proporcional al almacenamiento
        base[i] = q
        s -= q
    # crecida rápida (escorrentía directa) con recesión
    quick = np.zeros(len(precip))
    q = 0.0
    for i in range(len(precip)):
        q = 0.5 * q + precip[i] * 35.0
        quick[i] = q
    caudal = np.round(base + quick + 200.0, 1)   # + caudal de base mínimo
    return caudal


def construir() -> None:
    import geopandas as gpd
    import pandas as pd
    import rasterio
    from rasterio.transform import from_origin
    from shapely.geometry import LineString, Point, box

    FUENTE.mkdir(parents=True, exist_ok=True)
    dem = _dem()

    transform = from_origin(X0, Y0 + HEIGHT, CELL, CELL)
    with rasterio.open(FUENTE / "dem.tif", "w", driver="GTiff", height=NROW, width=NCOL,
                       count=1, dtype="float32", crs=CRS, transform=transform, nodata=-9999.0) as dst:
        dst.write(np.flipud(dem), 1)

    minx, maxx = X0 + 100, X0 + WIDTH - 100
    miny, maxy = Y0 + HEIGHT * 0.20, Y0 + HEIGHT * 0.80
    gpd.GeoDataFrame({"nombre": ["dominio"]}, geometry=[box(minx, miny, maxx, maxy)],
                     crs=CRS).to_file(FUENTE / "dominio.shp")

    yc = Y0 + HEIGHT / 2
    rio = LineString([(X0 + 150, yc + 30), (X0 + WIDTH / 2, yc), (X0 + WIDTH - 150, yc - 25)])
    gpd.GeoDataFrame({"nombre": ["estero"]}, geometry=[rio], crs=CRS).to_file(FUENTE / "rio.shp")

    pozos = [("Pozo_riego_1", X0 + 1100, yc + 300), ("Pozo_riego_2", X0 + 2500, yc - 250),
             ("Pozo_APR", X0 + 3200, yc + 120)]
    gpd.GeoDataFrame({"nombre": [p[0] for p in pozos]},
                     geometry=[Point(p[1], p[2]) for p in pozos], crs=CRS).to_file(FUENTE / "pozos.shp")
    pd.DataFrame([
        {"nombre": "Pozo_riego_1", "stress_period": "all", "rate_m3_dia": -350},
        {"nombre": "Pozo_riego_2", "stress_period": "all", "rate_m3_dia": -300},
        {"nombre": "Pozo_APR", "stress_period": "all", "rate_m3_dia": -180},
    ]).to_csv(FUENTE / "caudales.csv", index=False)

    # Observaciones (9 piezómetros)
    rng = np.random.default_rng(7)
    obs = []
    for i in range(9):
        x = X0 + rng.uniform(300, WIDTH - 300)
        y = miny + rng.uniform(150, (maxy - miny) - 150)
        col = min(max(int((x - X0) / CELL), 0), NCOL - 1)
        row = min(max(int((y - Y0) / CELL), 0), NROW - 1)
        nivel = float(dem[row, col]) - rng.uniform(2.0, 6.0)
        obs.append({"Name": f"PZ-{i + 1:02d}", "waterHead": round(nivel, 2), "geometry": Point(x, y)})
    gpd.GeoDataFrame(obs, crs=CRS).to_file(FUENTE / "observaciones.shp")

    # Geología: 3 unidades O->E (K horizontal + coef. de infiltración)
    tercio = WIDTH / 3
    unidades = [("Conos aluviales (grava)", 14.0, 0.12), ("Relleno fluvial (arena-limo)", 5.0, 0.08),
                ("Roca fracturada de borde", 0.5, 0.03)]
    polys, filas = [], []
    for i, (u, k, c) in enumerate(unidades):
        polys.append(box(X0 + i * tercio, Y0, X0 + (i + 1) * tercio, Y0 + HEIGHT))
        filas.append({"unidad": u, "K_md": k, "coef_inf": c})
    gpd.GeoDataFrame(filas, geometry=polys, crs=CRS).to_file(FUENTE / "geologia.shp")

    # Perfil litológico: acuífero libre / acuitardo / grava basal
    pd.DataFrame([
        {"layer": 1, "unidad": "Relleno aluvial (acuifero libre)", "kx_m_d": 12.0, "kz_m_d": 1.2,
         "sy": 0.12, "ss": 1e-05, "iconvert": 1},
        {"layer": 2, "unidad": "Lente de arcilla (acuitardo)", "kx_m_d": 0.2, "kz_m_d": 0.01,
         "sy": 0.03, "ss": 4e-04, "iconvert": 0},
        {"layer": 3, "unidad": "Grava basal (acuifero confinado)", "kx_m_d": 7.0, "kz_m_d": 0.7,
         "sy": 0.07, "ss": 1e-05, "iconvert": 0},
    ]).to_csv(FUENTE / "perfil_litologico.csv", index=False)

    # Clima DIARIO (3 años) + caudal del río medido (para flujo base)
    fechas, precip, et0 = _clima_diario()
    pd.DataFrame({"fecha": fechas.strftime("%Y-%m-%d"), "precip_mm": precip, "et0_mm": et0}).to_csv(
        FUENTE / "clima.csv", index=False)
    caudal = _caudal_rio(fechas, precip, et0)
    pd.DataFrame({"fecha": fechas.strftime("%Y-%m-%d"), "caudal_m3_d": caudal}).to_csv(
        FUENTE / "caudal_rio.csv", index=False)

    print(f"Datos de ejemplo_clima generados en {FUENTE}")
    print(f"  clima.csv: {len(fechas)} dias ({ANIOS} anios), precip anual ~{precip.sum() / ANIOS:.0f} mm")
    print(f"  caudal_rio.csv: caudal medio ~{caudal.mean():.0f} m3/d")


if __name__ == "__main__":
    construir()
