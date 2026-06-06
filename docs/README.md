# Documentación de mfworkflow

Índice de la documentación del proyecto.

## Guías
| Archivo | Qué es |
|---------|--------|
| [arquitectura.md](arquitectura.md) | Estructura del paquete y los dos motores (simple / mfsetup). |
| [instalacion_arm64.md](instalacion_arm64.md) | Instalación en macOS Apple Silicon. |
| [preparacion_datos.md](preparacion_datos.md) | Qué datos entregar y en qué formato (DEM, shapefile, CSV). |
| [Guia_MODFLOW_FloPy_DesdeCero.md](Guia_MODFLOW_FloPy_DesdeCero.md) | Guía conceptual desde cero. |
| [plan_mejoras_v2.md](plan_mejoras_v2.md) | Plan de mejoras (Voronoi, MODPATH 7, etc.). |
| [roadmap.md](roadmap.md) | Integraciones futuras (recarga climática CR2/DGA, SFR/MAW, pilot points, etc.). |

## Estándares (ASTM / SEIA)
| Archivo | Qué es |
|---------|--------|
| [astm/etapas.md](astm/etapas.md) | Las 7 etapas ASTM (D5447 / D5981) y sus comandos. |
| [astm/mapeo_sea.md](astm/mapeo_sea.md) | Mapeo etapas ASTM ↔ contenidos mínimos SEIA (Guía SEA 2012). |
| [alineacion_sea.md](alineacion_sea.md) | Matriz MODFLOW ↔ Guía SEA ↔ ciencia ↔ mfworkflow (qué tiene y qué falta). |

## Ejemplo real
| Archivo | Qué es |
|---------|--------|
| [ejemplo_regional.md](ejemplo_regional.md) | Caso real (cuenca andina, datos de Hatari Labs) corrido end-to-end con salidas reales. |
| `ejemplo_regional/` | Figuras reales del ejemplo (malla Voronoi, 3D, calibración…). |

## Carpetas internas
- `_tools/` — scripts auxiliares (p.ej. `generar_tutorial_docx.py`, que produce el tutorial Word/PDF).
- `_build/` — salidas generadas (Tutorial Word/PDF); no se versionan, se regeneran con:
  ```bash
  python docs/_tools/generar_tutorial_docx.py
  ```
