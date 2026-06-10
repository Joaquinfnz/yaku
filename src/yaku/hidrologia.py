#!/usr/bin/env python3
"""Hidrología y clima: balance de suelo diario, índices climáticos e hidrológicos,
separación de flujo base y respuesta napa–clima (desfase).

Pre-proceso SIMPLE (no un modelo hidrológico completo) para convertir una serie climática
multianual en la recarga del modelo hidrogeológico, y postproceso para sacar indicadores
correlacionados (la hidrogeología sigue siendo el centro). Todo en metros/días/mm coherentes.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger("yaku")


def pet_hargreaves(temp_c, *, lat: float = -33.0, td: float = 12.0) -> np.ndarray:
    """ET potencial diaria (mm/dia) via Hargreaves-Samani (1985).

    PET = 0.0023 * RA * (T + 17.8) * sqrt(TD)

    donde RA = radiacion extraterrestre (MJ/m2/dia) calculada desde la latitud,
    T = temperatura media (C), TD = rango diurno de temperatura (C).
    Si TD no esta disponible, se usa un valor tipico de 12 C.

    Parametros:
        temp_c: temperatura media (C), puede ser array.
        lat: latitud en grados (negativo hemisferio sur). Default -33 (Santiago).
        td: rango diurno de temperatura (C). Default 12.

    Retorna:
        PET en mm/dia (array numpy, mismo largo que temp_c).
    """
    T = np.clip(np.asarray(temp_c, dtype=float), -20, None)
    n = len(T)
    doy = np.arange(1, n + 1)
    lat_rad = np.radians(lat)
    decl = 0.409 * np.sin(2.0 * np.pi * doy / 365.0 - 1.39)
    ws = np.arccos(np.clip(-np.tan(lat_rad) * np.tan(decl), -1, 1))
    ra = (24.0 * 60.0 / np.pi) * 0.0820 * (
        ws * np.sin(lat_rad) * np.sin(decl)
        + np.cos(lat_rad) * np.cos(decl) * np.sin(ws)
    )
    pet = 0.0023 * ra * (T + 17.8) * np.sqrt(td)
    return np.clip(pet, 0, None)


# --------------------------------------------------------------------------- #
# 1) Balance de suelo diario  ->  recarga (la infiltracion que alimenta el modelo)
# --------------------------------------------------------------------------- #
def balance_suelo_diario(precip_mm, pet_mm, *, cc_mm: float = 100.0,
                         wp_mm: float = 50.0, coef_escorrentia: float = 0.1,
                         k_percolacion: float = 1.0,
                         soil_inicial: float | None = None) -> np.ndarray:
    """Recarga diaria (mm/día) con un balde de suelo + reservorio de percolación.

    Cada día: la lluvia que no escurre (P·(1−esc)) menos la ET REAL (ajustada por
    humedad del suelo) ajusta el almacenamiento del suelo (entre wp_mm y cc_mm).
    La ET real se reduce cuando el suelo está por debajo de capacidad de campo:
    AET = PET × min(1, soil / cc_mm). Esto evita sobre-estimar la ET en suelos secos
    (clave en clima semiárido). El excedente entra a un reservorio de percolación
    que libera recarga con constante `k_percolacion` (0–1; 1 = sin retardo).

    Parametros:
        precip_mm: precipitacion diaria (mm/dia).
        pet_mm: ET potencial diaria (mm/dia). Se usa Hargreaves si no hay datos.
        cc_mm: capacidad de campo del suelo (mm). Default 100.
        wp_mm: punto de marchitez permanente (mm). Debajo de este umbral, AET=0.
               Default 50 (tipico suelo franco-arenoso).
        coef_escorrentia: fraccion de la lluvia que escurre directamente (0-1).
        k_percolacion: constante de liberacion del reservorio (0-1). 1 = sin retardo.
        soil_inicial: humedad inicial del suelo (mm). Default = cc_mm (saturado).
    """
    P = np.asarray(precip_mm, dtype=float)
    PET = np.asarray(pet_mm, dtype=float)
    n = len(P)
    soil = float(cc_mm if soil_inicial is None else soil_inicial)
    k = float(np.clip(k_percolacion, 1e-3, 1.0))
    perc = 0.0
    rec = np.zeros(n)
    for i in range(n):
        pct = P[i] * (1.0 - coef_escorrentia)
        aet = PET[i] * min(1.0, soil / cc_mm) if cc_mm > 0 else PET[i]
        aet = min(aet, max(0.0, soil - wp_mm) + pct)
        bal = pct - aet
        if bal >= 0:
            espacio = cc_mm - soil
            exceso = max(0.0, bal - espacio)
            soil = min(cc_mm, soil + bal)
        else:
            soil = max(wp_mm, soil + bal)
            exceso = 0.0
        perc += exceso
        liberado = k * perc
        rec[i] = liberado
        perc -= liberado
    return rec


def agregar_a_periodos(fechas, valores_diarios, *, freq: str = "MS") -> pd.DataFrame:
    """Agrega una serie diaria a periodos de stress (mensual por defecto).

    Devuelve un DataFrame con: inicio (fecha), dias del periodo, suma_mm (lámina total) y
    media_mm_d (tasa media en mm/día, lista para convertir a m/d en recarga_periodos.csv).
    """
    s = pd.Series(np.asarray(valores_diarios, dtype=float), index=pd.to_datetime(fechas))
    grupo = s.resample(freq)
    suma = grupo.sum()
    dias = grupo.count().clip(lower=1)
    return pd.DataFrame({
        "inicio": suma.index,
        "dias": dias.to_numpy(dtype=float),
        "suma_mm": suma.to_numpy(dtype=float),
        "media_mm_d": (suma.to_numpy(dtype=float) / dias.to_numpy(dtype=float)),
    }).reset_index(drop=True)


# --------------------------------------------------------------------------- #
# 2) Índices climáticos / hidrológicos
# --------------------------------------------------------------------------- #
def _estandarizar_empirico(x: np.ndarray) -> np.ndarray:
    """Índice estandarizado no paramétrico: rango -> cuantil normal (Gringorten).

    Sirve para SPEI (P−PET puede ser negativo) y como respaldo robusto del SPI.
    """
    from scipy.stats import norm
    x = np.asarray(x, dtype=float)
    z = np.full(len(x), np.nan)
    m = np.isfinite(x)
    if m.sum() < 4:
        return z
    rangos = pd.Series(x[m]).rank().to_numpy()
    p = (rangos - 0.44) / (m.sum() + 0.12)          # posición de Gringorten
    z[m] = norm.ppf(np.clip(p, 1e-6, 1 - 1e-6))
    return z


def spi(precip_periodo, escala: int = 3) -> np.ndarray:
    """Índice de Precipitación Estandarizado (SPI) a una escala (n.º de periodos acumulados).

    Acumula la precipitación en ventana `escala`, ajusta una Gamma y la transforma a normal
    estándar. SPI < −1 indica sequía; > 1, humedad. Si no hay scipy o pocos datos, usa el
    estandarizado empírico.
    """
    x = pd.Series(np.asarray(precip_periodo, dtype=float)).rolling(
        escala, min_periods=escala).sum().to_numpy()
    try:
        from scipy.stats import gamma, norm
        z = np.full(len(x), np.nan)
        m = np.isfinite(x)
        val = x[m]
        pos = val[val > 0]
        if len(pos) < 5:
            return _estandarizar_empirico(x)
        a, _loc, scale = gamma.fit(pos, floc=0)
        q0 = (len(val) - len(pos)) / len(val)        # probabilidad de cero
        cdf = np.where(val > 0, q0 + (1 - q0) * gamma.cdf(val, a, loc=0, scale=scale), q0 / 2.0)
        z[m] = norm.ppf(np.clip(cdf, 1e-6, 1 - 1e-6))
        return z
    except Exception:  # noqa: BLE001
        return _estandarizar_empirico(x)


def spei(precip_periodo, pet_periodo, escala: int = 3) -> np.ndarray:
    """Índice Estandarizado de Precipitación−Evapotranspiración (SPEI) a una escala dada.

    Igual que el SPI pero sobre el balance climático P−PET, capturando el efecto de la demanda
    evaporativa (clave en clima árido). Estandarizado no paramétrico (P−PET es signo libre).
    """
    d = np.asarray(precip_periodo, dtype=float) - np.asarray(pet_periodo, dtype=float)
    x = pd.Series(d).rolling(escala, min_periods=escala).sum().to_numpy()
    return _estandarizar_empirico(x)


def indice_aridez(precip_total_mm: float, pet_total_mm: float) -> float:
    """Índice de aridez UNEP = P/PET (anual). <0.2 hiperárido … >0.65 húmedo."""
    return float(precip_total_mm / pet_total_mm) if pet_total_mm else float("nan")


def fraccion_recarga(recarga_total_mm: float, precip_total_mm: float) -> float:
    """Fracción de la precipitación que recarga el acuífero (recarga/precipitación)."""
    return float(recarga_total_mm / precip_total_mm) if precip_total_mm else float("nan")


# --------------------------------------------------------------------------- #
# 3) Separación de flujo base (valida la recarga con el caudal del río medido)
# --------------------------------------------------------------------------- #
def separacion_flujo_base(caudal, alpha: float = 0.925, pasadas: int = 3) -> np.ndarray:
    """Separa el flujo base del hidrograma con el filtro recursivo de Lyne–Hollick.

    El flujo base es la parte del caudal del río sostenida por el agua subterránea: es una
    estimación INDEPENDIENTE de la descarga del acuífero, que se compara con el caudal base
    simulado (paquete RIV) para validar la recarga sin acoplar un modelo hidrológico completo.
    """
    q = pd.Series(np.asarray(caudal, dtype=float)).interpolate(limit_direction="both").to_numpy()
    n = len(q)
    if n < 3:
        return q.copy()
    b = q.copy()
    for p in range(pasadas):
        adelante = (p % 2 == 0)
        orden = range(1, n) if adelante else range(n - 2, -1, -1)
        anterior = -1 if adelante else 1
        bb = b.copy()
        b_new = bb.copy()
        f_prev = 0.0
        for i in orden:
            j = i + anterior
            f_i = alpha * f_prev + (1.0 + alpha) / 2.0 * (bb[i] - bb[j])
            f_i = max(0.0, f_i)
            b_i = min(bb[i], bb[i] - f_i)
            b_new[i] = max(0.0, b_i)
            f_prev = f_i
        b = b_new
    return np.minimum(b, q)


def indice_flujo_base(caudal, baseflow) -> float:
    """BFI = volumen de flujo base / volumen total (fracción sostenida por el acuífero)."""
    q = np.asarray(caudal, dtype=float)
    b = np.asarray(baseflow, dtype=float)
    tot = np.nansum(q)
    return float(np.nansum(b) / tot) if tot else float("nan")


# --------------------------------------------------------------------------- #
# 4) Respuesta napa–clima: correlación con desfase (memoria del acuífero)
# --------------------------------------------------------------------------- #
def correlacion_desfase(forzante, respuesta, max_lag: int = 12) -> dict:
    """Correlación cruzada forzante(clima)→respuesta(napa) buscando el desfase óptimo.

    Devuelve {lag, r, curva} donde `lag` es el n.º de periodos que la napa tarda en responder
    al clima (recarga o SPI) y `r` la correlación máxima. Es la "memoria" del acuífero.
    """
    a = pd.Series(np.asarray(forzante, dtype=float))
    r = pd.Series(np.asarray(respuesta, dtype=float))
    curva = []
    mejor = {"lag": 0, "r": float("nan")}
    for lag in range(0, max_lag + 1):
        c = a.corr(r.shift(-lag))                    # respuesta retrasada `lag` respecto al clima
        curva.append((lag, float(c) if pd.notna(c) else float("nan")))
        if pd.notna(c) and (pd.isna(mejor["r"]) or abs(c) > abs(mejor["r"])):
            mejor = {"lag": lag, "r": float(c)}
    mejor["curva"] = curva
    return mejor
