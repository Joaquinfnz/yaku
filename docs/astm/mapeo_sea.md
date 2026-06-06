# Mapeo etapas ASTM ↔ contenidos SEIA (SEA 2012 + 2022)

El motor del workflow sigue el protocolo de modelación **ASTM D5447** (aplicación
de un código) y **D5981** (calibración). El informe se exporta en dos perfiles
(`informe.perfil: astm | sea`). Ambos consumen el mismo modelo y resultados; solo
cambia la estructura del entregable.

| Etapa ASTM (perfil `astm`) | Sección informe SEIA (perfil `sea`) | Referencia SEA |
|----------------------------|--------------------------------------|----------------|
| 1. Propósito y objetivos | 1. Introducción y objetivos | Guía SEA 2012 §1 |
| 2. Modelo conceptual | 2. Antecedentes y área de estudio + 3. Modelo conceptual | Guía SEA 2012 §3 |
| 3. Diseño del modelo numérico | 4. Construcción del modelo numérico | Guía SEA 2012 §3 |
| 4. Calibración (D5981) | 5. Calibración y validación | Guía SEA 2012 §3-4 |
| 5. Análisis de sensibilidad | 5. Calibración y validación (sensibilidad) | Guía SEA 2012 §4 |
| 6. Predicción e incertidumbre | 6. Simulaciones predictivas | Guía SEA 2012 §4; SEA 2022 recurso hídrico |
| (transversal al uso del modelo) | 7. Plan de seguimiento de variables ambientales | Guía SEA 2012 §6 |
| 7. Conclusiones | 8. Conclusiones | — |

## Notas
- El perfil `astm` es genérico internacional; sirve para proyectos dentro y fuera
  del SEIA.
- El perfil `sea` agrega la sección de **plan de seguimiento** (exigida por el
  SEIA) y reordena los contenidos según la Guía SEA 2012, complementada con los
  criterios de recurso hídrico SEA 2022.
- La trazabilidad del método (estándar ASTM aplicado) se estampa desde
  `config.yaml: astm.estandar` y en `resultados/inputs_metadata.json`.
