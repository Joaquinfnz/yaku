#!/usr/bin/env python3
"""Índices clima–hidrogeología: postproceso que correlaciona la serie climática con la
respuesta del acuífero. Calcula SPI/SPEI, aridez, fracción de recarga, separación de flujo
base (valida la recarga con el caudal medido) y el desfase napa–clima (memoria del acuífero).

Produce figuras + indices_clima.csv. La hidrogeología sigue siendo el centro: estos índices
resumen cómo el clima de varios años se traduce en agua subterránea.
"""

from __future__ import annotations

import logging
from pathlib import Path

import flopy
import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from yaku import hidrologia as H

logger = logging.getLogger("yaku")
_INACTIVO = 1e29


def _serie_napa(resultados_dir: Path, model_name: str) -> "np.ndarray | None":
    """Serie temporal de la carga media (capa superior) sobre celdas activas, por tiempo."""
    hds = Path(resultados_dir) / f"{model_name}.hds"
    if not hds.exists():
        return None
    try:
        hf = flopy.utils.HeadFile(str(hds), precision="double")
        serie = []
        for t in hf.get_times():
            h0 = np.asarray(hf.get_data(totim=t))
            top = h0[0] if h0.ndim == 3 else h0
            v = top[np.isfinite(top) & (np.abs(top) < _INACTIVO)]
            serie.append(float(v.mean()) if v.size else np.nan)
        return np.asarray(serie, dtype=float)
    except Exception as exc:  # noqa: BLE001
        logger.warning("No se pudo leer la serie de napa: %s", exc)
        return None


def _agregar_mensual(fechas, valores):
    s = pd.Series(np.asarray(valores, dtype=float), index=pd.to_datetime(fechas))
    g = s.resample("MS").sum()
    return g.index, g.to_numpy(dtype=float)


