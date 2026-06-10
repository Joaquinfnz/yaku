# Diccionario de datos (`datos/`)

Tablas de entrada del motor. **Unidades fijas**: longitud en **metros (m)**,
conductividad en **m/día**, caudal en **m³/día**, tiempo en **días**,
conductancia de río en **m²/día**. La Fase 4 valida estas unidades y la
coherencia geométrica.

## `tablas/parametros_modelo.csv` (clave, valor)
| clave | unidad | descripción |
|-------|--------|-------------|
| nlay, nrow, ncol | – | número de capas, filas, columnas |
| delr, delc | m | tamaño de celda (columna, fila) |
| top | m | techo del modelo |
| botm | m | base (si no se usa `capas_modelo.csv`) |
| starting_head | m | carga inicial |
| k | m/día | conductividad horizontal (si no se usa `capas_modelo.csv`) |
| recharge | m/día | recarga base |

## `tablas/capas_modelo.csv` (una fila por capa)
`layer, top_m, botm_m, kx_m_d, kz_m_d, sy, ss, iconvert`
- `top_m`, `botm_m` en m; **botm debe decrecer con la profundidad**.
- `kx_m_d`, `kz_m_d` en m/día (> 0).
- `sy` (–, 0–1), `ss` (1/m), `iconvert` (0 confinado / 1 no confinado).

## `tablas/contornos_carga.csv`
`lado, carga_m, layer, stress_period` — `lado` ∈ {izquierdo, derecho, superior, inferior}; `carga_m` en m; `layer` = número o `all` (aplica a **todas las capas**, recomendado en bordes laterales multicapa); `stress_period` = número o `all`. **Convención de filas:** row 0 = primera fila (sur, `origin='lower'`), por lo que `superior` = row 0 e `inferior` = última fila. Recomendado usar `izquierdo/derecho`.

## `tablas/pozos.csv`
`nombre, layer, row, col, stress_period, rate_m3_dia` — `rate_m3_dia` en m³/día (negativo = extracción).

## `tablas/rio.csv`
`layer, row, col, stage_m, cond_m2_d, river_bottom_m, stress_period` — `cond_m2_d` en m²/día (> 0); `river_bottom_m` ≤ `stage_m`.

## `tablas/stress_periods.csv`
`stress_period, perlen_d, nstp, tsmult, steady_state` — `perlen_d` en días (> 0); `nstp` entero (> 0); `steady_state` ∈ {0, 1}.

## `tablas/recarga_periodos.csv`
`stress_period, recharge_m_d` — `recharge_m_d` en m/día (≥ 0).

## `tablas/observaciones_nivel.csv` (calibración)
`nombre, layer, row, col, stress_period, head_observado_m, peso, grupo` — `head_observado_m` en m.

## `tablas/parametros_calibracion.csv` (calibración)
`nombre, tipo, archivo, campo, selector, valor_inicial, limite_inferior, limite_superior, transformacion, descripcion`.

## `gis/` (capas vectoriales)
`dominio.shp`, `pozos.shp`, `rio.shp` — **shapefile** (formato preferido; también se
aceptan .gpkg/.geojson). Geometrías con CRS proyectado en metros.

## `fuente/` (datos crudos para `yaku prep`)
DEM (`dem.tif`), `dominio.shp`, `pozos.shp`, `caudales.csv`, etc. Ver
`docs/preparacion_datos.md`. `yaku prep` los convierte en las tablas de `tablas/`.
