# Arquitectura de YAKU-MODFLOW (`yaku`)

Motor instalable + sistema de plantilla por proyecto para modelación de aguas
subterráneas (MODFLOW 6 + FloPy), alineado al protocolo **ASTM D5447 / D5981**.

## Capas

```
src/yaku/            EL MOTOR (paquete instalable, comando yaku)
├── cli.py                 comando yaku (new/build/run/calibrate/report/pipeline + avanzados)
├── config.py             ProjectConfig: lee config.yaml con rutas relativas al proyecto
├── logging_setup.py       logger unificado "yaku"
├── builder/              motor SIMPLE: CSV -> MODFLOW 6 + validación geométrica/unidades
│   ├── model_builder.py       orquestación (DIS/NPF/IC/STO/OC, Newton, build_and_run)
│   ├── geometria.py           capas, drapeado DEM, superficies por unidad, K distribuida, idomain
│   ├── bordes.py              CHD/WEL/RIV/DRN/GHB/EVT/SFR/UZF y recarga (uniforme/zonal/periodos)
│   └── validation.py          validación de unidades y coherencia
├── prep/                 datos crudos -> tablas (DEM, shp, perfil litológico)
│   ├── recarga.py             balance de suelo (Thornthwaite-Mather) desde clima.csv
│   └── clima_fuentes.py       lectores CR2 / CAMELS-CL -> clima.csv
├── setup/                motor PROFESIONAL: modflow-setup (YAML+GIS) + version stamping
├── calibration/          evaluación de ajuste + PEST++ (glm/ies) vía pyemu
│   ├── pest_setup.py          parámetros por zona/multiplicador (+ aforos multi-objetivo)
│   ├── pilot_points.py        pilot points + kriging -> campo K continuo
│   ├── caudales.py            caudal base SFR/RIV como observación (aforos.csv)
│   └── predict.py             escenario con/sin proyecto + Monte Carlo
├── mesh/                 mallas Voronoi/DISV (Triangle) refinadas en pozos
├── transport/            GWT (transporte) y GWT+BUY (intrusión salina)
├── pathlines/            MODPATH 7 + gradiente de Darcy
├── gis/                  preproceso shapefile/GeoJSON -> tablas + export GeoTIFF
├── viz/                  VTK (ParaView) + PyVista 3D
└── report/              informe PDF/DOCX, perfiles astm | sea
    ├── resultados.py          recolección de resultados del proyecto
    ├── figuras.py             primitivas de mapas (isopiezas, norte, escala)
    ├── zonas.py               balance por zonas (estilo ZoneBudget)
    └── indices_clima.py       SPI/SPEI, flujo base, memoria del acuífero

templates/proyecto_base/  plantilla clonada por `yaku new`
proyectos/                estudios reales (autocontenidos, versionables)
examples/                 caso_demo + ejemplo_clima (end-to-end)
docs/                     esta documentación + mapeo ASTM/SEA
tests/                    pytest (90 tests; `-m "not slow"` evita los que corren MF6)
```

## Dos motores

| Motor | `config.yaml: motor` | Entrada | Cuándo |
|-------|----------------------|---------|--------|
| Simple | `simple` | CSV en `datos/tablas/` | casos rápidos / didácticos |
| Profesional | `mfsetup` | YAML + GIS en `datos/gis/` | proyectos reales (grilla desde shp/raster) |

## Flujo por etapas ASTM

```
yaku new        -> instancia proyecto (Etapa 1: objetivos en config.yaml)
yaku prep       -> datos crudos -> tablas (DEM, shp, perfil litológico, base_capa{N}.tif)
yaku clima      -> series CR2 / CAMELS-CL -> clima.csv
yaku recarga    -> clima.csv -> recarga por balance de suelo (transiente opcional)
yaku gis        -> preproceso conceptual (Etapa 2)
yaku build      -> construcción numérica (Etapa 3) + validación + stamping
yaku run        -> ejecuta MODFLOW 6
yaku calibrate  -> ajuste + PEST++ (Etapas 4-5); --pilot-points = K continua;
                   aforos.csv = multi-objetivo (niveles + caudal base)
yaku sensibilidad -> ranking OAT de parámetros (Etapa 5)
yaku predict    -> con/sin proyecto + incertidumbre (Etapa 6)
yaku report     -> informe perfil astm|sea (Etapa 7; balance por zonas incluido)
yaku entregables-> carpeta entregables_seia/ (plan de seguimiento + anexos)
yaku pipeline   -> build + run + report
```

## Reproducibilidad
- Cada proyecto es autocontenido y versionable con git (solo `config.yaml` + `datos/`).
- `resultados/inputs_metadata.json` registra versiones del stack + hash SHA256 de
  las entradas (ver `setup/stamp.py`).
