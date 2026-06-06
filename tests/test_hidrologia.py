"""Tests del modulo de hidrologia/clima (balance diario, indices, flujo base, desfase)."""
import numpy as np
import pandas as pd

from mfworkflow import hidrologia as h


def _clima_sintetico(anios=5, seed=1):
    rng = np.random.default_rng(seed)
    fechas = pd.date_range("2015-01-01", periods=anios * 365, freq="D")
    doy = fechas.dayofyear.to_numpy()
    # lluvia estacional (invierno austral) + ruido, ET opuesta
    base = 4.0 * (1 + np.cos(2 * np.pi * (doy - 200) / 365))
    precip = np.clip(base * rng.gamma(1.0, 1.0, len(doy)), 0, None)
    pet = 2.0 * (1 + np.cos(2 * np.pi * (doy - 20) / 365)) + 0.5
    return fechas, precip, pet


def test_balance_diario_no_negativo_y_conserva():
    _f, p, e = _clima_sintetico()
    rec = h.balance_suelo_diario(p, e, cc_mm=80, coef_escorrentia=0.1, k_percolacion=0.3)
    assert len(rec) == len(p)
    assert (rec >= -1e-9).all()                 # recarga nunca negativa
    # la recarga no puede exceder la lluvia total infiltrada
    assert rec.sum() <= p.sum()


def test_agregar_a_periodos_mensual():
    f, p, e = _clima_sintetico(anios=2)
    rec = h.balance_suelo_diario(p, e)
    tab = h.agregar_a_periodos(f, rec, freq="MS")
    assert len(tab) == 24                        # 2 anios mensuales
    assert (tab["dias"] > 0).all()
    assert (tab["media_mm_d"] >= 0).all()


def test_spi_spei_estandarizados():
    _f, p, e = _clima_sintetico()
    pm = pd.Series(p).rolling(30).sum().dropna().to_numpy()[::30]   # ~mensual
    s = h.spi(pm, escala=3)
    fin = s[np.isfinite(s)]
    assert fin.size > 5
    assert -4 < fin.mean() < 4 and fin.std() > 0.3   # centrado y con dispersion
    sp = h.spei(pm, pm * 0.5, escala=3)
    assert np.isfinite(sp).any()


def test_separacion_flujo_base():
    rng = np.random.default_rng(0)
    n = 365
    base = 2.0 + np.sin(np.arange(n) / 40.0)            # componente lenta
    picos = rng.gamma(0.3, 5.0, n)                      # crecidas rapidas
    q = base + picos
    b = h.separacion_flujo_base(q, alpha=0.925, pasadas=3)
    assert (b <= q + 1e-9).all()                        # base <= caudal total
    assert (b >= -1e-9).all()
    bfi = h.indice_flujo_base(q, b)
    assert 0.0 < bfi < 1.0


def test_correlacion_desfase_detecta_lag():
    n = 120
    forz = np.sin(np.arange(n) / 6.0)
    resp = np.r_[np.zeros(3), forz[:-3]]                # respuesta retrasada 3 periodos
    out = h.correlacion_desfase(forz, resp, max_lag=8)
    assert out["lag"] == 3
    assert out["r"] > 0.8
