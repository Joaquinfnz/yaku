# modflow-workflow (`mfworkflow`)

Workflow **replicable** de modelación de aguas subterráneas con **MODFLOW 6 + FloPy**,
para estudios hidrogeológicos en el marco del SEIA (Chile). Autoría: **Joaquín Fernández**.

Convierte el flujo de trabajo en:

1. Un **motor instalable** (`pip install -e .`, comando `mfw`).
2. Un sistema de **plantilla por proyecto**: cada estudio es una carpeta autocontenida
   (`config.yaml + datos/ + resultados/ + informe/`), versionable con git y reproducible.
3. Etapas alineadas al protocolo de modelación **ASTM D5447 / D5981**.
4. Informe con **perfil seleccionable** (`astm` genérico internacional, o `sea` con los
   contenidos mínimos del SEIA chileno: Guía SEA 2012 + criterios de recurso hídrico SEA 2022).

## Instalación (macOS Apple Silicon / conda)

```bash
conda env create -f environment.yml
conda activate modflow-workflow
get-modflow :flopy   # binarios MODFLOW 6 si hiciera falta
mfw --version
```

## Uso rápido

```bash
mfw new mi_proyecto                       # crea proyectos/mi_proyecto/
mfw pipeline --project proyectos/mi_proyecto   # build -> run -> informe
mfw calibrate --project proyectos/mi_proyecto --run --engine pestpp-ies
mfw report --project proyectos/mi_proyecto --perfil sea   # informe SEIA
```

Preparación de datos y módulos avanzados (sobre un proyecto):

```bash
mfw doctor                     # chequea el entorno (mf6, mp7, triangle, pestpp...)
mfw prep       --project <p>   # datos crudos (DEM, shp, csv) -> tablas del modelo
mfw mesh       --project <p>   # malla Voronoi/DISV refinada en pozos (--run la corre)
mfw gis        --project <p>   # shapefile/GeoJSON -> tablas
mfw transport  --project <p>   # transporte de solutos (GWT)
mfw salina     --project <p>   # intrusión salina (GWT + BUY)
mfw pathlines  --project <p>   # trayectorias MODPATH 7 (zonas de captura)
mfw predict    --project <p>   # escenario con/sin proyecto + incertidumbre
mfw view3d     --project <p>   # exporta modelo 3D a VTK (ParaView) + PNG
```

Ver `docs/preparacion_datos.md` (qué datos entregar) y `docs/plan_mejoras_v2.md`.

## Estructura

```
src/mfworkflow/   motor (builder, setup, calibration, transport, pathlines, gis, viz, report, cli)
templates/        plantilla de proyecto (proyecto_base)
proyectos/        estudios reales (uno por carpeta)
examples/         caso_demo + ejemplo_regional (end-to-end)
docs/             arquitectura, instalación ARM64, mapeo ASTM/SEA
tests/            pytest
```

## Ejemplo real

`docs/ejemplo_regional.md` — caso real con datos de Hatari Labs (cuenca andina, DEM ASTER,
piezómetros): corre el workflow completo (`mfw prep` → malla Voronoi → flujo → informe) y muestra las
salidas reales. Reproducible con `python examples/ejemplo_regional/correr_ejemplo.py`.

## Documentación

- `docs/arquitectura.md` — estructura y dos motores (simple / mfsetup).
- `docs/instalacion_arm64.md` — instalación en macOS Apple Silicon.
- `docs/astm/etapas.md` — las 7 etapas ASTM y sus comandos.
- `docs/astm/mapeo_sea.md` — mapeo ASTM ↔ contenidos SEIA (perfil de informe `sea`).
- `docs/Guia_MODFLOW_FloPy_DesdeCero.md` — guía conceptual desde cero.

## Paquetes y procesos soportados

- **Flujo (GWF)**: DIS/DISV, NPF, STO, IC, recarga (RCH) y ET (EVT).
- **Bordes**: CHD, WEL, RIV, DRN, GHB.
- **Ríos acoplados (SFR)** y **zona vadosa (UZF)** — cuando hay `uzf.csv`, UZF
  reemplaza RCH+EVT (infiltración + ET con retardo, sin doble contabilidad).
- **Transporte (GWT)** y **densidad variable / intrusión salina (BUY)**.
- **Calibración** (evaluación de ajuste + PEST++ glm/ies) y **predicción con incertidumbre**.
- **Trayectorias** (MODPATH 7) y **mallas Voronoi/DISV** refinadas en pozos.
- **Solver Newton-Raphson** para celdas convertibles (secado/rehumedecimiento).

## Licencia y cómo citar

Distribuido bajo licencia **MIT** (ver [`LICENSE`](LICENSE)): puedes usarlo, modificarlo
y redistribuirlo libremente, **conservando el aviso de copyright y autoría**.

Si lo usas en estudios, informes o publicaciones, **por favor cítalo**. GitHub muestra
un botón *"Cite this repository"* a partir de [`CITATION.cff`](CITATION.cff). Cita sugerida:

> Fernández, J. (2026). *mfworkflow: Workflow replicable de modelación de aguas
> subterráneas (MODFLOW 6 + FloPy, ASTM / SEIA Chile)*, v2.0.0.
> https://github.com/Joaquinfnz/mfworkflow

## Estado

Workflow migrado a paquete instalable (`mfworkflow`, v2.0.0). Ver historial de git
para la evolución por fases.
