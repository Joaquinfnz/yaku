"""Validacion extendida de datos de entrada: coherencia geometrica y unidades.

Complementa ModflowModelBuilder.validate_input_data (que valida estructura y rangos
basicos) con:
  - coherencia geometrica de capas (botm estrictamente decreciente, continuidad
    top/botm, top global, carga inicial dentro de rango);
  - chequeos de plausibilidad de unidades (magnitudes tipicas de K, recarga, Ss).

Devuelve un ValidationResult con errores (bloquean) y advertencias (no bloquean).
Las unidades asumidas son las del diccionario de datos: m, m/dia, m3/dia, m2/dia.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd


# Rangos de plausibilidad (generan advertencia, no error)
K_MIN, K_MAX = 1e-6, 1e4          # m/dia
RCH_MAX = 0.05                     # m/dia (~18 m/ano, ya muy alto)
SS_MIN, SS_MAX = 1e-7, 1e-2        # 1/m
SY_MIN, SY_MAX = 0.0, 0.5         # adimensional


@dataclass
class ValidationResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def merge(self, other: "ValidationResult") -> "ValidationResult":
        self.errors.extend(other.errors)
        self.warnings.extend(other.warnings)
        return self


def _read(data_dir: Path, name: str) -> pd.DataFrame | None:
    path = data_dir / name
    if not path.exists():
        return None
    frame = pd.read_csv(path)
    return frame if not frame.empty else None


def validate_geometry_and_units(data_dir: Path) -> ValidationResult:
    """Valida coherencia geometrica y plausibilidad de unidades."""
    data_dir = Path(data_dir)
    res = ValidationResult()

    params_frame = _read(data_dir, "parametros_modelo.csv")
    params: dict[str, float] = {}
    if params_frame is not None and {"clave", "valor"} <= set(params_frame.columns):
        params = {str(r["clave"]): float(r["valor"]) for _, r in params_frame.iterrows()}

    # --- Plausibilidad de K y recarga globales ---
    if "k" in params and not (K_MIN <= params["k"] <= K_MAX):
        res.warnings.append(
            f"parametros_modelo.csv: k={params['k']} m/dia fuera del rango plausible "
            f"[{K_MIN}, {K_MAX}]. Verifica unidades (m/dia)."
        )
    if "recharge" in params and params["recharge"] > RCH_MAX:
        res.warnings.append(
            f"parametros_modelo.csv: recharge={params['recharge']} m/dia es muy alta "
            f"(> {RCH_MAX}). Verifica unidades (m/dia)."
        )

    # --- Coherencia geometrica de capas ---
    layers = _read(data_dir, "capas_modelo.csv")
    if layers is not None and {"layer", "top_m", "botm_m"} <= set(layers.columns):
        layers = layers.sort_values("layer").reset_index(drop=True)
        tops = layers["top_m"].astype(float).tolist()
        botms = layers["botm_m"].astype(float).tolist()

        # botm estrictamente decreciente
        for i in range(len(botms) - 1):
            if botms[i + 1] >= botms[i]:
                res.errors.append(
                    f"capas_modelo.csv: botm_m debe decrecer con la profundidad; "
                    f"capa {i + 2} ({botms[i + 1]}) >= capa {i + 1} ({botms[i]})."
                )
        # top > botm dentro de cada capa
        for i, (t, b) in enumerate(zip(tops, botms)):
            if t <= b:
                res.errors.append(
                    f"capas_modelo.csv: capa {i + 1} tiene top_m ({t}) <= botm_m ({b})."
                )
        # continuidad: top de capa i == botm de capa i-1
        for i in range(1, len(tops)):
            if abs(tops[i] - botms[i - 1]) > 1e-6:
                res.warnings.append(
                    f"capas_modelo.csv: discontinuidad entre capa {i} (botm={botms[i - 1]}) "
                    f"y capa {i + 1} (top={tops[i]}); ¿hueco/solape entre capas?"
                )
        # top global coincide con parametros_modelo.top
        if "top" in params and abs(tops[0] - params["top"]) > 1e-6:
            res.warnings.append(
                f"capas_modelo.csv: top de capa 1 ({tops[0]}) != parametros_modelo.top "
                f"({params['top']})."
            )
        # carga inicial dentro de [base global, top]
        if "starting_head" in params:
            sh = params["starting_head"]
            if not (botms[-1] <= sh <= tops[0]):
                res.warnings.append(
                    f"parametros_modelo.csv: starting_head ({sh}) fuera del rango del "
                    f"acuifero [{botms[-1]}, {tops[0]}]."
                )
        # plausibilidad de K/Sy/Ss por capa
        if "kx_m_d" in layers.columns:
            for i, k in enumerate(layers["kx_m_d"].astype(float)):
                if not (K_MIN <= k <= K_MAX):
                    res.warnings.append(f"capas_modelo.csv: kx_m_d capa {i + 1} = {k} fuera de rango plausible.")
        if "sy" in layers.columns:
            for i, sy in enumerate(layers["sy"].astype(float)):
                if not (SY_MIN <= sy <= SY_MAX):
                    res.warnings.append(f"capas_modelo.csv: sy capa {i + 1} = {sy} fuera de [0, 0.5].")
        if "ss" in layers.columns:
            for i, ss in enumerate(layers["ss"].astype(float)):
                if not (SS_MIN <= ss <= SS_MAX):
                    res.warnings.append(f"capas_modelo.csv: ss capa {i + 1} = {ss} fuera de rango plausible.")

    return res