def calcular_indices(cfg, figuras_dir: Path | None = None) -> dict | None:
    """Calcula los índices clima–hidrogeología del proyecto. Devuelve un dict con la tabla
    resumen, las series y las figuras, o None si no hay clima.csv."""
    fuente = cfg.datos_dir.parent / "fuente"
    clima_p = fuente / "clima.csv"
    if not clima_p.exists():
        logger.warning("No hay datos/fuente/clima.csv; no se calculan indices clima-hidrogeologia.")
        return None
    figuras_dir = Path(figuras_dir) if figuras_dir else (cfg.resultados_dir / "indices")
    figuras_dir.mkdir(parents=True, exist_ok=True)

    clima = pd.read_csv(clima_p)
    if "fecha" not in clima.columns or "precip_mm" not in clima.columns:
        logger.warning("clima.csv necesita 'fecha' y 'precip_mm' para los indices.")
        return None
    fechas = pd.to_datetime(clima["fecha"])
    precip = clima["precip_mm"].astype(float).to_numpy()
    if "et0_mm" in clima.columns:
        pet = clima["et0_mm"].astype(float).to_numpy()
    elif "temp_c" in clima.columns:
        lat = float(clima["lat"].iloc[0]) if "lat" in clima.columns else -33.0
        pet = H.pet_hargreaves(clima["temp_c"].astype(float).to_numpy(), lat=lat)
        logger.warning("clima.csv sin 'et0_mm'; ET estimada via Hargreaves (lat=%.1f, aproximada).", lat)
    else:
        pet = np.zeros_like(precip)

    # Agregar a mensual (los indices se calculan a paso mensual)
    idx_m, precip_m = _agregar_mensual(fechas, precip)
    _idx, pet_m = _agregar_mensual(fechas, pet)
    anios = max(1.0, (fechas.iloc[-1] - fechas.iloc[0]).days / 365.25)

    figuras: dict[str, Path] = {}
    resumen: list[dict] = []

    # --- Índices de sequía SPI / SPEI ---
    spi3 = H.spi(precip_m, escala=3)
    spi12 = H.spi(precip_m, escala=12)
    spei6 = H.spei(precip_m, pet_m, escala=6)
    fig, ax = plt.subplots(figsize=(8, 3.2))
    ax.axhline(0, color="0.6", lw=0.8)
    ax.axhline(-1, color="#d62728", lw=0.7, ls="--")
    ax.plot(idx_m, spi3, label="SPI-3", color="#1f77b4", lw=1.0)
    ax.plot(idx_m, spi12, label="SPI-12", color="#2ca02c", lw=1.2)
    ax.plot(idx_m, spei6, label="SPEI-6", color="#ff7f0e", lw=1.0, ls=":")
    ax.set_title("Índices de sequía meteorológica (SPI / SPEI)")
    ax.set_ylabel("SPI"); ax.legend(fontsize=8)
    fig.tight_layout(); p = figuras_dir / "indice_spi.png"
    fig.savefig(p, dpi=150, bbox_inches="tight"); plt.close(fig); figuras["spi"] = p

    aridez = H.indice_aridez(float(precip.sum()) / anios, float(pet.sum()) / anios)
    resumen.append({"indice": "Índice de aridez (P/PET)", "valor": round(aridez, 3),
                    "interpretacion": _clase_aridez(aridez)})
    resumen.append({"indice": "SPI-12 mínimo (sequía máx.)", "valor": round(float(np.nanmin(spi12)), 2),
                    "interpretacion": "< -1.5 = sequía severa"})

    # --- Fracción de recarga (recarga / precipitación) ---
    rec_p = cfg.datos_dir / "recarga_periodos.csv"
    if rec_p.exists():
        rec = pd.read_csv(rec_p)
        col = next((c for c in rec.columns if "recharge" in c.lower()), None)
        sp = cfg.datos_dir / "stress_periods.csv"
        dias = pd.read_csv(sp)["perlen_d"].astype(float).to_numpy() if sp.exists() else np.full(len(rec), 30.4)
        if col is not None:
            rmd = rec[col].astype(float).to_numpy()
            n = min(len(rmd), len(dias))
            rec_mm_total = float(np.sum(rmd[:n] * 1000.0 * dias[:n]))
            frac = H.fraccion_recarga(rec_mm_total / anios, float(precip.sum()) / anios)
            resumen.append({"indice": "Recarga media anual", "valor": f"{rec_mm_total / anios:.0f} mm/año",
                            "interpretacion": "infiltración profunda al acuífero"})
            resumen.append({"indice": "Fracción de recarga (R/P)", "valor": round(frac, 3),
                            "interpretacion": "fracción de la lluvia que recarga"})

    # --- Separación de flujo base (valida la recarga con el caudal medido) ---
    caud_p = fuente / "caudal_rio.csv"          # caudal del rio MEDIDO (no confundir con caudales.csv = bombeo)
    bfi = None
    if caud_p.exists():
        cau = pd.read_csv(caud_p)
        qcol = next((c for c in cau.columns if c.lower() in
                     ("caudal_m3_s", "caudal", "q_m3_s", "flow", "caudal_l_s", "caudal_m3_d")), None)
        if qcol is not None and "fecha" in cau.columns:
            q = cau[qcol].astype(float).to_numpy()
            base = H.separacion_flujo_base(q)
            bfi = H.indice_flujo_base(q, base)
            fig, ax = plt.subplots(figsize=(8, 3.0))
            fq = pd.to_datetime(cau["fecha"])
            ax.fill_between(fq, 0, base, color="#9ecae1", label="Flujo base (subterráneo)")
            ax.plot(fq, q, color="#08519c", lw=0.7, label="Caudal total")
            ax.set_title(f"Separación de flujo base — BFI = {bfi:.2f}")
            ax.set_ylabel(f"caudal ({qcol})"); ax.legend(fontsize=8)
            fig.tight_layout(); p = figuras_dir / "flujo_base.png"
            fig.savefig(p, dpi=150, bbox_inches="tight"); plt.close(fig); figuras["flujo_base"] = p
            resumen.append({"indice": "Índice de flujo base (BFI)", "valor": round(bfi, 2),
                            "interpretacion": "fracción del río sostenida por el acuífero"})
            # Validación: flujo base OBSERVADO vs caudal base SIMULADO (RIV acuífero->río)
            try:
                from yaku.report.resultados import leer_balance
                bal = leer_balance(cfg.resultados_dir / f"{cfg.model_name}.lst")
                if bal is not None:
                    riv = bal["df"][bal["df"]["componente"] == "RIV"]
                    if not riv.empty:
                        sim_base = float(riv["salida_m3d"].iloc[0])     # acuífero -> río
                        obs_base = float(np.nanmean(base))              # flujo base medio observado
                        if obs_base > 0 and sim_base > 0:
                            err = 100.0 * (sim_base - obs_base) / obs_base
                            resumen.append({
                                "indice": "Flujo base obs vs sim (validación)",
                                "valor": f"obs {obs_base:.0f} / sim {sim_base:.0f} m³/d",
                                "interpretacion": f"diferencia {err:+.0f}% (ideal: < ±20%)"})
            except Exception:  # noqa: BLE001
                pass

    # --- Respuesta napa–clima (memoria del acuífero) ---
    napa = _serie_napa(cfg.resultados_dir, cfg.model_name)
    if napa is not None and napa.size > 6 and rec_p.exists():
        rmd = pd.read_csv(rec_p)[col].astype(float).to_numpy() if col else None
        if rmd is not None:
            n = min(len(napa), len(rmd))
            lag = H.correlacion_desfase(rmd[:n], napa[:n], max_lag=min(12, n // 3))
            resumen.append({"indice": "Memoria del acuífero (desfase napa–recarga)",
                            "valor": f"{lag['lag']} periodos (r={lag['r']:.2f})",
                            "interpretacion": "tiempo de respuesta de la napa al clima"})
            # Figura napa vs recarga
            fig, ax = plt.subplots(figsize=(8, 3.2))
            ax.bar(range(n), rmd[:n] * 1000.0, color="#9ecae1", label="recarga (mm/d)")
            ax.set_ylabel("recarga (mm/d)", color="#1f6")
            ax2 = ax.twinx()
            ax2.plot(range(n), napa[:n], color="#d62728", lw=1.4, label="napa (m)")
            ax2.set_ylabel("carga media (m)", color="#d62728")
            ax.set_title(f"Respuesta napa–clima (desfase {lag['lag']} periodos, r={lag['r']:.2f})")
            ax.set_xlabel("periodo (mes)")
            fig.tight_layout(); p = figuras_dir / "respuesta_napa_clima.png"
            fig.savefig(p, dpi=150, bbox_inches="tight"); plt.close(fig)
            figuras["respuesta"] = p

    tabla = pd.DataFrame(resumen)
    csv = figuras_dir / "indices_clima.csv"
    tabla.to_csv(csv, index=False)
    logger.info("Índices clima-hidrogeologia: %d indicadores -> %s", len(tabla), csv)
    return {"tabla": tabla, "figuras": figuras, "csv": csv, "anios": anios, "bfi": bfi}


def _clase_aridez(a: float) -> str:
    if not np.isfinite(a):
        return "sin dato"
    if a < 0.05:
        return "hiperárido"
    if a < 0.2:
        return "árido"
    if a < 0.5:
        return "semiárido"
    if a < 0.65:
        return "subhúmedo seco"
    return "húmedo"
