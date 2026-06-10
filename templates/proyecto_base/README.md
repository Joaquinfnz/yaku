# Proyecto: {{nombre}}

- **Autor:** {{autor}}
- **Empresa:** {{empresa}}
- **Fecha:** {{fecha}}

Proyecto de modelación de aguas subterráneas (MODFLOW 6 + FloPy) generado con
`yaku`. Estructura autocontenida y replicable.

## Estructura
```
config.yaml                  parámetros del proyecto (etapas ASTM)
00_checklist_datos_ASTM.md   checklist de datos por etapa
datos/tablas/                tablas de entrada (CSV) — ver datos/README.md
datos/gis/                   geometrías (GeoJSON/shapefile) para motor mfsetup
resultados/                  salidas del modelo (no versionado)
informe/                     informe PDF (no versionado)
```

## Flujo de trabajo
```bash
yaku build    --project .     # Etapa 3: construir el modelo
yaku run      --project .     # ejecutar MODFLOW 6
yaku calibrate --project .    # Etapas 4-5: calibración / sensibilidad
yaku report   --project .     # Etapa 7: informe (perfil astm | sea)
# o todo de una:
yaku pipeline --project .     # build -> run -> report
```

Edita `datos/tablas/*.csv` con tus datos reales (ver `00_checklist_datos_ASTM.md`)
y vuelve a correr. Los resultados se regeneran; versiona `config.yaml` + `datos/`.
