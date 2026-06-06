# Arquitectura de `mfworkflow`

Motor instalable + sistema de plantilla por proyecto para modelación de aguas
subterráneas (MODFLOW 6 + FloPy), alineado al protocolo **ASTM D5447 / D5981**.

## Capas

```
src/mfworkflow/            EL MOTOR (paquete instalable, comando mfw)
├── cli.py                 comando mfw (new/build/run/calibrate/report/pipeline + avanzados)
├── config.py             ProjectConfig: lee config.yaml con rutas relativas al proyecto
├── logging_setup.py       logger unificado "mfworkflow"
├── builder/              motor SIMPLE: CSV -> MODFLOW 6 + validación geométrica/unidades
├── setup/                motor PROFESIONAL: modflow-setup (YAML+GIS) + version stamping
├── calibration/          evaluación de ajuste + PEST++ (glm/ies) vía pyemu
├── transport/            GWT (transporte) y GWT+BUY (intrusión salina)
├── pathlines/            trayectorias aproximadas (gradiente de Darcy)
├── gis/                  preproceso GeoJSON -> tablas
└── report/              informe PDF, perfiles astm | sea

templates/proyecto_base/  plantilla clonada por `mfw new`
proyectos/                estudios reales (autocontenidos, versionables)
examples/                 caso_demo + ejemplo_regional (end-to-end)
docs/                     esta documentación + mapeo ASTM/SEA
tests/                    pytest
```

## Dos motores

| Motor | `config.yaml: motor` | Entrada | Cuándo |
|-------|----------------------|---------|--------|
| Simple | `simple` | CSV en `datos/tablas/` | casos rápidos / didácticos |
| Profesional | `mfsetup` | YAML + GIS en `datos/gis/` | proyectos reales (grilla desde shp/raster) |

## Flujo por etapas ASTM

```
mfw new      -> instancia proyecto (Etapa 1: objetivos en config.yaml)
mfw gis      -> preproceso conceptual (Etapa 2)
mfw build    -> construcción numérica (Etapa 3) + validación + stamping
mfw run      -> ejecuta MODFLOW 6
mfw calibrate-> ajuste + PEST++ (Etapas 4-5)
mfw predict  -> incertidumbre (Etapa 6)  [pyemu/pestpp-ies]
mfw report   -> informe perfil astm|sea (Etapa 7)
mfw pipeline -> build + run + report
```

## Reproducibilidad
- Cada proyecto es autocontenido y versionable con git (solo `config.yaml` + `datos/`).
- `resultados/inputs_metadata.json` registra versiones del stack + hash SHA256 de
  las entradas (ver `setup/stamp.py`).
