# Checklist de datos por etapa ASTM ({{nombre}})

Protocolo de modelación **ASTM D5447** (aplicación de un código) y **D5981**
(calibración). Completa cada etapa antes de avanzar. La columna "Archivo" indica
dónde van los datos dentro de `datos/`.

## Etapa 1 — Propósito y objetivos (`config.yaml: objetivos`)
- [ ] Objetivo del modelo definido (qué pregunta responde).
- [ ] Régimen: steady-state o transiente.
- [ ] Escala: local o regional.
- [ ] Tipo de salida buscada: descensos, balance, zonas de captura, transporte, etc.

## Etapa 2 — Modelo conceptual (`datos/gis/`, `datos/tablas/`)
- [ ] Sistema de coordenadas (CRS) y extensión del dominio → `datos/gis/dominio.geojson`.
- [ ] DEM / topografía (techo del acuífero).
- [ ] Estratigrafía: techo y base por capa hidroestratigráfica → `capas_modelo.csv`.
- [ ] Estimaciones de K, Sy, Ss (ensayos de bombeo) → `capas_modelo.csv`.
- [ ] Recarga (por zonas o tiempo) → `parametros_modelo.csv` / `recarga_periodos.csv`.
- [ ] Cuerpos de agua: ríos, canales, mar → `rio.csv`, `datos/gis/rio.geojson`.
- [ ] Pozos: ubicación, caudales, fechas → `pozos.csv`, `datos/gis/pozos.geojson`.
- [ ] Balance hídrico conceptual (entradas/salidas).

## Etapa 3 — Diseño del modelo numérico (`datos/tablas/`)
- [ ] Discretización espacial: nrow, ncol, delr, delc → `parametros_modelo.csv`.
- [ ] Número de capas (nlay) coherente con `capas_modelo.csv`.
- [ ] Condiciones de borde → `contornos_carga.csv`.
- [ ] Condición inicial (carga inicial) → `parametros_modelo.csv`.
- [ ] Discretización temporal (stress periods) → `stress_periods.csv`.

## Etapa 4 — Calibración (D5981) (`datos/tablas/`)
- [ ] Niveles observados con peso y grupo → `observaciones_nivel.csv`.
- [ ] Parámetros ajustables con rangos → `parametros_calibracion.csv`.
- [ ] Objetivo de ajuste (RMSE/MAE aceptable) definido.

## Etapa 5 — Análisis de sensibilidad
- [ ] Lista de parámetros a analizar (deriva de Etapa 4).

## Etapa 6 — Predicción + incertidumbre
- [ ] Escenarios de predicción definidos.
- [ ] Estrategia de incertidumbre (ensemble PEST++-IES).

## Etapa 7 — Reporte (`config.yaml: informe`)
- [ ] Perfil de informe: `astm` (genérico) o `sea` (SEIA Chile).
- [ ] Para perfil `sea`: plan de seguimiento de variables ambientales.

---

### Preguntas prácticas previas
1. ¿El modelo será steady-state o transiente?
2. ¿Cuántas capas necesitas?
3. ¿El dominio es local o regional?
4. ¿Tus bordes son de carga, no flujo, río o general head?
5. ¿Tienes datos para calibrar o solo para explorar?
