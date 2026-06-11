# Documentación de YAKU-MODFLOW

Índice de la documentación del proyecto (paquete y comando: `yaku`).

## Guías
| Archivo | Qué es |
|---------|--------|
| [arquitectura.md](arquitectura.md) | Estructura del paquete y los dos motores (simple / mfsetup). |
| [instalacion_arm64.md](instalacion_arm64.md) | Instalación en macOS Apple Silicon. |
| [preparacion_datos.md](preparacion_datos.md) | Qué datos entregar y en qué formato (DEM, shapefile, CSV, clima CR2/CAMELS). |
| [Guia_MODFLOW_FloPy_DesdeCero.md](Guia_MODFLOW_FloPy_DesdeCero.md) | Guía conceptual desde cero. |
| [roadmap.md](roadmap.md) | Integraciones futuras (MAW/LAK/MVR, XT3D, data-worth, etc.). |

## Estándares (ASTM / SEIA)
| Archivo | Qué es |
|---------|--------|
| [astm/etapas.md](astm/etapas.md) | Las 7 etapas ASTM (D5447 / D5981) y sus comandos. |
| [astm/mapeo_sea.md](astm/mapeo_sea.md) | Mapeo etapas ASTM ↔ contenidos mínimos SEIA (Guía SEA 2012). |
| [alineacion_sea.md](alineacion_sea.md) | Matriz MODFLOW ↔ Guía SEA ↔ ciencia ↔ yaku (qué tiene y qué falta). |

## Ejemplos
| Carpeta | Qué es |
|---------|--------|
| `../examples/caso_demo/` | Demo mínimo (2 capas, SFR, pozos) para probar el pipeline completo. |
| `../examples/ejemplo_clima/` | Caso end-to-end TRANSIENTE clima–hidrogeología (recarga diaria 3 años, calibración, informe). |

## Carpetas internas
- `_tools/` — scripts auxiliares (p.ej. `generar_tutorial_docx.py`, que produce el tutorial Word/PDF).
- `_build/` — salidas generadas (Tutorial Word/PDF); no se versionan, se regeneran con:
  ```bash
  python docs/_tools/generar_tutorial_docx.py
  ```
