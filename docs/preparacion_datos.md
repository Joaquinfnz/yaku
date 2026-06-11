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

### Insumos opcionales (mejoran el modelo)

| Dato | Formato | Archivo en `datos/fuente/` | Para qué sirve |
|------|---------|-----------------------------|----------------|
| **Geología / unidades** | shapefile polígono (campo `coef_inf`) | `geologia.shp` | recarga zonal + zonas del balance |
| **Perfil litológico** | CSV (`layer, kx_m_d, kz_m_d, sy, ss, iconvert[, unidad]`) | `perfil_litologico.csv` | contraste acuífero/acuitardo por capa |
| **Base de cada unidad** | raster GeoTIFF | `base_capa1.tif`, `base_capa2.tif`… | **geometría no plana**: superficie de base por capa |
| **Clima** | CSV (`fecha, precip_mm[, temp_c, et0_mm]`) | `clima.csv` | recarga por balance de suelo (`yaku recarga`) |
| **Aforos / caudal base** | CSV (`nombre, caudal_m3_d[, peso]`) | `datos/tablas/aforos.csv` | calibración **multi-objetivo** (niveles + río) |
| **Zonas del balance** | CSV grilla nrow×ncol de enteros | `datos/tablas/zonas_balance.csv` | balance por sectores (estilo ZoneBudget) |
| **Zona vadosa** | CSV | `datos/tablas/uzf.csv` | UZF reemplaza RCH+EVT (infiltración con retardo) |

¿No tienes `clima.csv` a mano? Conviértelo desde fuentes chilenas:

```bash
yaku clima --project <p> --fuente cr2    --precip descarga_explorador.csv
yaku clima --project <p> --fuente camels --precip precip_cr2met_day.txt --estacion 8332001
```

Unidades: longitud en **metros** (CRS proyectado, ej. UTM), caudal en **m³/día**.
**Todos los archivos en el mismo sistema de coordenadas (CRS).**

## Datos que conviene sumar (si los tienes)

Lo básico (DEM + borde + pozos + caudales) ya permite un modelo. Para un estudio
serio, agrega progresivamente:

- **Base del acuífero / espesor de capas**: rasters `base_capa{N}.tif` con la cota de
  base de cada unidad (de sondajes/geofísica) → `yaku prep` los remuestrea a la grilla
  (`botm_grid_capa{N}.csv`) y el modelo deja de ser plano. Si no los tienes,
  `--espesor` asume un espesor uniforme.
- **Estratigrafía / capas hidrogeológicas**: define `nlay` y las propiedades por
  capa (K, Sy, Ss) → `datos/tablas/capas_modelo.csv` (lo genera `prep` desde
  `perfil_litologico.csv` si existe; lo ajustas).
- **Conductividad (K) distribuida**: la produce la calibración por **pilot points**
  (`yaku calibrate --pilot-points`): PEST ajusta K en una grilla de puntos y el campo
  interpolado queda en `k_field_capa{N}.csv`.
- **Recarga**: `geologia.shp` con `coef_inf` reparte la recarga por unidad
  (`recarga_zonas.csv`), y `clima.csv` + `yaku recarga` la hace transiente
  (balance de suelo diario o mensual).
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
