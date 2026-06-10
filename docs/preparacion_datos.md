# Preparación de la información para el modelo

Esta guía responde: **¿qué datos junto y en qué formato los entrego?** El comando
`yaku prep` toma estos insumos crudos y arma un borrador de las tablas del modelo.

## Dónde van los datos crudos
Dentro de tu proyecto, en `datos/fuente/`. Luego corres:

```bash
yaku prep --project proyectos/<tu_proyecto> --cellsize 100 --nlay 1 --espesor 50
```

Eso genera `datos/tablas/*.csv` (editable) y copia las capas a `datos/gis/`.

## Qué entregar y en qué formato

| Dato | Formato | Archivo en `datos/fuente/` | Para qué sirve |
|------|---------|-----------------------------|----------------|
| **DEM** del lugar | raster GeoTIFF | `dem.tif` | techo (top) del modelo y pendiente |
| **Borde** del modelo | shapefile polígono | `dominio.shp` | define la grilla y el área activa |
| **Pozos** | shapefile puntos (campo `nombre`) | `pozos.shp` | ubicación de bombeos/observación |
| **Caudales de bombeo** | CSV (`nombre, stress_period, rate_m3_dia`) | `caudales.csv` | bombeo por pozo y periodo |
| **Ríos / canales** | shapefile línea | `rio.shp` | condición de borde tipo río |
| **Niveles observados** | shapefile puntos + CSV | `observaciones.shp` + `niveles.csv` | calibración |

Unidades: longitud en **metros** (CRS proyectado, ej. UTM), caudal en **m³/día**.
**Todos los archivos en el mismo sistema de coordenadas (CRS).**

## Datos que conviene sumar (si los tienes)

Lo básico (DEM + borde + pozos + caudales) ya permite un modelo. Para un estudio
serio, agrega progresivamente:

- **Base del acuífero / espesor de capas**: raster o shapefile de puntos con
  elevación de la base de cada unidad hidrogeológica (de sondajes/geofísica).
  Si no lo tienes, `--espesor` asume un espesor uniforme.
- **Estratigrafía / capas hidrogeológicas**: define `nlay` y las propiedades por
  capa (K, Sy, Ss) → `datos/tablas/capas_modelo.csv` (lo genera `prep`, lo ajustas).
- **Zonas de conductividad (K)**: shapefile de polígonos con un campo de valor K,
  desde ensayos de bombeo. (Hoy se ingresa como K uniforme; zonas = mejora futura.)
- **Recarga**: zonas (shapefile polígono) o estimación desde precipitación/clima
  (CSV de series). Por ahora recarga uniforme (`recharge`).
- **Bordes regionales**: shapefile (línea/polígono) de carga conocida (mar, lago,
  gradiente regional) → `contornos_carga.csv`.
- **Drenes, vegas, humedales, lagunas**: shapefile polígono/línea.
- **Series de tiempo**: niveles y caudales con fecha (CSV) → define los stress periods.
- **Clima**: precipitación y evapotranspiración (CSV/raster) para estimar recarga.

## Resumen de tipos de archivo que usas tú
- **Shapefile (.shp)** → bordes, pozos, ríos, zonas, observaciones (geometría + atributos).
- **DEM / raster (.tif)** → elevaciones (top, base, K, recarga continua).
- **CSV** → series de tiempo (caudales, niveles, clima) enlazadas por `nombre`/fecha.

## Flujo completo recomendado
```bash
yaku new 2026_mi_estudio
# copia tus archivos a proyectos/2026_mi_estudio/datos/fuente/
yaku prep    --project proyectos/2026_mi_estudio
# revisa y ajusta datos/tablas/*.csv (capas, K, bordes)
yaku gis     --project proyectos/2026_mi_estudio   # (opcional) verifica el mapeo GIS
yaku pipeline --project proyectos/2026_mi_estudio  # construir, correr, informe
```
