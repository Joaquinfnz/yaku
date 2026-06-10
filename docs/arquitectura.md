# Arquitectura de `yaku`

Motor instalable + sistema de plantilla por proyecto para modelación de aguas
subterráneas (MODFLOW 6 + FloPy), alineado al protocolo **ASTM D5447 / D5981**.

## Capas

```
src/yaku/            EL MOTOR (paquete instalable, comando yaku)
├── cli.py                 comando yaku (new/build/run/calibrate/report/pipeline + avanzados)
├── config.py             ProjectConfig: lee config.yaml con rutas relativas al proyecto
├── logging_setup.py       logger unificado "yaku"
├── builder/              motor SIMPLE: CSV -> MODFLOW 6 + validación geométrica/unidades
├── setup/                motor PROFESIONAL: modflow-setup (YAML+GIS) + version stamping
├── calibration/          evaluación de ajuste + PEST++ (glm/ies) vía pyemu
├── transport/            GWT (transporte) y GWT+BUY (intrusión salina)
├── pathlines/            trayectorias aproximadas (gradiente de Darcy)
├── gis/                  preproceso GeoJSON -> tablas
└── report/              informe PDF, perfiles astm | sea

templates/proyecto_base/  plantilla clonada por `yaku new`
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
yaku new      -> instancia proyecto (Etapa 1: objetivos en config.yaml)
yaku gis      -> preproceso conceptual (Etapa 2)
yaku build    -> construcción numérica (Etapa 3) + validación + stamping
yaku run      -> ejecuta MODFLOW 6
yaku calibrate-> ajuste + PEST++ (Etapas 4-5)
yaku predict  -> incertidumbre (Etapa 6)  [pyemu/pestpp-ies]
yaku report   -> informe perfil astm|sea (Etapa 7)
yaku pipeline -> build + run + report
```

## Reproducibilidad
- Cada proyecto es autocontenido y versionable con git (solo `config.yaml` + `datos/`).
- `resultados/inputs_metadata.json` registra versiones del stack + hash SHA256 de
  las entradas (ver `setup/stamp.py`).
