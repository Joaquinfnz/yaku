#!/usr/bin/env python3
"""Genera el tutorial general de yaku en Word (.docx) + PDF.

Usa el helper de diseño `docx_helpers.DocBuilder` (tema azul/agua, sin emojis).
El helper esta **vendorizado** junto a este script (docs/_tools/docx_helpers.py) para
que el generador sea replicable en cualquier máquina; si existe la skill `crear-word`
del usuario, se prefiere esa versión. Incluye las figuras del caso demo y cubre las
capacidades actuales (prep, Voronoi/DISV, MODPATH 7, predict, 3D, doctor).
"""

from __future__ import annotations

import sys
from pathlib import Path

# docx_helpers: vendorizado aquí (replicable). Si esta la skill crear-word, se prefiere.
_AQUI = Path(__file__).resolve().parent
_SKILL = Path.home() / ".claude" / "skills" / "crear-word"
for _origen in (_SKILL, _AQUI):
    if (_origen / "docx_helpers.py").exists():
        sys.path.insert(0, str(_origen))
        break
from docx_helpers import DocBuilder, docx_to_pdf  # noqa: E402

REPO = Path(__file__).resolve().parents[2]   # docs/_tools/ -> repo
IMG = REPO / "examples" / "caso_demo" / "resultados"


