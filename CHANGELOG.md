# Changelog

Formato basado en [Keep a Changelog](https://keepachangelog.com/es/1.1.0/);
versiones según [SemVer](https://semver.org/lang/es/).

## [1.0.0-beta] — 2026-06-10

Primera versión pública con el nombre **YAKU-MODFLOW** (repo renombrado;
el paquete y el comando siguen siendo `yaku`). La numeración del proyecto se
reinicia en 1.0 beta para la serie pública; las versiones 1.0/2.0 anteriores
fueron desarrollo interno (`mfworkflow` / `yaku`).

### Agregado
- Renombre público a **YAKU-MODFLOW** (repo GitHub, README, CITATION).
- `yaku clima`: subcomando CLI para convertir series CR2 / CAMELS-CL a `clima.csv`.
- Tutorial Word/PDF regenerado con las secciones nuevas (clima chileno, pilot
  points, multi-objetivo, balance por zonas, geometría no plana).
- Documentación actualizada (arquitectura, preparación de datos, etapas ASTM,
  matriz de alineación SEA, roadmap con estado real).
- CI con GitHub Actions (`pytest -m "not slow"` + ruff en cada push/PR).
- `pre-commit` con ruff y chequeos básicos; configuración de ruff en `pyproject.toml`.
- Calibración con **pilot points** (`pyemu.PstFrom`) como alternativa a zonas/multiplicadores.
- Geometría **no plana** en el motor simple: `capas_modelo.csv` acepta superficies raster
  de techo/base por unidad.
- Postproceso SEA: balance por zonas (ZoneBudget), isopiezas, profundidad de napa y
  descensos con/sin proyecto, integrados al informe `--perfil sea`.
- Lectores de clima **CR2 (Explorador Climático)** y **CAMELS-CL** → `clima.csv` estándar.
- Calibración **multi-objetivo**: niveles + caudal base SFR como grupos de observación PEST.

### Corregido
- Mensajes de la CLI/TUI que aún decían `mfw` tras el renombre a `yaku`.
- Referencias rotas del README (`plan_mejoras_v2.md`, `ejemplo_regional`).
- Figura SPI del informe: el índice SPEI-6 se calculaba pero no se graficaba.
- Variables muertas detectadas por ruff (builder, evaluate, modpath7, prepare).

## [2.0.0] — 2026-06-09
- Renombre del proyecto a **Yaku** (paquete `src/yaku`, comando `yaku`; `mfw` queda como alias).
- SFR/UZF end-to-end; balance de recarga UZF; limpieza del caso demo.
- Acreditación de motores base (USGS) y `CITATION.cff`.

## [1.0.0] — 2026-06-05
- Primera versión estable del workflow como paquete instalable (`mfworkflow`):
  MODFLOW 6 + FloPy, clima–hidrogeología, índices, informes ASTM/SEA.
