# Guia MODFLOW 6 + FloPy Desde Cero

## Para que sirve este paquete

Sirve para que un hidrogeologo externo pueda tomar un flujo base de trabajo y replicarlo sin depender de Obsidian ni del computador original.

## Workflow incluido

1. Instalacion del entorno conda
2. Verificacion tecnica del stack
3. Modelo base hardcoded para validar que el motor corre
4. Modelo guiado por datos de entrada en CSV
5. Generacion de informe PDF desde el resultado HDS

## Adaptacion ya incluida

El script `04_modelo_base/modelo_desde_datos.py` ahora acepta:

- multiples capas mediante `capas_modelo.csv`
- multiples stress periods mediante `stress_periods.csv`
- recarga variable por periodo mediante `recarga_periodos.csv`
- pozos y rios asignados por capa y periodo

## Componentes del stack

- `modflow6`: motor numerico
- `flopy`: construccion y lectura de modelos en Python
- `pyemu`: base para calibracion futura
- `geopandas` y `rasterio`: preproceso SIG
- `pyvista` y `trame`: visualizacion 3D
- `reportlab`: informe PDF

## Como aplicar 3D a MODFLOW

Despues de correr un modelo, puedes levantar una visualizacion 3D de la carga hidraulica final desde el archivo `HDS`.

```bash
conda run -n modflow-workflow python 04_modelo_base/visualizar_heads_3d.py --hds 04_modelo_base/resultados_datos/modelo_datos.hds
```

Eso te genera una superficie 3D de cargas para una capa del modelo.

## Lo minimo que debe saber el externo

- El archivo de salida principal es `*.hds`
- Los scripts de ejemplo ya dejan figuras y reportes en sus carpetas de resultados
- El modelo de datos se alimenta desde `07_datos_ejemplo/01_tablas/`

## Ruta de uso recomendada

### 1. Probar instalacion

```bash
conda run -n modflow-workflow python 00_setup/verify_installation.py
```

### 2. Correr modelo base

```bash
conda run -n modflow-workflow python 04_modelo_base/modelo_prueba.py
```

### 3. Correr modelo desde insumos

```bash
conda run -n modflow-workflow python 04_modelo_base/modelo_desde_datos.py
```

### 4. Generar informe PDF

```bash
conda run -n modflow-workflow python 06_informe_pdf/generar_informe.py --hds 04_modelo_base/resultados_datos/modelo_datos.hds --output 06_informe_pdf/output/informe_modelo_datos.pdf
```

## Como escalar este workflow

1. Reemplazar los CSV de ejemplo por datos reales
2. Agregar paquetes de bombeo, rio, recarga y almacenamiento segun proyecto
3. Integrar shapefiles o GeoJSON reales en el preproceso
4. Agregar calibracion con `pyemu`
5. Usar el PDF como base para un informe de consultoria
