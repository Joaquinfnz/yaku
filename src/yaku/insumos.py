"""Contrato de insumos del modelo: qué archivos se necesitan, en tres niveles.

Una única fuente de verdad sobre qué hay que entregar antes de modelar, para que la
TUI (`yaku tui`), el comando `yaku check` y la validación de `build/run` hablen todos el
mismo idioma:

- **OBLIGATORIO**: mínimo imprescindible para construir/correr el modelo.
- **IMPORTANTE**: muy recomendado (top real, bombeos, calibración).
- **OPCIONAL**: habilita procesos extra (río, transiente, PEST++, multicapa, clima).

No importa geopandas ni nada pesado: solo comprueba existencia de archivos, resolviendo
las rutas con `ProjectConfig` (`config.py`).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

OBLIGATORIO = "obligatorio"
IMPORTANTE = "importante"
OPCIONAL = "opcional"
NIVELES = (OBLIGATORIO, IMPORTANTE, OPCIONAL)

_VECTOR_EXTS = (".shp", ".gpkg", ".geojson")

# Tablas que el motor necesita sí o sí para construir (gate de build/run).
MINIMOS_PARA_CORRER = (
    "parametros_modelo.csv",
    "capas_modelo.csv",
    "contornos_carga.csv",
    "stress_periods.csv",
)


@dataclass(frozen=True)
class Insumo:
    """Un insumo del modelo y cómo localizarlo dentro de un proyecto."""

    clave: str
    nivel: str
    para_que: str
    tabla: str | None = None    # CSV en datos/tablas/
    vector: str | None = None   # capa vectorial (datos/gis/ o datos/fuente/)
    fuente: str | None = None   # archivo exacto en datos/fuente/

    def localizar(self, cfg) -> Path | None:
        """Devuelve la ruta del insumo si existe en el proyecto, o None."""
        if self.tabla:
            p = cfg.datos_dir / self.tabla
            if p.exists():
                return p
        if self.vector:
            for base in (cfg.gis_dir, cfg.project_dir / "datos" / "fuente"):
                for ext in _VECTOR_EXTS:
                    p = base / f"{self.vector}{ext}"
                    if p.exists():
                        return p
        if self.fuente:
            p = cfg.project_dir / "datos" / "fuente" / self.fuente
            if p.exists():
                return p
        return None


# Catálogo completo, en el orden en que se le muestra al usuario.
CATALOGO: tuple[Insumo, ...] = (
    # --- OBLIGATORIOS ---
    Insumo("dominio", OBLIGATORIO, "Borde del modelo (polígono): define la grilla y el dominio.",
           vector="dominio"),
    Insumo("parametros_modelo.csv", OBLIGATORIO, "nlay/nrow/ncol, tamaño de celda, top, K y recarga base.",
           tabla="parametros_modelo.csv"),
    Insumo("capas_modelo.csv", OBLIGATORIO, "Geometría (top/botm) y K/Sy/Ss por capa.",
           tabla="capas_modelo.csv"),
    Insumo("contornos_carga.csv", OBLIGATORIO, "Condiciones de borde de carga (CHD).",
           tabla="contornos_carga.csv"),
    Insumo("stress_periods.csv", OBLIGATORIO, "Discretización temporal (periodos de esfuerzo).",
           tabla="stress_periods.csv"),
    # --- IMPORTANTES ---
    Insumo("dem.tif", IMPORTANTE, "DEM del terreno: da un 'top' real (mejor geometría).",
           fuente="dem.tif"),
    Insumo("pozos", IMPORTANTE, "Ubicación de los pozos de bombeo.",
           vector="pozos", tabla="pozos.csv"),
    Insumo("caudales.csv", IMPORTANTE, "Caudales de bombeo por pozo (m³/día).",
           fuente="caudales.csv"),
    Insumo("observaciones_nivel.csv", IMPORTANTE, "Niveles medidos en pozos → calibración.",
           tabla="observaciones_nivel.csv"),
    # --- OPCIONALES ---
    Insumo("rio", OPCIONAL, "Interacción río–acuífero (paquete RIV).",
           vector="rio", tabla="rio.csv"),
    Insumo("sfr.csv", OPCIONAL, "Río con routing hidráulico (Streamflow Routing, más realista que RIV).",
           tabla="sfr.csv"),
    Insumo("uzf.csv", OPCIONAL, "Zona vadosa con ET retardada (UZF, reemplaza RCH+EVT).",
           tabla="uzf.csv"),
    Insumo("uzf_periodos.csv", OPCIONAL, "Infiltración y ET por periodo para UZF.",
           tabla="uzf_periodos.csv"),
    Insumo("recarga_periodos.csv", OPCIONAL, "Recarga variable en el tiempo (transiente).",
           tabla="recarga_periodos.csv"),
    Insumo("parametros_calibracion.csv", OPCIONAL, "Parámetros ajustables con rangos (PEST++).",
           tabla="parametros_calibracion.csv"),
    Insumo("geologia", OPCIONAL, "Unidades geológicas → K y recarga por zona (modelo multicapa 3D).",
           vector="geologia", fuente="geologia.shp"),
    Insumo("clima.csv", OPCIONAL, "Series de precipitación/ET → recarga climática (integración futura).",
           fuente="clima.csv"),
)


@dataclass
class ReporteInsumos:
    """Resultado de revisar los insumos de un proyecto."""

    items: list[tuple[Insumo, Path | None]]

    def por_nivel(self, nivel: str) -> list[tuple[Insumo, Path | None]]:
        return [(ins, ruta) for ins, ruta in self.items if ins.nivel == nivel]

    def faltan(self, nivel: str) -> list[str]:
        return [ins.clave for ins, ruta in self.por_nivel(nivel) if ruta is None]

    @property
    def ok_minimos(self) -> bool:
        """True si están todos los OBLIGATORIOS."""
        return not self.faltan(OBLIGATORIO)

    @property
    def faltan_para_correr(self) -> list[str]:
        """Tablas imprescindibles para build/run que faltan (gate del motor)."""
        presentes = {ins.clave for ins, ruta in self.items if ruta is not None}
        return [t for t in MINIMOS_PARA_CORRER if t not in presentes]


def revisar_insumos(cfg) -> ReporteInsumos:
    """Revisa la presencia de cada insumo del catálogo en el proyecto."""
    return ReporteInsumos(items=[(ins, ins.localizar(cfg)) for ins in CATALOGO])


def formatear(reporte: ReporteInsumos, *, raiz: Path | None = None) -> list[str]:
    """Líneas legibles del checklist, agrupadas por nivel (para CLI/TUI sin rich)."""
    titulos = {
        OBLIGATORIO: "OBLIGATORIOS (mínimo para modelar)",
        IMPORTANTE: "IMPORTANTES (muy recomendados)",
        OPCIONAL: "OPCIONALES (procesos extra)",
    }
    lineas: list[str] = []
    for nivel in NIVELES:
        lineas.append(f"\n{titulos[nivel]}:")
        for ins, ruta in reporte.por_nivel(nivel):
            marca = "OK " if ruta else "-- "
            detalle = ""
            if ruta is not None and raiz is not None:
                try:
                    detalle = f"  ({ruta.relative_to(raiz)})"
                except ValueError:
                    detalle = f"  ({ruta})"
            lineas.append(f"  [{marca}] {ins.clave:26s} {ins.para_que}{detalle}")
    if reporte.ok_minimos:
        lineas.append("\n=> Mínimos completos: puedes construir y correr el modelo.")
    else:
        lineas.append(f"\n=> FALTAN obligatorios: {', '.join(reporte.faltan(OBLIGATORIO))}. "
                      "Complétalos antes de construir/correr (yaku prep ayuda a generarlos).")
    return lineas
