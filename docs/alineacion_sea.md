# Alineación: MODFLOW ↔ Guía SEA ↔ ciencia ↔ yaku

Qué puede producir un modelo MODFLOW 6, qué **exige/pide la Guía SEA** (uso de modelos de aguas
subterráneas en el SEIA, 2012), qué interesa por el lado **científico**, y el **estado en
yaku**. El objetivo es que el workflow entregue, de forma estándar, **todo** lo que un
estudio SEA y un estudio científico necesitan. Autor: Joaquín Fernández.

Estado: ✅ implementado · 🟡 parcial · ⬜ por agregar.

## Lo que pide la Guía SEA (estructura del informe técnico de modelación)
Construcción del modelo hidrogeológico (modelo conceptual → discretización → parámetros → bordes)
· Presentación de resultados de las simulaciones · **Calibración** con **balance hídrico**
(flujos de entrada/salida y **discrepancia %**), niveles en régimen permanente, modelo **regional
y de detalle** · Análisis de sensibilidad · Simulaciones predictivas (con/sin proyecto) ·
Incertidumbre · Limitaciones · **Plan de seguimiento de variables ambientales** · Glosario ·
Anexos (archivos del modelo, metadatos, trazabilidad).

## Matriz de salidas

| Salida / capacidad | MODFLOW | Guía SEA | Ciencia | yaku |
|---|---|---|---|---|
| Modelo conceptual (texto + figura esquemática) | — | exige | sí | 🟡 texto (`secciones.md`); falta figura |
| Discretización: grilla DIS / DISV-Voronoi multicapa | sí | exige | sí | ✅ `mesh`, `build` |
| Mapa de carga hidráulica por capa | sí | exige | sí | ✅ informe |
| **Balance hídrico global + discrepancia %** | sí | **exige** | sí | ✅ (`Mf6ListBudget`, gate ≤1%) |
| Balance por **zonas/sectores** (regional vs detalle) | sí | pide | sí | 🟡 por capa; falta por unidad/sector definido |
| **Calibración** niveles permanente (RMSE, sesgo, scatter, residuos) | sí | **exige** | sí | ✅ |
| **Validación** (split-sample) | sí | pide | sí | ✅ grupo `validacion` |
| **Análisis de sensibilidad** (OAT por parámetro) | sí | pide | sí | ✅ `sensibilidad` + sección en el informe |
| Predicción **con/sin proyecto** (descensos) | sí | **exige** | sí | ✅ `predict` |
| Incertidumbre (ensemble) | sí | pide | sí | 🟡 Monte Carlo; falta **PEST++-IES** formal |
| Profundidad de napa + umbral **GDE** (vegas/bofedales) | sí | pide | sí | ✅ napa + GDE |
| **Caudal base** río–acuífero | sí | pide | sí | ✅ |
| Zonas de captura / tiempos de viaje (MODPATH 7) | sí | pide | sí | ✅ `pathlines` |
| **Secciones verticales** (estratos + carga) | sí | pide | sí | ✅ en el informe (PlotCrossSection) |
| Transporte de solutos / calidad de agua | sí | a veces | sí | ✅ `transport`, `salina` |
| Recarga desde clima (balance de suelo) | — | base conceptual | sí | ✅ `recarga` |
| **Plan de seguimiento** con umbrales (descensos predichos) | — | **exige** | sí | ✅ `entregables` |
| Anexos: inputs del modelo + versiones + hash | sí | exige | sí | ✅ `entregables` / `stamp` |
| Visualización 3D (litología/ríos/pozos) | sí (VTK) | apoyo | sí | ✅ `view3d` enriquecido |
| **Exportar a GIS** (cargas/napa a raster GeoTIFF) | sí | práctica | sí | ✅ `export-gis` |
| **Data-worth / FOSM** (justificar monitoreo) | vía pyemu | apoyo fuerte | sí | ⬜ por agregar |

## Lo que FALTA para "lo más completo posible" (priorizado)

**Hechos (2026-06-05):** ✅ secciones verticales · ✅ export a GIS (`export-gis`) ·
✅ análisis de sensibilidad (`sensibilidad`).

**Quedan (outputs):**
1. **Balance regional vs. detalle** (ZoneBudget por sectores definidos por el usuario). 🟡 (hay por capa)
2. **Figura del modelo conceptual** (esquema de unidades, recarga/descarga, bordes). ⬜
3. **Mapas de descenso por capa y por escenario**. 🟡

**Mejoras de modelación (ciencia + exactitud, mayor esfuerzo — roadmap):**
- **SFR** (caudal base físico con aforos) · **UZF/EVT** (ET y GDE) · **recarga distribuida por zona**.
- **Pilot points** (`pyemu.PstFrom`) + **PEST++-IES** + **data-worth** (defendible ante el SEA).
- **XT3D** (anisotropía), **MAW/LAK/DRN/HFB** (pozos multicapa, lagunas, drenes, fallas).

**Producto (consultoría privada):**
- `CHANGELOG.md` + versionado semántico, `pre-commit`, GUI **Streamlit** para informes sin CLI.
- **Bundle reproducible** (datos + config + lockfile + notebook + hash).

## Fuentes
- Guía para el uso de modelos de aguas subterráneas en el SEIA (SEA, 2012):
  <https://www.sea.gob.cl/documentacion/guias-y-criterios/guia-para-el-uso-de-modelos-de-aguas-subterraneas-en-el-seia>
- MODFLOW 6 (USGS) — paquetes y salidas: <https://www.usgs.gov/software/modflow-6-usgs-modular-hydrologic-model>,
  <https://water.usgs.gov/ogw/modflow/mf6io.pdf>
- pyemu / GMDSI (pilot points, data-worth): <https://gmdsi.org/>
