"""Carga y validacion del config.yaml de un proyecto.

A diferencia del workflow antiguo (rutas absolutas a 07_datos_ejemplo/...), aqui
todas las rutas son RELATIVAS a la carpeta del proyecto, de modo que cada estudio
sea autocontenido y replicable. La estructura esperada:

    proyecto:   {nombre, descripcion, autor, fecha}
    objetivos:  {proposito, tipo: steady|transient, escala: local|regional}
    motor:      simple | mfsetup
    rutas:      {datos, gis, resultados, informe}   (relativas al proyecto)
    modelo:     {name}
    solver:     {complexity}
    informe:    {perfil: astm|sea, titulo}
    astm:       {estandar}
    calibracion:{observaciones, parametros}   (relativas al proyecto)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class ProjectConfig:
    """Configuracion de un proyecto, con rutas resueltas al directorio del proyecto."""

    project_dir: Path
    raw: dict[str, Any] = field(default_factory=dict)

    # --- Acceso conveniente a bloques ---
    @property
    def proyecto(self) -> dict[str, Any]:
        return self.raw.get("proyecto", {})

    @property
    def motor(self) -> str:
        return str(self.raw.get("motor", "simple")).strip().lower()

    @property
    def model_name(self) -> str:
        return str(self.raw.get("modelo", {}).get("name", self.proyecto.get("nombre", "modelo")))

    @property
    def solver_complexity(self) -> str:
        return str(self.raw.get("solver", {}).get("complexity", "MODERATE"))

    @property
    def informe(self) -> dict[str, Any]:
        return self.raw.get("informe", {})

    @property
    def perfil_informe(self) -> str:
        return str(self.informe.get("perfil", "astm")).strip().lower()

    # --- Rutas resueltas (absolutas) ---
    def _resolve(self, key: str, default: str) -> Path:
        rel = self.raw.get("rutas", {}).get(key, default)
        path = Path(rel)
        return path if path.is_absolute() else (self.project_dir / path)

    @property
    def datos_dir(self) -> Path:
        return self._resolve("datos", "datos/tablas")

    @property
    def gis_dir(self) -> Path:
        return self._resolve("gis", "datos/gis")

    @property
    def resultados_dir(self) -> Path:
        return self._resolve("resultados", "resultados")

    @property
    def informe_dir(self) -> Path:
        return self._resolve("informe", "informe")

    @property
    def log_dir(self) -> Path:
        return self.resultados_dir / "log"

    @property
    def setup_yaml(self) -> Path:
        """Ruta al YAML de modflow-setup (motor mfsetup)."""
        rel = self.raw.get("rutas", {}).get("setup_yaml", "datos/gis/setup_mfsetup.yaml")
        path = Path(rel)
        return path if path.is_absolute() else (self.project_dir / path)

    def calib_path(self, key: str, default: str) -> Path:
        rel = self.raw.get("calibracion", {}).get(key, default)
        path = Path(rel)
        return path if path.is_absolute() else (self.project_dir / path)

    def validate(self) -> list[str]:
        """Validaciones minimas del propio config (no de los datos del modelo)."""
        errors: list[str] = []
        if not self.proyecto.get("nombre"):
            errors.append("config.yaml: falta proyecto.nombre")
        if self.motor not in {"simple", "mfsetup"}:
            errors.append(f"config.yaml: motor invalido '{self.motor}' (use simple | mfsetup)")
        if self.perfil_informe not in {"astm", "sea"}:
            errors.append(f"config.yaml: informe.perfil invalido '{self.perfil_informe}' (use astm | sea)")
        if not self.datos_dir.exists():
            errors.append(f"config.yaml: rutas.datos no existe: {self.datos_dir}")
        return errors


def load_config(config_path: Path) -> ProjectConfig:
    """Carga un config.yaml y devuelve un ProjectConfig con project_dir = carpeta padre."""
    config_path = Path(config_path)
    if not config_path.exists():
        raise FileNotFoundError(f"No existe config: {config_path}")
    with open(config_path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    return ProjectConfig(project_dir=config_path.resolve().parent, raw=raw)


def resolve_project_config(project: Path) -> ProjectConfig:
    """Acepta una carpeta de proyecto o la ruta directa a su config.yaml."""
    project = Path(project)
    config_path = project / "config.yaml" if project.is_dir() else project
    return load_config(config_path)
