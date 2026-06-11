# Roadmap — integraciones futuras

Ideas para hacer el modelo **más complejo y más exacto**, ordenadas por impacto.
Plan de evolución de YAKU-MODFLOW. Autor: Joaquín Fernández.

> **Hecho al 2026-06-10:** lectores CR2/CAMELS-CL (`yaku clima`) + balance de suelo
> (`yaku recarga`); SFR/UZF/DRN/GHB/EVT; Newton-Raphson; **pilot points** con kriging;
> calibración **multi-objetivo** (niveles + caudal base); **ZoneBudget por zonas**;
> geometría no plana por unidad; CI + pre-commit + CHANGELOG. Lo de abajo se mantiene
> como referencia; lo pendiente real: MAW/LAK/MVR, XT3D/GridGen/DISU, FOSM/data-worth,
> Morris/Sobol, conda-lock/pixi, TUI Textual, wizard `yaku init`.

## 1. Recarga climática (datos chilenos) — *mayor impacto*
Convertir series de clima en **recarga distribuida y transiente** mediante un
**balance hídrico de suelo** (estilo USGS *Soil-Water-Balance* / SWB2):

- Fuentes: **CR2 — Explorador Climático** (precipitación, temperatura, caudales),
  **CAMELS-CL** (series por cuenca: precip, T, ET₀ por Hargreaves/MODIS, SWE) y **DGA**
  (derechos y niveles). 
- Flujo: precip + ET₀ + uso de suelo → recarga por zona y por periodo → `recarga_periodos.csv`.
- Conecta con `clima.csv` (ya previsto como insumo opcional).

## 2. Condiciones de borde físicas (paquetes avanzados MODFLOW 6)
- **SFR** (Streamflow-Routing): interacción río–acuífero con balance de caudal; además
  el caudal base sirve como **dato de calibración** (aforos).
- **MAW** (Multi-Aquifer Well): pozos que cruzan varias capas (mejor que `WEL` en mina).
- **DRN / GHB**: drenajes y bordes regionales de carga general.
- **LAK**: lagunas / tranques. **MVR** (Water Mover): encadenar paquetes (p. ej.
  rechazo de infiltración → río).

## 3. Numérica y malla
- **XT3D**: anisotropía / tensor completo de K en mallas Voronoi irregulares.
- **Newton-Raphson** + under-relaxation: acuífero libre, celdas que se secan/rehumedecen.
- **GridGen** (quadtree) / **DISU**: refinamiento anidado donde se necesita detalle.

## 4. Calibración a nivel de decisión (GMDSI)
- **Pilot points + `pyemu.PstFrom`**: en vez de multiplicadores por zona; escala a
  10⁵–10⁶ parámetros y da mapas de K calibrados y defendibles.
- **Calibración multi-objetivo**: niveles **+ caudal base** del río.
- **FOSM / data-worth analysis**: qué dato nuevo reduce más la incertidumbre →
  **justifica las campañas de monitoreo ante el SEIA** con números.
- Sensibilidad global (Morris/Sobol) y validación **split-sample**.

## 5. Postproceso
- **ZoneBudget** por zonas; **secciones verticales**; mapas de **profundidad de napa**
  y **descensos**.

## 6. Ingeniería / replicabilidad
- **CI** con `pytest` (GitHub Actions), `pre-commit`, **`conda-lock`** para fijar el entorno.
- Posible upgrade de la terminal a **Textual** (paneles, logs en vivo, paleta Ctrl+P).

## 7. Hacia un producto replicable (ingeniería)
- **Entorno fijo**: `conda-lock` o **pixi** (hoy `environment.yml` no fija versiones).
- **CI** (GitHub Actions con pytest sobre `caso_demo`) + `pre-commit` (ruff/black) + CHANGELOG + semver.
- **Interfaz**: subir la TUI a **Textual** (paneles, logs en vivo, figuras); o mini-GUI **Streamlit** para informes.
- **Asistente** `yaku init` (wizard por tipo de estudio: dewatering / intrusión salina / GDE).
- **Bundle reproducible**: datos + config + lockfile + notebook + hash (extiende inputs_metadata.json).

## 8. Análisis a integrar (ríos + precipitación + meteorología + geología)
- **Recarga meteorológica** (prioridad): balance de suelo diario (SWB2 / estilo **mHM**) con precip+T+ET₀
  (CR2/CAMELS-CL/DGA) + uso de suelo + coef_inf por unidad geológica → recarga distribuida transiente;
  validar con cloruro (CMB), GRACE, ET MODIS.
- **Ríos**: **SFR** (caudal base, ganancia/pérdida por tramo) + **UZF** + **MVR** (filosofía GSFLOW/OWHM).
- **ET freática** (EVT/UZF) para vegas/bofedales.
- **Geología**: K calibrable por unidad (pilot points por zona), **XT3D** (anisotropía), **HFB** (fallas).
- **Bordes**: **MAW** (pozos multicapa), **LAK** (lagunas), **DRN** (dewatering).
- **Calidad**: edad del agua y trazadores sobre el GWT actual.

## 9. Salidas / indicadores para SEA y ciencia
- **Profundidad de napa** con umbrales ecológicos (declive < 2.5 m crítico para GDE).
- **Caudal base** y ganancia/pérdida por tramo de río.
- **Descensos** con/sin proyecto + **zonas de captura** (MODPATH, ya existe).
- **Balance por zonas (ZoneBudget)**: recarga, bombeo, río, ET, almacenamiento.
- **Identificación de GDE** (vegas/bofedales) y efecto del proyecto — entregable clave SEIA.
- **Incertidumbre (PEST++-IES) + data-worth** → plan de seguimiento defendible.

---

### Fuentes
- CR2 — Explorador Climático y CAMELS-CL: <https://www.cr2.cl/explorador-climatico/>,
  <https://www.cr2.cl/datos-informacion-integrada-por-cuencas/>
- Hughes et al. (2024), *FloPy Workflows for Creating Structured and Unstructured
  MODFLOW Models*, **Groundwater**.
- MODFLOW 6 (USGS): paquetes avanzados SFR/LAK/UZF/MAW/MVR.
- pyemu / GMDSI: pilot points, `PstFrom`, data-worth (FOSM). <https://gmdsi.org/>
- FloPy 3.9: GridGen / DISU (quadtree).
- GSFLOW / MODFLOW-OWHM (acople agua superficial-subterránea): <https://www.usgs.gov/software/gsflow-coupled-groundwater-and-surface-water-flow-model>
- Recarga (SWB2 / cloruro / GRACE / ET MODIS): <https://doi.org/10.3390/su18041830>
- Indicadores GDE / umbrales ecológicos: <https://www.nature.com/articles/s44221-024-00221-w>, <https://hess.copernicus.org/articles/29/2153/2025/>
