# datos/fuente/ — insumos crudos

Pon aquí tus archivos tal cual los tienes y corre `mfw prep`:

- `dem.tif`        DEM del lugar (raster, metros)
- `dominio.shp`    borde del modelo (polígono)
- `pozos.shp`      pozos (puntos, campo `nombre`)
- `caudales.csv`   bombeos (`nombre, stress_period, rate_m3_dia`)
- `rio.shp`        río (línea, opcional)
- `observaciones.shp` + `niveles.csv`  (opcional, calibración)

Todos en el mismo CRS proyectado (metros). Ver docs/preparacion_datos.md.
