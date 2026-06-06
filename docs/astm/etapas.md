# Etapas de modelación ASTM (D5447 / D5981)

El motor organiza el trabajo en las 7 etapas del protocolo ASTM. Cada etapa tiene
un comando, una entrega y una sección de informe.

| # | Etapa | Comando | Entrega | Sección informe (perfil astm) |
|---|-------|---------|---------|-------------------------------|
| 1 | Propósito y objetivos | `config.yaml: objetivos` | objetivos, tipo (steady/transiente), escala | Cap. 1 |
| 2 | Modelo conceptual | `mfw gis` + checklist | dominio, capas, balance conceptual | Cap. 2 |
| 3 | Diseño numérico | `mfw build` | grilla DIS, paquetes, inputs + stamping | Cap. 3 |
| 4 | Calibración (D5981) | `mfw calibrate` | RMSE/MAE, scatter obs-sim, parámetros | Cap. 4 |
| 5 | Sensibilidad | `mfw calibrate --setup-pest` | ranking de parámetros | Cap. 5 |
| 6 | Predicción + incertidumbre | `mfw calibrate --run --engine pestpp-ies` | escenarios, bandas de incertidumbre | Cap. 6 |
| 7 | Reporte | `mfw report --perfil astm\|sea` | PDF estructurado | doc completo |

- **D5447** — Standard Guide for Application of a Groundwater Flow Model to a
  Site-Specific Problem.
- **D5981** — Standard Guide for Calibrating a Groundwater Flow Model Application.

Para el entregable del SEIA chileno, usar `--perfil sea` (ver `mapeo_sea.md`).
