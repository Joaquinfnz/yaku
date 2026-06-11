# Insumos para modelar (qué necesitas antes de empezar)

Esta carpeta es un **ejemplo de los archivos de entrada** que entrega el modelador
antes de correr `yaku`. Copia esta estructura a tu proyecto (`datos/fuente/`) y
reemplaza los archivos de ejemplo por los tuyos. Luego `yaku prep` los convierte en las
tablas del modelo, y `yaku check` te dice qué tienes y qué te falta.

> **Unidades fijas:** longitud en **metros**, conductividad en **m/día**, caudal en
> **m³/día**, tiempo en **días**. Todas las capas en el **mismo CRS proyectado** (UTM).

Los insumos se ordenan en tres niveles. `yaku check` usa exactamente esta clasificación.

---

## 🟥 OBLIGATORIOS (sin esto no se puede modelar)

| Insumo | Archivo | Para qué |
|--------|---------|----------|
| **Dominio** | `dominio.shp` (polígono) | Borde del modelo → define la grilla y la extensión. |
| **Parámetros del modelo** | `parametros_modelo.csv` | nlay/nrow/ncol, tamaño de celda, top, K y recarga base. |
| **Capas** | `capas_modelo.csv` | Geometría (top/botm) y K/Sy/Ss por capa. |
| **Bordes de carga** | `contornos_carga.csv` | Condiciones de borde (CHD). |
| **Tiempo** | `stress_periods.csv` | Discretización temporal (steady/transiente). |

> Las cuatro tablas se pueden **generar automáticamente** con `yaku prep` a partir del
> `dominio.shp` (+ `dem.tif`); luego las editas. El `dominio.shp` sí o sí lo pones tú.

## 🟨 IMPORTANTES (muy recomendados; suben la calidad del modelo)

| Insumo | Archivo | Para qué |
|--------|---------|----------|
| **DEM** | `dem.tif` (raster) | Topografía → `top` real del terreno. *(Ejemplo: ver `examples/ejemplo_clima/datos/fuente/dem.tif`.)* |
| **Pozos** | `pozos.shp` (puntos) | Ubicación de los pozos de bombeo. |
| **Caudales** | `caudales.csv` | Bombeo por pozo (m³/día; negativo = extracción). |
| **Niveles observados** | `observaciones.shp` o `observaciones_nivel.csv` | Niveles medidos → calibración (RMSE/MAE). |

## 🟩 OPCIONALES (habilitan procesos extra)

| Insumo | Archivo | Habilita |
|--------|---------|----------|
| **Río** | `rio.shp` (línea) | Interacción río–acuífero (paquete RIV). |
| **Recarga transiente** | `recarga_periodos.csv` | Recarga variable en el tiempo. |
| **Parámetros de calibración** | `parametros_calibracion.csv` | Calibración formal con PEST++. |
| **Geología** | `geologia.shp` (polígonos con `K_md`, `coef_inf`) | K y recarga por unidad → modelo **multicapa 3D**. |
| **Clima** | `clima.csv` (precip/temp/ET₀) | Recarga climática (integración futura). |

---

## Cómo usarlo

```bash
yaku new mi_proyecto                       # crea el proyecto desde la plantilla
cp -r templates/insumos_ejemplo/datos/fuente/* proyectos/mi_proyecto/datos/fuente/
# reemplaza los de ejemplo por tus archivos reales, luego:
yaku prep  --project proyectos/mi_proyecto # fuente -> tablas del modelo
yaku check --project proyectos/mi_proyecto # revisa obligatorios/importantes/opcionales
yaku run   --project proyectos/mi_proyecto # construye y corre (bloquea si faltan mínimos)
```

Los archivos de esta carpeta (`dominio`, `pozos`, `rio`, `observaciones`, `caudales.csv`,
`clima.csv`) son **ejemplos mínimos** para que veas el formato; no son un caso real.