def build(out_docx: Path) -> Path:
    d = DocBuilder()

    # ---------- PORTADA ----------
    d.cover(
        "YAKU-MODFLOW",
        "Modelación de aguas subterráneas con MODFLOW 6 + FloPy",
        "Tutorial general de uso  -  Autor: Joaquín Fernández",
    )
    d.p("Guía paso a paso para preparar datos, construir, calibrar, predecir y reportar "
        "modelos de flujo subterráneo de forma replicable (estándar ASTM / SEIA), pensada "
        "tanto para ti como para quien se incorpore al equipo.")

    d.h2("Contenido")
    for t in [
        "Qué es esto y para quién", "Qué puedes lograr (ejemplos reales)",
        "Conceptos mínimos (sin pánico)", "Instalación y chequeo (yaku doctor)",
        "Empezar guiado: la pantalla onboard", "La idea clave: un proyecto = una carpeta",
        "Qué datos necesitas: insumos y yaku check", "Preparación de datos (yaku prep)",
        "Recarga desde el clima (yaku recarga)", "Clima chileno: CR2 y CAMELS-CL (yaku clima)",
        "Acoplamiento clima-hidrogeologia (transiente e indices)",
        "Unidades de medida (entradas y salidas)",
        "Mapa de modulos: donde cambiar cada cosa", "Tutorial paso a paso (caso real, de principio a fin)",
        "Los comandos de yaku, uno por uno", "Los dos motores: simple y profesional (GIS)",
        "Mallas Voronoi / grilla multicapa (DISV)", "Calibración: ¿el modelo se parece a la realidad?",
        "Predicción y análisis de incertidumbre", "Trayectorias y zonas de captura (MODPATH 7)",
        "Transporte e intrusión salina", "Visualización 3D (litología, ríos, pozos)",
        "El informe SEA: data-driven y editable", "Indicadores para el SEA (napa/GDE, caudal base, balance)",
        "El paquete de entregables SEIA", "Cómo lo usa otra persona del equipo",
        "Si algo falla (problemas comunes)", "Glosario rápido",
    ]:
        d.numbered(t)
    d.page_break()

    # ---------- 1 ----------
    d.h1("Qué es esto y para quién")
    d.p("yaku automatiza todo el proceso de hacer un modelo de aguas subterráneas con "
        "MODFLOW 6, desde los datos crudos hasta el informe técnico final. Esta pensado para "
        "consultoría de forma repetible: cada estudio nuevo se arma en minutos desde una plantilla.")
    d.p("Sirve para dos públicos:")
    d.bullet("Quien ya sabe hidrogeología y quiere automatizar lo repetitivo.")
    d.bullet("Quien recién se incorpora y necesita correr un modelo sin partir de cero.")
    d.info_box("En una frase",
               "Pones tus archivos (DEM, shapefiles, CSV), escribes un comando, y obtienes el "
               "modelo corrido, calibrado, con escenarios e informe. Todo ordenado y reproducible.")

    # ---------- 2 ----------
    d.h1("Qué puedes lograr (ejemplos reales)")
    d.p("MODFLOW 6 + FloPy es el estándar mundial en modelación de aguas subterráneas. Con este "
        "workflow puedes abordar, entre otros:")
    d.table(["Aplicación", "Uso típico"], [
        ["Depresión de napas (dewatering)", "Descenso de niveles por bombeo de una mina o excavación y su efecto en pozos y vegas."],
        ["Zonas de captura / protección de pozos", "Áreas de protección a 2, 5 y 10 años (MODPATH 7)."],
        ["Transporte de contaminantes", "Avance de una pluma (nitratos, metales, solventes) y su origen."],
        ["Interacción río-acuífero", "Cómo el bombeo afecta el caudal de un río o el nivel de un humedal."],
        ["Intrusión salina costera", "Avance de la cuña salina (densidad variable, GWT + BUY)."],
        ["Línea base y predicción SEIA", "Escenarios con y sin proyecto para un EIA/DIA en Chile."],
    ])
    d.info_box("Todo desde la misma base",
               "Los módulos del workflow (preparación, malla, flujo, calibración, predicción, "
               "transporte, trayectorias, 3D e informe) comparten el mismo proyecto. Fuentes: "
               "USGS/FloPy (Hughes et al., 2024), gidahatari/Hatari Labs (mf6Voronoi).")

    # ---------- 3 ----------
    d.h1("Conceptos mínimos (sin pánico)")
    d.p("No necesitas programar. Solo entender estas ideas:")
    d.table(["Término", "Qué significa en simple"], [
        ["MODFLOW 6", "El programa que simula cómo se mueve el agua subterránea."],
        ["FloPy", "Librería de Python que arma y corre MODFLOW por nosotros."],
        ["Grilla / celdas", "El terreno se divide en celdas; cada una tiene sus propiedades."],
        ["Capas", "Las unidades del acuífero en profundidad (relleno, roca, etc.)."],
        ["Stress period", "Un tramo de tiempo de la simulación (p.ej. época de bombeo)."],
        ["Calibración", "Ajustar el modelo para que se parezca a lo medido en terreno."],
        ["DISV / Voronoi", "Grilla de celdas irregulares, más finas donde importa (pozos)."],
    ])

    # ---------- 4 ----------
    d.h1("Instalación y chequeo (yaku doctor)")
    d.p("Requiere Miniconda/Anaconda. Ubícate en la carpeta del proyecto y crea el entorno:")
    d.code("cd ~/Desktop/modflow-workflow\nconda env create -f environment.yml\nconda activate modflow-workflow")
    d.p("Verifica que todo esté instalado (binarios y paquetes) con un solo comando:")
    d.code("yaku doctor")
    d.info_box("macOS Apple Silicon (M1/M2/M3)",
               "Todo corre nativo. Si faltan binarios de MODFLOW/MODPATH/Triangle, instalalos con "
               "'get-modflow :flopy'. yaku doctor te dice exactamente qué falta.")

    # ---------- onboard ----------
    d.h1("Empezar guiado: la pantalla onboard")
    d.p("Si no te acuerdas de los comandos, no importa: escribe solo 'yaku' (o 'yaku onboard') y se "
        "abre una pantalla de inicio que te guia. Muestra el estado del entorno, te deja elegir o "
        "crear un proyecto, y dentro del proyecto te dice qué tienes hecho y cuál es el siguiente paso.")
    d.code("yaku            # abre la pantalla onboard (igual que 'yaku onboard')")
    d.p("Dentro de un proyecto, el onboard muestra un panel de estado y las etapas agrupadas por "
        "paquetes (A. insumos y malla, B. modelo, C. calibración, D. avanzados, E. resultados):")
    d.code("Estado del proyecto\n"
           "  Insumos mínimos: OK\n"
           "  Modelo corrido:  falta\n"
           "  Informe:         falta\n"
           "  => Siguiente paso: corre el modelo (Pipeline completo o build + run)")
    d.info_box("Para que sirve",
               "Es la forma más fácil de usar yaku y de que lo use alguien nuevo: en vez de "
               "memorizar comandos, sigues el 'siguiente paso sugerido'. Cada opción del menú dice "
               "que hace y que datos necesita.")

    # ---------- 5 ----------
    d.h1("La idea clave: un proyecto = una carpeta")
    d.p("Cada estudio vive en su propia carpeta, autocontenida y ordenada:")
    d.code("proyectos/mi_proyecto/\n"
           "  config.yaml          parámetros del proyecto\n"
           "  datos/fuente/        tus archivos crudos (DEM, shp, csv)\n"
           "  datos/tablas/        tablas del modelo (CSV)\n"
           "  datos/gis/           capas vectoriales (shapefile)\n"
           "  resultados/          lo que genera el modelo\n"
           "  informe/             el PDF final")
    d.p("Copias la carpeta, cambias los datos y tienes otro estudio. Versionas con git solo "
        "config.yaml + datos/; los resultados se regeneran.")

    # ---------- insumos ----------
    d.h1("Qué datos necesitas: insumos y yaku check")
    d.p("Antes de modelar conviene saber que tienes y que falta. 'yaku check' revisa los insumos del "
        "proyecto y los clasifica en tres niveles:")
    d.table(["Nivel", "Qué son", "Ejemplos"], [
        ["Obligatorios", "Minimo para correr el modelo.", "dominio.shp, parámetros_modelo.csv, capas_modelo.csv, contornos_carga.csv, stress_periods.csv"],
        ["Importantes", "Muy recomendados (suben la calidad).", "dem.tif, pozos.shp + caudales.csv, observaciones_nivel.csv"],
        ["Opcionales", "Habilitan procesos extra.", "río.shp, recarga_periodos.csv, parámetros_calibración.csv, geología.shp, clima.csv"],
    ])
    d.code("yaku datos --project proyectos/mi_proyecto    # crea plantillas de lo que falta\nmfw check --project proyectos/mi_proyecto")
    d.info_box("Bloqueo de seguridad",
               "Si faltan los obligatorios, yaku no te deja construir/correr y te dice cuales "
               "faltan. Hay una carpeta de ejemplo de insumos en templates/insumos_ejemplo/ con un "
               "LEEME que separa obligatorios / importantes / opcionales.")

    # ---------- 6 ----------
    d.h1("Preparación de datos (yaku prep)")
    d.p("Tu trabajas en shapefile, DEM y CSV. Pones esos archivos crudos en datos/fuente/ y "
        "yaku prep los convierte en las tablas del modelo. Qué entregar y en qué formato:")
    d.table(["Dato", "Formato", "Archivo en datos/fuente/"], [
        ["DEM del lugar", "raster GeoTIFF", "dem.tif"],
        ["Borde del modelo", "shapefile polígono", "dominio.shp"],
        ["Pozos", "shapefile puntos (campo nombre)", "pozos.shp"],
        ["Caudales de bombeo", "CSV (nombre, stress_period, rate_m3_dia)", "caudales.csv"],
        ["Rios / canales", "shapefile línea", "río.shp"],
        ["Niveles observados", "shapefile puntos + CSV", "observaciones.shp + niveles.csv"],
        ["Base de cada unidad (opcional)", "raster GeoTIFF", "base_capa1.tif, base_capa2.tif, ..."],
        ["Perfil litologico (opcional)", "CSV (layer, kx, kz, sy, ss, iconvert)", "perfil_litologico.csv"],
    ])
    d.code("yaku prep --project proyectos/mi_proyecto --cellsize 100 --nlay 1 --espesor 50")
    d.p("Si entregas rasters base_capa{N}.tif (cota de base de cada unidad, de sondajes o "
        "geofisica), prep los remuestrea a la grilla y el modelo deja de ser plano: cada capa "
        "sigue su superficie real, con espesor minimo garantizado (geometria no plana).")
    d.info_box("Unidades y CRS",
               "Todo en metros (CRS proyectado, p.ej. UTM), caudal en m3/dia. Todos los archivos "
               "en el mismo sistema de coordenadas. Detalle en docs/preparación_datos.md.")

    # ---------- recarga ----------
    d.h1("Recarga desde el clima (yaku recarga)")
    d.p("La recarga (el agua de lluvia que llega al acuífero) es uno de los datos más difíciles. En "
        "vez de inventar un numero, puedes calcularla desde tu serie climatica, DENTRO del workflow "
        "(sin programas externos). Pones datos/fuente/clima.csv con columnas fecha, precip_mm, "
        "temp_c, et0_mm y corres:")
    d.code("yaku recarga --project proyectos/mi_proyecto --metodo balance")
    d.p("Usa un balance de suelo simple (Thornthwaite-Mather): cada mes, lo que llueve menos lo que "
        "se evapora llena el suelo; el excedente es recarga. Escribe recarga_periodos.csv, que el "
        "modelo usa como recarga variable en el tiempo. Si no tienes ET, usa --método coeficiente "
        "(recarga = coeficiente x precipitación).")
    d.info_box("Sin salir del workflow",
               "Esto reemplaza tener que usar otro modelo hidrológico. Para casos de cuencas con "
               "deshielo (Patagonia) hay un modulo de glaciares previsto para una version futura.")

    # ---------- clima CR2 / CAMELS ----------
    d.h1("Clima chileno: CR2 y CAMELS-CL (yaku clima)")
    d.p("No necesitas armar clima.csv a mano: el comando yaku clima convierte los formatos de "
        "las fuentes chilenas mas usadas al formato del workflow.")
    d.code("yaku clima --project proyectos/mi_proyecto --fuente cr2 --precip descarga_explorador.csv\n"
           "yaku clima --project proyectos/mi_proyecto --fuente camels --precip precip_cr2met_day.txt --estacion 8332001")
    d.bullet("CR2 (explorador.cr2.cl): acepta series diarias o mensuales, con metadatos antes del "
             "encabezado, columnas fecha o agno/mes/dia, y nodata -9999.")
    d.bullet("CAMELS-CL (camels.cr2.cl): series por cuenca; eliges la tuya con --estacion (gauge_id).")
    d.bullet("Puedes sumar temperatura (--temp) y evapotranspiracion (--et0); quedan como columnas "
             "extra de clima.csv y mejoran el balance de suelo.")
    d.info_box("Flujo completo del clima",
               "yaku clima (CR2/CAMELS -> clima.csv) -> yaku recarga (balance de suelo -> recarga "
               "por periodo) -> yaku indices (SPI/SPEI, flujo base, memoria del acuifero).")

    # ---------- clima-hidrogeologia ----------
    d.h1("Acoplamiento clima–hidrogeología (transiente e índices)")
    d.p("Si das una serie climatica de varios anios, el modelo puede correr en regimen TRANSIENTE "
        "y mostrar como la napa responde al clima en el tiempo. La idea es simple: el clima entra "
        "como un pre-proceso (un balde de suelo), la hidrogeologia sigue siendo el centro, y al "
        "final salen indices que correlacionan clima y agua subterranea.")
    d.h2("1) Datos que das")
    d.table(["Archivo", "Que es", "Obligatorio?"], [
        ["datos/fuente/clima.csv", "Serie DIARIA: fecha, precip_mm, et0_mm (o temp_c).", "para transiente"],
        ["datos/fuente/caudal_rio.csv", "Caudal del rio MEDIDO (fecha, caudal_m3_d).", "opcional (valida)"],
    ])
    d.h2("2) Recarga diaria y transiente")
    d.code("yaku recarga --project proyectos/mi_proyecto --metodo balance --transiente --k-percolacion 0.05")
    d.p("Detecta que el clima es diario, corre el balance de suelo dia a dia (con un retardo de "
        "percolacion k_percolacion) y agrega la recarga a periodos mensuales. Con --transiente "
        "escribe ademas stress_periods.csv (1.er periodo permanente + el resto transiente), asi el "
        "modelo corre toda la serie. La napa sube con las lluvias y baja en los anios secos.")
    d.h2("3) Indices clima–hidrogeologia")
    d.code("yaku indices --project proyectos/mi_proyecto")
    d.p("Calcula y grafica (en resultados/indices/):")
    d.bullet("SPI / SPEI: indices de sequia meteorologica (precipitacion y precip-ET estandarizadas).")
    d.bullet("Indice de aridez (P/PET) y fraccion de recarga (recarga/precipitacion).")
    d.bullet("Separacion de FLUJO BASE del caudal medido (filtro Lyne-Hollick) e indice BFI: la parte "
             "del rio sostenida por el acuifero. Valida la recarga con un dato real, sin un modelo grande.")
    d.bullet("MEMORIA DEL ACUIFERO: el desfase (lag) con que la napa responde a la recarga/clima, por "
             "correlacion cruzada. Es el numero que conecta clima -> agua subterranea.")
    d.info_box("Base vs opcional",
               "BASE (siempre funciona): geometria, capas, K, bordes, recarga, rios, pozos, calibracion, "
               "balance, prediccion, informe. OPCIONAL (se activa con su archivo): clima multianual + "
               "transiente, caudal_rio.csv (flujo base), drn.csv/ghb.csv/evt_periodos.csv (drenes, borde "
               "regional, ET freatica/vegas), geologia.shp (K y recarga por zona), malla Voronoi. El "
               "ejemplo examples/ejemplo_clima/ corre TODO esto de punta a punta.")

    # ---------- unidades ----------
    d.h1("Unidades de medida (entradas y salidas)")
    d.p("Todo el modelo trabaja en un sistema COHERENTE: longitud en metros (m) y tiempo en "
        "dias (d). De ahi se derivan las demas (m/d, m3/d, m2/d). El error de unidad es el mas "
        "comun en modelacion y el SEA lo revisa: respeta estas unidades al editar las tablas.")
    d.h2("Unidades de las ENTRADAS (datos/tablas/ y datos/fuente/)")
    d.table(["Archivo", "Campo", "Unidad", "Que es"], [
        ["parametros_modelo.csv", "cellsize", "m", "Tamano de celda de la grilla."],
        ["parametros_modelo.csv", "top / botm", "m s.n.m.", "Cota del techo y base del modelo."],
        ["parametros_modelo.csv", "starting_head", "m", "Nivel inicial (arranque del solver)."],
        ["parametros_modelo.csv", "recharge", "m/d", "Recarga uniforme (si no hay recarga_periodos)."],
        ["capas_modelo.csv", "top_m / botm_m", "m s.n.m.", "Techo y base de cada capa."],
        ["capas_modelo.csv", "kx_m_d / kz_m_d", "m/d", "Conductividad K horizontal y vertical."],
        ["capas_modelo.csv", "sy", "adimensional (0-1)", "Rendimiento especifico (acuifero libre)."],
        ["capas_modelo.csv", "ss", "1/m", "Almacenamiento especifico (confinado)."],
        ["capas_modelo.csv", "iconvert", "0/1", "1 = libre (convertible), 0 = confinado."],
        ["geologia.shp", "K_md", "m/d", "K horizontal por unidad geologica (en planta)."],
        ["geologia.shp", "coef_inf", "fraccion (0-1)", "Coeficiente de infiltracion por unidad."],
        ["perfil_litologico.csv", "kx_m_d / kz_m_d", "m/d", "K por unidad (vertical) que arma las capas."],
        ["contornos_carga.csv", "carga_m", "m", "Carga constante (CHD) en cada borde."],
        ["stress_periods.csv", "perlen_d", "dias", "Duracion del periodo de stress."],
        ["stress_periods.csv", "nstp / tsmult / steady_state", "adim / adim / 0-1", "Pasos, multiplicador, regimen."],
        ["pozos.csv / caudales.csv", "rate_m3_dia", "m3/d", "Caudal (NEGATIVO = extraccion)."],
        ["rio.csv", "stage_m / river_bottom_m", "m", "Cota de agua y fondo del rio."],
        ["rio.csv", "cond_m2_d", "m2/d", "Conductancia del lecho (RIV)."],
        ["drn.csv (opcional)", "elev_m / cond_m2_d", "m / m2/d", "Drenes/manantiales (DRN)."],
        ["ghb.csv (opcional)", "head_m / cond_m2_d", "m / m2/d", "Borde de carga general (GHB)."],
        ["evt_periodos.csv (opcional)", "rate_m_d / extinction_depth_m", "m/d / m", "ET freatica (vegas/GDE)."],
        ["recarga_periodos.csv", "recharge_m_d", "m/d", "Recarga por periodo (de yaku recarga)."],
        ["recarga_zonas.csv", "coef_inf por celda", "fraccion", "Reparte la recarga por unidad geologica."],
        ["observaciones_nivel.csv", "head_observado_m", "m", "Nivel medido para calibrar."],
        ["observaciones_nivel.csv", "peso", "adimensional", "Peso del dato en la calibracion."],
        ["clima.csv", "precip_mm / et0_mm", "mm", "Precipitacion y evapotranspiracion por periodo."],
        ["clima.csv", "temp_c", "C", "Temperatura media del periodo."],
        ["caudal_rio.csv (opcional)", "caudal_m3_d", "m3/d", "Caudal del rio medido (valida flujo base)."],
    ])
    d.h2("Unidades de las SALIDAS")
    d.table(["Salida", "Unidad", "Donde aparece"], [
        ["Carga hidraulica (nivel)", "m", "Mapas de carga, .hds, isopiezas del informe."],
        ["Profundidad de napa", "m", "Mapa de napa / indicador GDE."],
        ["Balance hidrico", "m3/d", "Tabla y grafico de balance (entradas/salidas)."],
        ["Caudal base rio-acuifero", "m3/d", "Seccion de balance del informe."],
        ["Descenso (con/sin proyecto)", "m", "Mapa de descenso de la prediccion."],
        ["RMSE / MAE / sesgo", "m", "Estadisticos de calibracion + criterio SEA."],
        ["Sensibilidad", "adimensional", "Cambio relativo de RMSE por parametro (OAT)."],
        ["Recarga reportada", "mm/ano", "Convertida desde m/d (x1000 x365)."],
        ["Tiempos de viaje (MODPATH)", "dias", "Zonas de captura / perimetros de proteccion."],
        ["Concentracion (transporte)", "g/m3 (o la de la fuente)", "Pluma de soluto / intrusion salina."],
    ])
    d.info_box("Conversiones utiles",
               "recarga: 1 m/d = 365000 mm/ano | caudal: 1 L/s = 86.4 m3/d | "
               "K tipica: grava 100-1000 m/d, arena 1-100, limo 0.01-1, arcilla <0.001. "
               "El caudal de bombeo va NEGATIVO (se extrae del acuifero).")

    # ---------- modulos ----------
    d.h1("Mapa de modulos: donde cambiar cada cosa")
    d.p("Cada cosa se cambia en UN lugar. Si quieres ajustar un coeficiente, un borde o un "
        "tiempo, esta tabla te dice que archivo tocar (y la unidad), sin entrar al codigo.")
    d.table(["Quiero cambiar...", "Archivo / lugar", "Campo o parametro", "Unidad"], [
        ["Conductividad K por capa", "datos/tablas/capas_modelo.csv", "kx_m_d, kz_m_d", "m/d"],
        ["Almacenamiento", "datos/tablas/capas_modelo.csv", "sy, ss", "adim, 1/m"],
        ["K por zona geologica", "datos/fuente/geologia.shp", "K_md", "m/d"],
        ["Coeficiente de infiltracion", "datos/fuente/geologia.shp", "coef_inf", "fraccion"],
        ["Recarga (total/temporal)", "datos/tablas/recarga_periodos.csv", "recharge_m_d (o yaku recarga)", "m/d"],
        ["Reparto espacial de recarga", "datos/fuente/geologia.shp -> recarga_zonas.csv", "coef_inf (lo rasteriza prep)", "fraccion"],
        ["Bordes de carga", "datos/tablas/contornos_carga.csv", "carga_m", "m"],
        ["Bombeo", "datos/tablas/caudales.csv / pozos.csv", "rate_m3_dia (negativo)", "m3/d"],
        ["Rio (nivel, conductancia, fondo)", "datos/tablas/rio.csv", "stage_m, cond_m2_d, river_bottom_m", "m, m2/d, m"],
        ["Drenes / manantiales", "datos/tablas/drn.csv (opcional)", "elev_m, cond_m2_d", "m, m2/d"],
        ["Borde regional (semi-permeable)", "datos/tablas/ghb.csv (opcional)", "head_m, cond_m2_d", "m, m2/d"],
        ["ET freatica / vegas (GDE)", "datos/tablas/evt_periodos.csv (opcional)", "rate_m_d, extinction_depth_m", "m/d, m"],
        ["Correr transiente con clima", "yaku recarga --transiente", "clima.csv diario -> stress_periods", "dias"],
        ["Indices clima-hidrogeologia", "yaku indices", "SPI/SPEI, BFI, memoria napa-clima", "-"],
        ["Geometria / espesor", "parametros_modelo.csv o yaku prep --espesor", "top, botm / --espesor", "m"],
        ["Techo siguiendo el terreno", "config.yaml", "modelo.drapear_dem: true", "-"],
        ["Tiempos / regimen", "datos/tablas/stress_periods.csv", "perlen_d, nstp, steady_state", "dias"],
        ["Celda y numero de capas", "yaku prep", "--cellsize, --nlay, --espesor", "m"],
        ["Parametros a calibrar", "datos/tablas/parametros_calibracion.csv", "valor_inicial, limites, transformacion", "-"],
        ["Solver", "config.yaml", "solver.complexity (SIMPLE/MODERATE/COMPLEX)", "-"],
        ["Perfil de informe", "config.yaml o yaku report --perfil", "informe.perfil (astm/sea)", "-"],
        ["Texto del informe", "informe/secciones.md", "bloques '## titulo'", "-"],
    ])
    d.p("Y si quieres extender el motor (programar algo nuevo), cada modulo del codigo tiene "
        "una sola responsabilidad:")
    d.table(["Modulo (src/yaku/)", "Responsabilidad"], [
        ["cli.py", "Comandos yaku (new/prep/build/run/calibrate/predict/report...)."],
        ["config.py", "Lee config.yaml y resuelve rutas del proyecto."],
        ["prep/prepare.py, prep/recarga.py", "Arma tablas desde insumos; recarga desde clima."],
        ["builder/model_builder.py", "CSV -> MODFLOW 6 (DIS/NPF/RIV/CHD/RCH/WEL), drapeado, solver."],
        ["gis/preprocess.py, gis/export.py", "Shapefile/raster -> tablas; exporta rasters de salida."],
        ["mesh/voronoi.py", "Malla Voronoi no estructurada (DISV) refinada en pozos."],
        ["calibration/ (evaluate, pest_setup, predict, sensibilidad)", "Ajuste, PEST++/pyemu, prediccion, sensibilidad, twin."],
        ["transport/ (gwt, seawater)", "Transporte de solutos e intrusion salina (densidad)."],
        ["pathlines/", "Trayectorias y zonas de captura (MODPATH 7)."],
        ["report/ (resultados, pdf, tema, docx_report, entregables)", "Informe data-driven + paquete SEIA."],
        ["viz/plots_3d.py", "Escenas 3D (litologia, rios, pozos, napa)."],
    ])

    # ---------- 7 ----------
    d.h1("Tutorial paso a paso (caso real, de principio a fin)")
    d.p("El flujo completo de un estudio, en orden. Puedes hacerlo todo desde el onboard (escribe "
        "'yaku' y sigue el siguiente paso) o con los comandos:")
    d.h2("Paso 1 - Crear el proyecto según el tipo de estudio")
    d.code('yaku new mina_X --tipo dewatering        # dewatering | intrusion | gde | general')
    d.p("El tipo orienta los objetivos y deja el perfil de informe en 'sea' (SEIA).")
    d.h2("Paso 2 - Poner los insumos y revisarlos")
    d.p("Copia tus archivos crudos a datos/fuente/, corre yaku prep (sección de preparación) y, si "
        "tienes clima, yaku recarga. Revisa que no falte nada:")
    d.code("yaku check --project proyectos/mina_X")
    d.h2("Paso 3 - (Opcional) malla multicapa y geología")
    d.code("yaku mesh --project proyectos/mina_X --run    # DISV multicapa drapeado bajo el DEM")
    d.h2("Paso 4 - Correr el modelo")
    d.code("yaku pipeline --project proyectos/mina_X       # build + run + informe")
    d.p("Construye el modelo (recortando el dominio real con idomain), corre MODFLOW 6 y genera "
        "figuras e informe. Así se ve el mapa de carga hidráulica:")
    d.image(IMG / "caso_demo_heads.png", "Figura 1. Mapa de carga hidráulica final.", 4.6)
    d.p("Y la evolucion del nivel en el tiempo (modelos transientes):")
    d.image(IMG / "caso_demo_timeseries.png", "Figura 2. Serie temporal de carga en un pozo.", 4.6)
    d.h2("Paso 5 - Calibrar, predecir y entregar")
    d.code("yaku calibrate  --project proyectos/mina_X\n"
           "yaku predict    --project proyectos/mina_X --uncertainty 30\n"
           "yaku entregables --project proyectos/mina_X --perfil sea")
    d.p("Quedas con el ajuste, los escenarios con/sin proyecto, la incertidumbre y el paquete SEIA "
        "completo listo para presentar.")

    # ---------- 8 ----------
    d.h1("Los comandos de yaku, uno por uno")
    d.table(["Comando", "Qué hace"], [
        ["yaku  (sin nada) / onboard", "Pantalla de inicio guiada: estado del proyecto + siguiente paso."],
        ["yaku doctor", "Chequea el entorno (mf6, mp7, triangle, pestpp, paquetes)."],
        ["yaku new <nombre> --tipo <t>", "Crea un proyecto (tipo: dewatering | intrusion | gde | general)."],
        ["yaku datos --project <p>", "Asistente: crea plantillas editables de las tablas que faltan."],
        ["yaku check --project <p>", "Revisa los insumos (obligatorios / importantes / opcionales)."],
        ["yaku prep --project <p>", "Datos crudos (DEM, shp, csv) -> tablas del modelo."],
        ["yaku clima --project <p> --fuente cr2|camels", "Series CR2 / CAMELS-CL -> clima.csv del proyecto."],
        ["yaku recarga --project <p>", "clima.csv (precip/ET) -> recarga por periodo (balance de suelo)."],
        ["yaku mesh --project <p>", "Malla Voronoi/DISV multicapa refinada (--run la corre)."],
        ["yaku gis --project <p>", "Shapefile/GeoJSON -> tablas row/col (avisa CRS)."],
        ["yaku build / run --project <p>", "Construye / ejecuta MODFLOW 6 (usa idomain del dominio)."],
        ["yaku calibrate --project <p>", "Ajuste + PEST++ (--run --engine pestpp-ies); --pilot-points = mapa de K; aforos.csv = multi-objetivo."],
        ["yaku sensibilidad --project <p>", "Sensibilidad de los parametros (OAT, RMSE +/-10%)."],
        ["yaku predict --project <p>", "Escenario con/sin proyecto + incertidumbre."],
        ["yaku transport / salina --project <p>", "Transporte de solutos / intrusión salina."],
        ["yaku pathlines --project <p>", "Trayectorias MODPATH 7 (zonas de captura)."],
        ["yaku view3d --project <p>", "3D a VTK: carga, litología (K), recarga, río y pozos."],
        ["yaku export-gis --project <p>", "Cargas y profundidad de napa a raster GeoTIFF (QGIS)."],
        ["yaku report --project <p>", "Informe PDF data-driven (--perfil astm | sea)."],
        ["yaku entregables --project <p>", "Paquete SEIA: informe + figuras + tablas + plan de seguimiento."],
        ["yaku pipeline --project <p>", "build + run + report, todo seguido."],
    ])
    d.info_box("Ayuda a mano", "Cualquier comando admite -h, por ejemplo 'yaku predict -h'. "
               "Escribe 'yaku' solo para abrir el onboard con el estado del proyecto.")

    # ---------- 9 ----------
    d.h1("Los dos motores: simple y profesional (GIS)")
    d.p("En config.yaml, el campo 'motor' define como se construye el modelo:")
    d.table(["motor", "Cuando usarlo"], [
        ["simple", "Casos rápidos o didacticos. Lees los datos desde los CSV de datos/tablas/."],
        ["mfsetup", "Proyectos reales. Grilla y propiedades desde datos GIS (shapefile, raster DEM) "
                    "con modflow-setup (USGS)."],
    ])

    # ---------- 10 ----------
    d.h1("Mallas Voronoi / grilla refinada (DISV)")
    d.p("Las grillas regulares gastan celdas. Una malla Voronoi refina solo donde importa "
        "(pozos, ríos), como hace gidahatari. Se genera desde el borde con:")
    d.code("yaku mesh --project proyectos/mi_proyecto --cell-size 150 --refine 5 --run")
    d.image(IMG / "malla" / "malla_voronoi.png", "Figura 3. Malla Voronoi refinada alrededor de los pozos (puntos rojos).", 4.4)
    d.p("El flag --run construye y corre un modelo MODFLOW 6 DISV sobre esa malla para verificarla:")
    d.image(IMG / "malla" / "voronoi_cargas.png", "Figura 4. Flujo resuelto sobre la malla Voronoi (DISV).", 4.2)

    # ---------- 11 ----------
    d.h1("Calibración: ¿el modelo se parece a la realidad?")
    d.p("Calibrar es ajustar parámetros (como la conductividad) para que los niveles simulados "
        "coincidan con los medidos. Tres niveles:")
    d.numbered("Evaluación de ajuste: error (RMSE, MAE) entre observado y simulado.")
    d.numbered("PEST++ GLM: ajuste automatico por gradiente + sensibilidad.")
    d.numbered("PEST++ IES (ensemble): history matching + incertidumbre.")
    d.code("yaku calibrate --project proyectos/mi_proyecto --run --engine pestpp-ies")
    d.image(IMG / "calibración" / "grafico_observado_vs_simulado.png",
            "Figura 5. Observado vs simulado; puntos sobre la línea 1:1 = ajuste perfecto.", 4.0)
    d.info_box("Criterio de aceptacion SEA",
               "La Guia SEA 2012 considera ACEPTABLE un error medio (MAE) <= 5% de la diferencia "
               "maxima de niveles observados. El informe lo evalua y marca CUMPLE / NO cumple, con "
               "el histograma y el mapa de residuos (que revela sesgos espaciales).")
    d.h2("Pilot points: un mapa de K continuo")
    d.p("La calibracion clasica ajusta una K por zona o capa. Con pilot points, PEST ajusta la "
        "conductividad en una grilla de puntos repartidos por el dominio y el campo K(x, y) se "
        "interpola entre ellos (kriging). El resultado es un mapa de K continuo y defendible "
        "(practica GMDSI), en vez de un solo numero:")
    d.code("yaku calibrate --project proyectos/mi_proyecto --pilot-points --pp-cada 5 --setup-pest")
    d.p("El campo calibrado queda en k_field_capa{N}.csv; al copiarlo a datos/tablas/, el modelo "
        "lo usa automaticamente en las corridas siguientes.")
    d.h2("Multi-objetivo: niveles + caudal del rio")
    d.p("Si tienes aforos del rio (caudal base), crea datos/tablas/aforos.csv (nombre, caudal_m3_d) "
        "y la calibracion comparara ADEMAS el intercambio rio-acuifero simulado (SFR o RIV) contra "
        "lo medido. Calibrar contra dos tipos de datos a la vez restringe mucho mejor el modelo.")
    d.p("En los ejemplos del repositorio, las observaciones se generan con un experimento gemelo "
        "(se muestrea el campo de cargas simulado y se le agrega un ruido pequeno): asi son "
        "consistentes con los bordes y la calibracion converge. Con datos reales, en cambio, las "
        "observaciones son tus niveles medidos en terreno.")

    # ---------- 12 ----------
    d.h1("Predicción y análisis de incertidumbre")
    d.p("El efecto del proyecto se evalua comparando un escenario con y sin proyecto (descenso de "
        "niveles por bombeo), y se cuantifica su incertidumbre:")
    d.code("yaku predict --project proyectos/mi_proyecto --factor 1.5 --uncertainty 30")
    d.image(IMG / "predicción" / "descenso_escenario.png",
            "Figura 6. Descenso de niveles del escenario con proyecto (con vs sin).", 4.4)
    d.image(IMG / "predicción" / "incertidumbre_montecarlo.png",
            "Figura 7. Carga media e incertidumbre (Monte Carlo sobre los rangos de calibración).", 5.4)

    # ---------- 13 ----------
    d.h1("Trayectorias y zonas de captura (MODPATH 7)")
    d.p("Con particulas reales (MODPATH 7) se obtienen las zonas de captura de los pozos y los "
        "tiempos de viaje (protección de pozos a 2/5/10 años):")
    d.code("yaku pathlines --project proyectos/mi_proyecto --direction backward")
    d.image(IMG / "trayectorias" / "trayectorias_modpath7.png",
            "Figura 8. Trayectorias hacia los pozos (zona de captura) con MODPATH 7.", 4.6)

    # ---------- 14 ----------
    d.h1("Transporte e intrusión salina")
    d.p("Para contaminantes disueltos (modelo GWT) o intrusión salina costera (GWT + BUY):")
    d.code("yaku transport --project <p>      # pluma de un soluto\nmfw salina    --project <p>      # cuña salina (densidad variable)")
    d.image(IMG / "transporte" / "concentración_final.png",
            "Figura 9. Concentración final de un soluto (modelo de transporte GWT).", 5.2)

    # ---------- 15 ----------
    d.h1("Visualización 3D (litología, ríos, pozos)")
    d.p("El modelo se exporta a VTK (se abre en ParaView, como hace gidahatari). El 3D no solo "
        "muestra la carga: lleva varios campos coloreables, todos derivados del modelo, que puedes "
        "prender/apagar:")
    d.table(["Campo", "Qué muestra"], [
        ["carga_m", "El nivel piezometrico (la napa)."],
        ["K_m_d", "La conductividad por celda = litología / permeabilidad por estrato."],
        ["recarga_m_d", "La lluvia que entra por la superficie."],
        ["río / pozos", "Las celdas de río y los pozos, como objetos marcados."],
    ])
    d.code("yaku view3d --project proyectos/mi_proyecto --exageration 20")
    d.info_box("Estratigrafia 3D asociada al modelo",
               "Con el modelo multicapa (yaku mesh --run) los estratos se ven apilados y los coloreas "
               "por litología (K) o por carga. Es la geología 3D conectada a los parámetros reales.")

    # ---------- 16 ----------
    SHOW = REPO / "docs" / "showcase" / "figuras"
    d.h1("El informe SEA: data-driven y editable")
    d.p("El informe se genera con DOS perfiles según a donde va: 'astm' (estándar internacional, "
        "7 etapas D5447/D5981) o 'sea' (contenidos mínimos SEIA, Guía SEA 2012).")
    d.code("yaku report --project proyectos/mi_proyecto --perfil sea")
    d.p("Lo importante: el informe es DATA-DRIVEN. No es una plantilla con frases vacias: escribe "
        "con tus resultados reales la calibración (RMSE, observado vs simulado, residuos), el "
        "balance hidrico (global y por capa), los escenarios de descenso, la incertidumbre y los "
        "anexos de trazabilidad (versiones + hash de los datos).")
    d.p("El informe incluye ademas: un mapa de planta del modelo conceptual (dominio, rio, pozos), "
        "la tabla de unidades geologicas con su K horizontal y coeficiente de infiltracion, la tabla "
        "de capas con K horizontal/vertical, mapas de carga con ISOPIEZAS etiquetadas en coordenadas "
        "(Este/Norte, con norte y barra de escala), y -si corriste 'yaku mesh'- la vista 3D de la malla "
        "Voronoi. Las unidades de cada tabla estan en la seccion 'Unidades de medida' de este tutorial.")
    d.h2("Rellenar lo cualitativo (informe/secciónes.md)")
    d.p("Lo que el modelo no puede escribir (modelo conceptual, antecedentes, limitaciones, "
        "conclusiones) lo pones tu en el archivo informe/secciónes.md, con encabezados '## titulo'. "
        "El informe inyecta ese texto en la sección que corresponde. Así el PDF sale 90% armado y "
        "tu solo completas lo cualitativo.")
    d.info_box("ASTM vs SEIA", "No compiten: ASTM es el método; SEIA es el formato del entregable. "
               "El motor es uno solo, el informe se adapta con --perfil.")

    # ---------- indicadores ----------
    d.h1("Indicadores para el SEA (napa/GDE, caudal base, balance)")
    d.p("El informe SEA calcula y escribe los indicadores que el evaluador suele pedir:")
    d.bullet("Profundidad de la napa y cuantas celdas tienen napa somera (<= 2.5 m), donde puede "
             "haber ecosistemas dependientes del agua subterránea (vegas, bofedales, turberas).")
    d.image(SHOW / "caso_demo_profundidad_napa.png",
            "Figura 8. Profundidad del nivel freatico (zonas someras = posible GDE).", 4.4)
    d.bullet("Descenso de niveles con y sin proyecto (efecto del proyecto).")
    d.image(SHOW / "descenso_escenario.png",
            "Figura 9. Descenso de niveles del escenario con proyecto.", 4.4)
    d.bullet("Caudal base (intercambio río-acuífero) y balance hidrico por capa / sector.")
    d.bullet("Balance por ZONAS (estilo ZoneBudget): entradas/salidas por unidad geologica o por "
             "sectores propios (zonas_balance.csv), con tabla y grafico en el informe.")
    d.bullet("Discrepancia del balance con criterio de aceptacion (<= 1%).")
    d.bullet("Mapas de carga con isopiezas etiquetadas, coordenadas y VECTORES DE FLUJO "
             "(direccion del agua subterranea), mas el mapa de recarga distribuida por unidad.")
    d.bullet("Tabla de VERIFICACION DE CALIDAD (QA): convergencia, cierre de balance, celdas secas, "
             "rango de carga y de conductividad, criterio de calibracion -cada uno OK / REVISAR.")
    d.info_box("Paquetes de borde disponibles",
               "El motor arma CHD (carga fija), GHB (borde regional semi-permeable), RIV (rios), "
               "DRN (drenes/manantiales), WEL (pozos), RCH (recarga, distribuible por unidad) y EVT "
               "(evapotranspiracion freatica, base fisica de vegas/bofedales). GHB/DRN/EVT son opcionales: "
               "se activan poniendo su archivo (ghb.csv / drn.csv / evt_periodos.csv). Para transporte: "
               "GWT (solutos) y BUY (intrusion salina).")

    # ---------- entregables ----------
    d.h1("El paquete de entregables SEIA")
    d.p("Un solo comando arma la carpeta lista para presentar al SEIA:")
    d.code("yaku entregables --project proyectos/mi_proyecto --perfil sea")
    d.p("Crea informe/entregables_seia/ con todo ordenado:")
    d.table(["Contenido", "Que es"], [
        ["informe_<perfil>.pdf", "El informe data-driven completo."],
        ["figuras/", "Todas las figuras de resultados (napa, descenso, calibración, carga por capa)."],
        ["tablas/", "metricas de ajuste, balance, parámetros, residuos."],
        ["modelo/", "Los archivos de entrada de MODFLOW 6 + metadatos (anexo de trazabilidad)."],
        ["plan_seguimiento.csv", "Plan de seguimiento con umbrales reales (descenso predicho por pozo)."],
        ["MANIFIESTO.md", "Indice del paquete + versiones + hash de las entradas."],
    ])
    d.info_box("Showcase",
               "En docs/showcase/ hay un ejemplo real de este informe SEA y su paquete, para ver de "
               "que es capaz el workflow sin correr nada.")

    # ---------- 17 ----------
    d.h1("Cómo lo usa otra persona del equipo")
    d.numbered("Instala una vez el entorno y corre yaku doctor (sección 4).")
    d.numbered("Escribe 'yaku' para abrir el onboard y crear su proyecto (elige el tipo de estudio).")
    d.numbered("Pone sus archivos crudos en datos/fuente/ y corre yaku prep (y yaku recarga si hay clima).")
    d.numbered("Corre yaku check para ver que no falte nada; el onboard le sugiere el siguiente paso.")
    d.numbered("Corre yaku pipeline, luego calibrate/predict, y genera el paquete con yaku entregables.")
    d.info_box("Buena práctica", "Versiona cada proyecto con git (config.yaml + datos/ + informe/secciónes.md). "
               "El archivo resultados/inputs_metadata.json guarda versiones y un hash de los datos usados. "
               "Para clavar versiones identicas en otra máquina, usa environment-lock.yml.")

    # ---------- 18 ----------
    d.h1("Si algo falla (problemas comunes)")
    d.table(["Síntoma", "Solución"], [
        ["'yaku' no se reconoce", "Activa el entorno: conda activate modflow-workflow."],
        ["No encuentra config.yaml", "Indica el proyecto: --project proyectos/<tu_proyecto>."],
        ["'No existe HDS'", "Corre primero yaku run (o yaku pipeline)."],
        ["'Faltan tablas minimas'", "Te falta un insumo obligatorio. Corre yaku check para ver cual."],
        ["mp7 / triangle FALTA", "Instala binarios: get-modflow :flopy. Verifica con yaku doctor."],
        ["El modelo no converge", "Revisa bordes y geometria de capas; baja la complejidad del solver."],
        ["Advertencia de unidades", "Un valor parece fuera de rango (ej. K en m/s). Usa m/dia."],
    ])

    # ---------- 19 ----------
    d.h1("Glosario rápido")
    d.table(["Palabra", "Definición"], [
        ["ASTM D5447/D5981", "Normas internacionales del proceso de modelación y calibración."],
        ["SEIA / SEA", "Sistema/Servicio de Evaluación de Impacto Ambiental (Chile)."],
        ["PEST++ / pyemu", "Herramientas de calibración automática e incertidumbre."],
        ["DISV / Voronoi", "Grilla no estructurada de celdas irregulares (refinamiento local)."],
        ["MODPATH 7", "Seguimiento de particulas: zonas de captura y tiempos de viaje."],
        ["GWT / BUY", "Transporte de solutos / densidad variable (intrusión salina)."],
        ["Pipeline", "Secuencia automática: construir -> correr -> reportar."],
    ])

    return d.save(out_docx)


if __name__ == "__main__":
    salida = REPO / "docs" / "_build" / "Tutorial_yaku.docx"
    salida.parent.mkdir(parents=True, exist_ok=True)
    docx = build(salida)
    print(f"DOCX: {docx}")
    try:
        pdf = docx_to_pdf(docx)
        print(f"PDF: {pdf}")
    except Exception as exc:
        print(f"PDF no generado: {exc}")
