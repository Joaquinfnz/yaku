# MDF 1.0 — Empezar aquí

Versión final, limpia, del motor de modelación de aguas subterráneas **yaku**
(MODFLOW 6 + FloPy), para informes SEA y ciencia. Autor: **Joaquín Fernández**.

El tutorial completo (detallado, con unidades y mapa de módulos) está en:
**`docs/Tutorial_yaku.pdf`** — léelo en paralelo a estos pasos.

---

## 1. Instalar (una vez)

```bash
cd ~/Desktop/MDF_1.0
conda env create -f environment.yml        # crea el entorno (o usa el que ya tienes)
conda activate yaku
pip install -e .                            # instala el comando 'yaku'
get-modflow :flopy                          # binarios MODFLOW 6 (si faltan)
yaku doctor                                  # chequea el entorno
```

## 2. Correr el ejemplo completo (clima → modelo transiente → índices)

Este ejemplo demuestra TODO: clima diario de 3 años, recarga transiente, modelo drapeado,
calibración, predicción, informe SEA e **índices clima–hidrogeología** (SPI/SPEI, flujo base,
memoria del acuífero).

**Opción A — todo de una:**
```bash
python examples/ejemplo_clima/correr_ejemplo.py
```

**Opción B — paso a paso (como en el tutorial, sección "Tutorial paso a paso"):**
```bash
P=examples/ejemplo_clima
python $P/construir_datos.py                              # genera clima + caudal + GIS
yaku prep    --project $P --cellsize 100 --nlay 3 --espesor 60
yaku recarga --project $P --metodo balance --transiente   # clima diario -> recarga transiente
# (edita aquí datos/tablas/*.csv si quieres cambiar K, bordes, etc.)
yaku check   --project $P
yaku gis     --project $P
yaku build   --project $P
yaku run     --project $P
yaku indices --project $P                                  # SPI/SPEI, flujo base, memoria napa-clima
yaku calibrate --project $P
yaku predict   --project $P --uncertainty 10
yaku report    --project $P --perfil sea
yaku entregables --project $P --perfil sea
```

## 3. Dónde mirar los resultados
- **Informe:** `examples/ejemplo_clima/informe/informe_ejemplo_clima_sea.pdf`
- **Índices clima–hidrogeología:** `examples/ejemplo_clima/resultados/indices/`
  (SPI, respuesta napa–clima, separación de flujo base + `indices_clima.csv`).
- **Entregables SEIA:** `examples/ejemplo_clima/informe/entregables_seia/`

## 4. Tu propio proyecto
```bash
yaku new mi_estudio                          # crea proyectos/mi_estudio/
# copia tus datos a proyectos/mi_estudio/datos/fuente/ (DEM, dominio.shp, clima.csv, ...)
yaku prep --project proyectos/mi_estudio
yaku pipeline --project proyectos/mi_estudio
```

> **Qué cambiar dónde** (coeficientes, bordes, recarga, etc.): tabla "Mapa de módulos" del tutorial.
> **Unidades** de cada entrada/salida: sección "Unidades de medida" del tutorial.
> **Qué es base y qué es opcional:** info-box "Base vs opcional" del tutorial.
