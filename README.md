# Yaku

Workflow **replicable** de modelación de aguas subterráneas con **MODFLOW 6 + FloPy**,
para estudios hidrogeológicos en el marco del SEIA (Chile). Autoría: **Joaquín Fernández**.

Convierte el flujo de trabajo en:

1. Un **motor instalable** (`pip install -e .`, comando `yaku`).
2. Un sistema de **plantilla por proyecto**: cada estudio es una carpeta autocontenida
   (`config.yaml + datos/ + resultados/ + informe/`), versionable con git y reproducible.
3. Etapas alineadas al protocolo de modelación **ASTM D5447 / D5981**.
4. Informe con **perfil seleccionable** (`astm` genérico internacional, o `sea` con los
   contenidos mínimos del SEIA chileno: Guía SEA 2012 + criterios de recurso hídrico SEA 2022).

## Instalación (macOS Apple Silicon / conda)

```bash
conda env create -f environment.yml
conda activate yaku
get-modflow :flopy   # binarios MODFLOW 6 si hiciera falta
yaku --version
```

## Uso rápido

```bash
yaku new mi_proyecto                       # crea proyectos/mi_proyecto/
yaku pipeline --project proyectos/mi_proyecto   # build -> run -> informe
yaku calibrate --project proyectos/mi_proyecto --run --engine pestpp-ies
yaku report --project proyectos/mi_proyecto --perfil sea   # informe SEIA
```

Preparación de datos y módulos avanzados (sobre un proyecto):

```bash
yaku doctor                     # chequea el entorno (mf6, mp7, triangle, pestpp...)
yaku prep       --project <p>   # datos crudos (DEM, shp, csv) -> tablas del modelo
yaku mesh       --project <p>   # malla Voronoi/DISV refinada en pozos (--run la corre)
yaku gis        --project <p>   # shapefile/GeoJSON -> tablas
yaku transport  --project <p>   # transporte de solutos (GWT)
yaku salina     --project <p>   # intrusión salina (GWT + BUY)
yaku pathlines  --project <p>   # trayectorias MODPATH 7 (zonas de captura)
yaku predict    --project <p>   # escenario con/sin proyecto + incertidumbre
yaku view3d     --project <p>   # exporta modelo 3D a VTK (ParaView) + PNG
```

Ver `docs/preparacion_datos.md` (qué datos entregar) y `docs/plan_mejoras_v2.md`.

## Estructura

```
src/yaku/   motor (builder, setup, calibration, transport, pathlines, gis, viz, report, cli)
templates/        plantilla de proyecto (proyecto_base)
proyectos/        estudios reales (uno por carpeta)
examples/         caso_demo + ejemplo_regional (end-to-end)
docs/             arquitectura, instalación ARM64, mapeo ASTM/SEA
tests/            pytest
```

## Ejemplo real

`docs/ejemplo_regional.md` — caso real con datos de Hatari Labs (cuenca andina, DEM ASTER,
piezómetros): corre el workflow completo (`yaku prep` → malla Voronoi → flujo → informe) y muestra las
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

> Fernández, J. (2026). *yaku: Workflow replicable de modelación de aguas
> subterráneas (MODFLOW 6 + FloPy, ASTM / SEIA Chile)*, v2.0.0.
> https://github.com/Joaquinfnz/yaku

## Créditos y herramientas base

`yaku` es una **capa de orquestación**: integra y automatiza un flujo de trabajo
sobre motores científicos de código abierto desarrollados por terceros (principalmente el
**USGS**). Este paquete **no reimplementa** esos motores; los usa como dependencias. El
crédito por el cálculo hidrogeológico corresponde a sus autores. Si publicas resultados
obtenidos con esta herramienta, **cita además los motores que usaste**:

- **MODFLOW 6** — Langevin, C.D., Hughes, J.D., Banta, E.R., Niswonger, R.G., Panday, S.,
  & Provost, A.M. (2017). *Documentation for the MODFLOW 6 Groundwater Flow Model.* U.S.
  Geological Survey Techniques and Methods, book 6, chap. A55. https://doi.org/10.3133/tm6A55
- **FloPy** — Bakker, M., Post, V., Langevin, C.D., Hughes, J.D., White, J.T., Starn, J.J.,
  & Fienen, M.N. (2016). *Scripting MODFLOW Model Development Using Python and FloPy.*
  Groundwater, 54(5), 733–739. https://doi.org/10.1111/gwat.12413
- **PEST++** — White, J.T., Hunt, R.J., Fienen, M.N., & Doherty, J.E. (2020). *Approaches to
  Highly Parameterized Inversion: PEST++ Version 5.* U.S. Geological Survey Techniques and
  Methods 7C26. https://doi.org/10.3133/tm7C26
- **pyEMU** — White, J.T., Fienen, M.N., & Doherty, J.E. (2016). *A python framework for
  environmental model uncertainty analysis.* Environmental Modelling & Software, 85, 217–228.
  https://doi.org/10.1016/j.envsoft.2016.08.017
- **MODPATH 7** — Pollock, D.W. (2016). *User guide for MODPATH version 7.* U.S. Geological
  Survey Open-File Report 2016-1086. https://doi.org/10.3133/ofr20161086

Cada dependencia conserva su propia licencia y aviso de copyright. El protocolo de modelación
sigue los estándares **ASTM D5447 / D5981** y, en Chile, la **Guía SEA 2012** (contenidos de
dominio público).

## Estado

Workflow migrado a paquete instalable (`yaku`, v2.0.0). Ver historial de git
para la evolución por fases.
