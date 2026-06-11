#!/usr/bin/env python3
"""Genera un informe PDF (o Markdown de respaldo) desde un archivo HDS.

Migrado desde 06_informe_pdf/generar_informe.py. La firma se limpio para no
depender de un argparse.Namespace ni de rutas del workflow antiguo. La capa de
perfiles de informe (astm | sea) se incorpora en la Fase 7; por ahora produce el
informe base (equivalente al perfil 'astm' minimo).
"""

from __future__ import annotations

import logging
import tempfile
import unicodedata
from datetime import datetime
from pathlib import Path

import flopy
import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import Image as RLImage
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table

    from yaku.report import tema

    HAS_REPORTLAB = True
except Exception:  # pragma: no cover - depende del entorno
    HAS_REPORTLAB = False
    inch = 72  # 1 pulgada = 72 pt (fallback para defaults de funcion)


logger = logging.getLogger("yaku")


# Estructura del informe segun perfil. Cada item es (titulo, texto_guia).
# El bloque de estadisticos + figura se inserta en la seccion marcada con insert_figura.
PERFILES: dict[str, dict] = {
    "astm": {
        "subtitulo": "Estructura según protocolo ASTM D5447 / D5981",
        "insert_figura": "3. Diseño del modelo numérico",
        "secciones": [
            ("1. Propósito y objetivos", "Objetivo del modelo, tipo (steady/transiente) y escala (local/regional)."),
            ("2. Modelo conceptual", "Marco hidrogeológico, capas, condiciones de borde y balance conceptual."),
            ("3. Diseño del modelo numérico", "Discretización espacial/temporal, paquetes MODFLOW 6 y parámetros."),
            ("4. Calibración (D5981)", "Comparación observado vs simulado, RMSE/MAE y parámetros calibrados."),
            ("5. Análisis de sensibilidad", "Parámetros más influyentes sobre las predicciones."),
            ("6. Predicción e incertidumbre", "Escenarios de predicción y bandas de incertidumbre (ensemble)."),
            ("7. Conclusiones", "Síntesis de resultados, limitaciones y recomendaciones."),
        ],
    },
    "sea": {
        "subtitulo": "Contenidos mínimos - Guía SEA 2012 + criterios recurso hídrico SEA 2022",
        "insert_figura": "5. Construcción del modelo numérico",
        "secciones": [
            ("1. Introducción y objetivos", "Objetivos del modelo en el contexto del proyecto y del SEIA."),
            ("2. Marco normativo", "Normativa e instrumentos aplicables a la modelación y al recurso hídrico."),
            ("3. Antecedentes y área de estudio", "Ubicación, contexto hidrogeológico regional y antecedentes."),
            ("4. Modelo conceptual", "Unidades hidrogeológicas, recarga/descarga, niveles y balance hídrico conceptual."),
            ("5. Construcción del modelo numérico", "Código (MODFLOW 6), dominio, discretización espacial y temporal, "
             "condiciones de borde y parámetros hidráulicos."),
            ("6. Calibración y validación", "Calibración en estado estacionario y transiente; estadísticos de ajuste "
             "(RMSE, MAE, sesgo), mapas e histograma de residuos y validación del modelo."),
            ("7. Análisis de sensibilidad", "Identificación de los parámetros más influyentes sobre los resultados."),
            ("8. Balance hídrico del modelo", "Entradas y salidas simuladas (recarga, bombeo, ríos, almacenamiento) "
             "y cierre del balance por zonas."),
            ("9. Simulaciones predictivas (escenarios)", "Escenarios con y sin proyecto; efectos sobre niveles, caudales "
             "y ecosistemas asociados."),
            ("10. Análisis de incertidumbre", "Cuantificación de incertidumbre de las predicciones (ensemble PEST++-IES)."),
            ("11. Limitaciones del modelo", "Supuestos, vacíos de información y alcance/validez de las predicciones."),
            ("12. Plan de seguimiento de variables ambientales", "Variables, puntos y frecuencia de monitoreo "
             "asociados al modelo, para verificar las predicciones en el tiempo."),
            ("13. Conclusiones", "Síntesis de resultados y recomendaciones."),
            ("14. Glosario", "Definición de los términos técnicos utilizados en el informe."),
            ("15. Anexos", "Archivos de entrada/salida del modelo, metadatos de versiones y trazabilidad "
             "(resultados/inputs_metadata.json)."),
        ],
    },
}


# Contenido institucional de las secciones SEA "Marco normativo" y "Glosario".
MARCO_NORMATIVO: list[tuple[str, str]] = [
    ("Ley N° 19.300", "Bases Generales del Medio Ambiente; art. 11 define los criterios de "
     "significancia de impactos evaluados en el SEIA."),
    ("DL N° 1.122 (Código de Aguas)", "Define los derechos de aprovechamiento y el régimen de "
     "las aguas subterráneas; base para el análisis de derechos y caudales comprometidos."),
    ("Ley N° 20.936 y normas DGA", "Áreas de restricción y zonas de prohibición de extracción."),
    ("Guía SEA 2012", "\"Guía para el uso de modelos de aguas subterráneas en el SEIA\"; "
     "contenidos mínimos, criterios de calibración (MAE ≤ 5 % de la diferencia máxima observada) "
     "y de cierre de balance (error < 1 % al final de cada período de stress)."),
    ("Criterios recurso hídrico SEA 2022", "Criterios para evaluar impactos sobre la cantidad y "
     "calidad del recurso hídrico subterráneo y ecosistemas dependientes (GDE)."),
]

GLOSARIO: list[tuple[str, str]] = [
    ("Acuífero", "Formación geológica permeable capaz de almacenar y ceder agua."),
    ("Acuitardo", "Unidad que almacena agua pero la transmite con dificultad (baja conductividad)."),
    ("Calibración", "Ajuste de parámetros para que las cargas simuladas reproduzcan las observadas."),
    ("Conductividad hidráulica (K)", "Capacidad del medio poroso para transmitir agua (m/d)."),
    ("Condición de borde", "Representación matemática del flujo o la carga en los límites del modelo."),
    ("GDE", "Ecosistema dependiente del agua subterránea (vegas, bofedales, turberas)."),
    ("MAE / RMSE", "Error medio absoluto / raíz del error cuadrático medio de la calibración (m)."),
    ("Período de stress", "Intervalo en que las tensiones del sistema (recarga, bombeo) se mantienen constantes."),
    ("Régimen permanente / transiente", "Equilibrio sin cambios en el tiempo / evolución temporal de niveles."),
]


def load_heads(hds_path: Path) -> tuple[np.ndarray, list[float]]:
    """Carga la carga hidraulica final y la lista de tiempos desde un .hds."""
    hds = flopy.utils.HeadFile(str(hds_path), precision="double")
    times = hds.get_times()
    if times:
        return hds.get_data(totim=times[-1]), times
    return hds.get_data(), []


def build_figure(head: np.ndarray, figure_path: Path) -> None:
    figure_path.parent.mkdir(parents=True, exist_ok=True)
    fig, axis = plt.subplots(figsize=(7, 5))
    image = axis.imshow(head[0, :, :], origin="lower", cmap="viridis")
    axis.set_title("Mapa de carga hidraulica")
    axis.set_xlabel("col")
    axis.set_ylabel("row")
    fig.colorbar(image, ax=axis, label="m")
    fig.tight_layout()
    fig.savefig(figure_path, dpi=200, bbox_inches="tight")
    plt.close(fig)


def write_markdown(
    output_path: Path,
    head: np.ndarray,
    times: list[float],
    *,
    titulo: str,
    autor: str,
    perfil: str = "astm",
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    spec = PERFILES.get(perfil, PERFILES["astm"])
    lines = [
        f"# {titulo}",
        "",
        f"_{spec['subtitulo']}_",
        "",
        f"- Autor: {autor}",
        f"- Fecha: {datetime.now().strftime('%Y-%m-%d')}",
        f"- Tiempos simulados: {len(times)}",
        "",
    ]
    estadisticos = [
        "**Estadisticos del modelo:**",
        f"- Capas: {head.shape[0]} | Filas: {head.shape[1]} | Columnas: {head.shape[2]}",
        f"- Carga minima: {head.min():.2f} m | maxima: {head.max():.2f} m | media: {head.mean():.2f} m",
        f"- Desviacion estandar: {head.std():.2f} m",
    ]
    for titulo_sec, guia in spec["secciones"]:
        lines.append(f"## {titulo_sec}")
        lines.append("")
        lines.append(guia)
        if titulo_sec == spec["insert_figura"]:
            lines.append("")
            lines.extend(estadisticos)
        lines.append("")
    output_path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Helpers para el informe data-driven (cada seccion escribe contenido real)
# ---------------------------------------------------------------------------
def _norm(texto: str) -> str:
    """minúsculas sin acentos, para identificar secciones por palabra clave."""
    base = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in base if unicodedata.category(c) != "Mn")


def _fmt(v) -> str:
    if isinstance(v, float):
        return f"{v:.4g}"
    return str(v)


_ANCHO_UTIL = 6.8 * inch   # A4 menos márgenes (54+54 pt)


def _celda(valor, *, header=False):
    """Envuelve el contenido de una celda en Paragraph para que el texto haga wrap."""
    estilo = ParagraphStyle(
        "celda_h" if header else "celda",
        fontName="Helvetica-Bold" if header else "Helvetica",
        fontSize=8, leading=9.5,
        textColor=colors.white if header else colors.HexColor("#212121"),
    )
    return Paragraph(str(valor), estilo)


def _tabla_rl(data: list[list], col_widths=None):
    """Tabla reportlab (tema azul) con celdas que envuelven texto y caben en la página."""
    ncol = len(data[0]) if data else 1
    if col_widths is None:
        col_widths = [_ANCHO_UTIL / ncol] * ncol
    else:
        total = sum(col_widths)
        if total > _ANCHO_UTIL:   # reescala si excede el ancho útil
            col_widths = [w * _ANCHO_UTIL / total for w in col_widths]
    cuerpo = [[_celda(v, header=(i == 0)) for v in fila] for i, fila in enumerate(data)]
    t = Table(cuerpo, colWidths=col_widths, repeatRows=1)
    t.setStyle(tema.estilo_tabla())
    return t


def _df_tabla(df, max_rows: int = 14, col_widths=None):
    data = [list(df.columns)]
    for fila in df.head(max_rows).itertuples(index=False):
        data.append([_fmt(v) for v in fila])
    return _tabla_rl(data, col_widths)


_ETIQUETAS_CAPAS = {
    "layer": "Capa", "top_m": "Techo (m)", "botm_m": "Base (m)",
    "kx_m_d": "K horizontal (m/d)", "kz_m_d": "K vertical (m/d)",
    "sy": "Sy (rend. esp.)", "ss": "Ss (1/m)", "iconvert": "Tipo",
    "unidad": "Unidad hidrogeológica",
}
_ETIQUETAS_GEOLOGIA = {
    "unidad": "Unidad geológica", "K_md": "K horizontal (m/d)", "k_md": "K horizontal (m/d)",
    "coef_inf": "Coef. de infiltración", "coef_escorrentia": "Coef. de escorrentía",
}


def _tabla_capas(df, **kw):
    """Tabla de capas con encabezados legibles (K horizontal/vertical, etc.) y tipo libre/confinado."""
    d = df.copy()
    if "iconvert" in d.columns:
        d["iconvert"] = d["iconvert"].map(
            lambda v: "libre" if str(v).strip() in ("1", "1.0") else "confinado")
    d = d.rename(columns={k: v for k, v in _ETIQUETAS_CAPAS.items() if k in d.columns})
    return _df_tabla(d, **kw)


def _tabla_geologia(df, **kw):
    """Tabla de unidades geológicas (K horizontal y coef. de infiltración) con encabezados legibles."""
    d = df.rename(columns={k: v for k, v in _ETIQUETAS_GEOLOGIA.items() if k in df.columns})
    return _df_tabla(d, **kw)


def _imagen(path: Path, styles, ancho: float = 5.4 * inch, titulo: str | None = None):
    flowables = []
    if titulo:
        flowables.append(Paragraph(titulo, styles["Heading4"]))
    flowables.append(RLImage(str(path), width=ancho, height=ancho * 0.72))
    return flowables


def leer_secciones_md(path: Path) -> dict[str, str]:
    """Lee informe/secciones.md (encabezados '## <titulo>') -> {titulo_normalizado: texto}.

    Permite al consultor escribir el contenido cualitativo (modelo conceptual, limitaciones,
    conclusiones, antecedentes, GDE...) y que el informe lo inyecte en la seccion que matchea.
    """
    path = Path(path)
    if not path.exists():
        return {}
    secciones: dict[str, str] = {}
    clave = None
    buffer: list[str] = []
    en_comentario = False
    for linea in path.read_text(encoding="utf-8").splitlines():
        # Ignorar comentarios HTML (<!-- ejemplo -->): guían al consultor sin filtrarse al informe.
        if en_comentario:
            if "-->" in linea:
                en_comentario = False
            continue
        desnuda = linea.strip()
        if desnuda.startswith("<!--"):
            if "-->" not in desnuda:
                en_comentario = True
            continue
        if linea.startswith("## "):
            if clave is not None:
                secciones[clave] = "\n".join(buffer).strip()
            clave = _norm(linea[3:].strip())
            buffer = []
        elif clave is not None:
            buffer.append(linea)
    if clave is not None:
        secciones[clave] = "\n".join(buffer).strip()
    return {k: v for k, v in secciones.items() if v}


def _texto_usuario(textos: dict | None, norm_titulo: str) -> str | None:
    """Devuelve el texto del consultor cuya clave matchea la seccion, si existe."""
    if not textos:
        return None
    for clave, texto in textos.items():
        if clave and (clave in norm_titulo or norm_titulo in clave):
            return texto
    return None


def _parrafos(texto: str, styles) -> list:
    """Convierte texto (parrafos separados por linea en blanco) en flowables."""
    bloques = [b.strip() for b in texto.split("\n\n") if b.strip()]
    out = []
    for b in bloques:
        out.append(Paragraph(b.replace("\n", " "), styles["BodyText"]))
        out.append(Spacer(1, 0.05 * inch))
    return out


def _bloques_seccion(titulo_sec: str, res, styles, guia: str, textos: dict | None = None) -> list:
    """Devuelve los flowables de una seccion: texto del consultor o guia + datos reales."""
    n = _norm(titulo_sec)
    # Texto editable del consultor (informe/secciones.md) o, si no hay, la frase guia.
    user = _texto_usuario(textos, n)
    if user:
        out = _parrafos(user, styles)
        out.append(Spacer(1, 0.04 * inch))
    else:
        out = [Paragraph(guia, styles["BodyText"]), Spacer(1, 0.06 * inch)]

    def aviso(txt):
        out.append(Paragraph(f"<i>{txt}</i>", styles["BodyText"]))

    if "conceptual" in n:
        if res.mapa_conceptual:
            out.append(Spacer(1, 0.08 * inch))
            out.extend(_imagen(res.mapa_conceptual, styles,
                               titulo="Planta del modelo conceptual: dominio activo, río y red de "
                                      "pozos de bombeo y de observación (fondo de color = conductividad K "
                                      "cuando varía en planta)"))
        if res.unidades_geologicas is not None and not res.unidades_geologicas.empty:
            out.append(Spacer(1, 0.08 * inch))
            out.append(Paragraph("Unidades geológicas: conductividad e infiltración", styles["Heading4"]))
            out.append(Paragraph(
                "Zonificación hidrogeológica en planta. La conductividad K horizontal gobierna el "
                "flujo lateral y el coeficiente de infiltración, la fracción de la precipitación que "
                "recarga el acuífero en cada unidad.", styles["BodyText"]))
            out.append(_tabla_geologia(res.unidades_geologicas))
        if res.parametros and res.parametros.get("capas") is not None:
            out.append(Spacer(1, 0.08 * inch))
            out.append(Paragraph("Estratificación vertical (capas del modelo)", styles["Heading4"]))
            out.append(_tabla_capas(res.parametros["capas"]))

    elif "calibrac" in n or "validacion" in n:
        cal = res.calibracion
        if cal:
            out.append(Paragraph("Estadísticos de ajuste", styles["Heading4"]))
            out.append(_df_tabla(cal["metricas"], col_widths=[2.7 * inch, 2.5 * inch]))
            # Criterio cuantitativo Guía SEA 2012 (3.4.2): MAE <= 5 % de la dif. máxima observada.
            crit = res.criterio_calibracion
            if crit and crit.get("cumple") is not None:
                ok = crit["cumple"]
                estado = "CUMPLE" if ok else "NO cumple"
                color = "#2E7D32" if ok else "#C62828"
                out.append(Paragraph(
                    f'Criterio SEA: MAE = {crit["mae_m"]:.2f} m frente al umbral aceptable de '
                    f'{crit["umbral_aceptable_m"]:.2f} m (5 % de la diferencia máxima observada, '
                    f'{crit["dif_max_obs_m"]:.1f} m) — <font color="{color}">{estado}</font>. '
                    f'RMSE = {crit["rmse_m"]:.2f} m, sesgo = {crit["sesgo_m"]:.2f} m.',
                    styles["BodyText"]))
            if cal.get("scatter"):
                out.append(Spacer(1, 0.1 * inch))
                out.extend(_imagen(cal["scatter"], styles, titulo="Observado vs simulado"))
            if res.residuos_figs and res.residuos_figs.get("histograma"):
                out.append(Spacer(1, 0.1 * inch))
                out.extend(_imagen(res.residuos_figs["histograma"], styles,
                                   titulo="Histograma de residuos (idealmente simétrico y centrado en cero)"))
            if res.residuos_figs and res.residuos_figs.get("mapa"):
                out.append(Spacer(1, 0.1 * inch))
                out.extend(_imagen(res.residuos_figs["mapa"], styles,
                                   titulo="Distribución espacial de residuos"))
            if res.series_tiempo:
                out.append(Spacer(1, 0.1 * inch))
                out.extend(_imagen(res.series_tiempo, styles,
                                   titulo="Series de tiempo de carga simulada por pozo"))
            if cal.get("residuos") is not None:
                out.append(Spacer(1, 0.1 * inch))
                out.append(Paragraph("Residuos por observación", styles["Heading4"]))
                out.append(_df_tabla(cal["residuos"]))
        else:
            aviso("Aún no hay resultados de calibración en el proyecto.")

    elif "balance" in n:
        bal = res.balance
        if bal:
            out.append(Paragraph("Balance hídrico simulado (m³/día)", styles["Heading4"]))
            out.append(_df_tabla(bal["df"]))
            if res.balance_barras:
                out.append(Spacer(1, 0.08 * inch))
                out.extend(_imagen(res.balance_barras, styles,
                                   titulo="Entradas y salidas por componente"))
            disc = bal.get("discrepancia_pct")
            if disc is not None:
                # Criterio ASTM/USGS: |discrepancia| <= 1 % para aceptar el balance.
                ok = abs(disc) <= 1.0
                estado = "dentro del criterio (≤ 1 %)" if ok else "FUERA del criterio (> 1 %): revisar el modelo"
                color = "#2E7D32" if ok else "#C62828"
                out.append(Paragraph(
                    f'Discrepancia del balance: <font color="{color}">{disc:.3g} % — {estado}</font>.',
                    styles["BodyText"]))
            if res.caudal_base:
                cb = res.caudal_base
                out.append(Spacer(1, 0.06 * inch))
                out.append(Paragraph(
                    f"Intercambio río–acuífero: río→acuífero {cb['rio_a_acuifero_m3d']:.1f} m³/d, "
                    f"acuífero→río (caudal base) {cb['acuifero_a_rio_m3d']:.1f} m³/d "
                    f"(neto {cb['neto_m3d']:.1f} m³/d).", styles["BodyText"]))
            if res.balance_por_capa is not None:
                out.append(Spacer(1, 0.08 * inch))
                out.append(Paragraph("Balance por capa / sector (m³/día)", styles["Heading4"]))
                out.append(_df_tabla(res.balance_por_capa, max_rows=30))
            bz = getattr(res, "balance_por_zonas", None)
            if bz and bz.get("df") is not None:
                out.append(Spacer(1, 0.08 * inch))
                out.append(Paragraph("Balance por zonas (m³/día)", styles["Heading4"]))
                out.append(Paragraph(
                    "Fuentes y sumideros por zona del acuífero (unidades geológicas o sectores "
                    "definidos en zonas_balance.csv), estilo ZoneBudget. No incluye el "
                    "intercambio lateral entre zonas.", styles["BodyText"]))
                out.append(_df_tabla(bz["df"], max_rows=40))
                if bz.get("figura"):
                    out.extend(_imagen(bz["figura"], styles,
                                       titulo="Entradas y salidas por zona y componente"))
            ic = res.indices_clima
            if ic and ic.get("tabla") is not None and not ic["tabla"].empty:
                out.append(Spacer(1, 0.12 * inch))
                out.append(Paragraph("Índices clima–hidrogeología", styles["Heading4"]))
                out.append(Paragraph(
                    "Indicadores que correlacionan el clima con la respuesta del acuífero: sequía "
                    "(SPI/SPEI), aridez, fracción de la lluvia que recarga, flujo base del río "
                    "sostenido por el acuífero (BFI) y la memoria del acuífero (desfase napa–clima).",
                    styles["BodyText"]))
                out.append(_df_tabla(ic["tabla"], max_rows=12))
                figs = ic.get("figuras") or {}
                if figs.get("respuesta"):
                    out.append(Spacer(1, 0.08 * inch))
                    out.extend(_imagen(figs["respuesta"], styles,
                                       titulo="Respuesta napa–clima: la recarga (barras) y el nivel "
                                              "medio (línea); la napa cae en los años secos y se recupera"))
                if figs.get("flujo_base"):
                    out.append(Spacer(1, 0.08 * inch))
                    out.extend(_imagen(figs["flujo_base"], styles,
                                       titulo="Separación de flujo base del caudal medido (valida la recarga)"))
                if figs.get("spi"):
                    out.append(Spacer(1, 0.08 * inch))
                    out.extend(_imagen(figs["spi"], styles, titulo="Índice de sequía meteorológica (SPI)"))
        else:
            aviso("Sin balance disponible (requiere el .lst de una corrida).")

    elif "construc" in n or "diseno" in n:
        par = res.parametros
        if par and par.get("globales") is not None:
            out.append(Paragraph("Parámetros del modelo", styles["Heading4"]))
            out.append(_df_tabla(par["globales"], col_widths=[2.7 * inch, 2.5 * inch]))
        if par and par.get("capas") is not None:
            out.append(Spacer(1, 0.08 * inch))
            out.append(Paragraph("Capas hidrogeológicas (conductividad y almacenamiento)", styles["Heading4"]))
            out.append(_tabla_capas(par["capas"]))
        if res.recarga and res.recarga.get("total_mm"):
            out.append(Paragraph(
                f"Recarga media aplicada: {res.recarga['total_mm']:.0f} mm/año "
                f"(desde recarga_periodos.csv, balance de suelo precipitación–evapotranspiración).",
                styles["BodyText"]))
        if res.recarga_mapa:
            out.append(Spacer(1, 0.06 * inch))
            out.extend(_imagen(res.recarga_mapa, styles,
                               titulo="Recarga distribuida por unidad geológica (coeficiente de "
                                      "infiltración): las zonas más permeables reciben más recarga"))
        if res.stats_por_capa:
            out.append(Spacer(1, 0.08 * inch))
            out.append(Paragraph("Carga simulada por capa", styles["Heading4"]))
            data = [["capa", "min (m)", "max (m)", "media (m)", "desv (m)"]]
            for s in res.stats_por_capa:
                data.append([s["capa"], _fmt(s["min_m"]), _fmt(s["max_m"]),
                             _fmt(s["media_m"]), _fmt(s["desv_m"])])
            out.append(_tabla_rl(data))
        for png in res.mapas_carga:
            out.append(Spacer(1, 0.1 * inch))
            out.extend(_imagen(png, styles))
        if res.napa:
            s = res.napa["stats"]
            out.append(Spacer(1, 0.1 * inch))
            out.append(Paragraph("Profundidad del nivel freático", styles["Heading4"]))
            out.append(Paragraph(
                f"Napa entre {s['min_m']:.1f} y {s['max_m']:.1f} m (media {s['media_m']:.1f} m). "
                f"{s['celdas_someras']} celdas ({100 * s['frac_someras']:.0f} %) con napa somera "
                f"(≤ {s['umbral_m']:.1f} m), potencial presencia de ecosistemas dependientes (GDE).",
                styles["BodyText"]))
            out.extend(_imagen(res.napa["png"], styles))
        if res.napa_animacion:
            out.append(Paragraph(
                "Se incluye además una animación de la evolución temporal del nivel freático "
                f"(régimen transiente) en los entregables: <i>{res.napa_animacion.name}</i>.",
                styles["BodyText"]))
        if res.seccion_vertical:
            out.append(Spacer(1, 0.1 * inch))
            out.extend(_imagen(res.seccion_vertical, styles, titulo="Sección vertical (estratos y carga)"))
        if res.malla_voronoi or res.malla_3d:
            out.append(Spacer(1, 0.1 * inch))
            out.append(Paragraph("Discretización alternativa: malla Voronoi (DISV)", styles["Heading4"]))
            out.append(Paragraph(
                "Como verificación de la discretización se generó además una malla Voronoi no "
                "estructurada, refinada en torno a los pozos, y su modelo de flujo equivalente (DISV).",
                styles["BodyText"]))
            if res.malla_voronoi:
                out.append(Spacer(1, 0.06 * inch))
                out.extend(_imagen(res.malla_voronoi, styles, titulo="Malla Voronoi en planta (refinada en los pozos)"))
            if res.malla_3d:
                out.append(Spacer(1, 0.06 * inch))
                out.extend(_imagen(res.malla_3d, styles,
                                   titulo="Vista 3D de la malla Voronoi (bloque coloreado por carga hidráulica)"))

    elif "sensibilidad" in n:
        if res.sensibilidad is not None and not res.sensibilidad.empty:
            out.append(Paragraph("Sensibilidad de los parámetros (OAT, ±10%)", styles["Heading4"]))
            out.append(_df_tabla(res.sensibilidad))
            top = res.sensibilidad.iloc[0]
            out.append(Paragraph(
                f"El parámetro más influyente es <b>{top['parametro']}</b> "
                f"(sensibilidad {top['sensibilidad']}).", styles["BodyText"]))
        else:
            aviso("Aún no se ha incorporado el análisis de sensibilidad en el proyecto.")

    elif "predict" in n or "escenario" in n or "simulaciones" in n:
        pred = res.prediccion
        if pred and (pred.get("descenso") is not None or pred.get("descenso_png")):
            if pred.get("descenso") is not None:
                out.append(Paragraph("Resumen del escenario (descenso)", styles["Heading4"]))
                out.append(_df_tabla(pred["descenso"]))
            if pred.get("descenso_png"):
                out.extend(_imagen(pred["descenso_png"], styles))
        else:
            aviso("Aún no se han incorporado escenarios de predicción en el proyecto.")
        # Afeccion a ecosistemas dependientes del agua subterranea (GDE)
        if res.napa:
            s = res.napa["stats"]
            out.append(Spacer(1, 0.08 * inch))
            out.append(Paragraph("Afección a ecosistemas dependientes (GDE)", styles["Heading4"]))
            out.append(Paragraph(
                f"{s['celdas_someras']} celdas ({100 * s['frac_someras']:.0f} %) con napa somera "
                f"(≤ {s['umbral_m']:.1f} m), donde pueden existir vegas, bofedales o turberas "
                f"sensibles a descensos del nivel freático. Verificar afección de los escenarios "
                f"sobre estas zonas.", styles["BodyText"]))

    elif "incertidumbre" in n:
        pred = res.prediccion
        if pred and (pred.get("incertidumbre") is not None or pred.get("incert_png")):
            if pred.get("incertidumbre") is not None:
                out.append(Paragraph("Resumen de incertidumbre (Monte Carlo)", styles["Heading4"]))
                out.append(_df_tabla(pred["incertidumbre"]))
            if pred.get("incert_png"):
                out.extend(_imagen(pred["incert_png"], styles))
        else:
            aviso("Aún no se ha incorporado el análisis de incertidumbre en el proyecto.")

    elif "anexo" in n:
        if res.qa is not None and not res.qa.empty:
            out.append(Paragraph("Verificación de calidad del modelo (QA)", styles["Heading4"]))
            out.append(Paragraph(
                "Chequeos automáticos de credibilidad del modelo (convergencia, cierre de balance, "
                "celdas secas, rangos de carga y de conductividad, calibración).", styles["BodyText"]))
            out.append(_df_tabla(res.qa, max_rows=20))
            out.append(Spacer(1, 0.1 * inch))
        tz = res.trazabilidad
        if tz:
            out.append(Paragraph("Trazabilidad y versiones", styles["Heading4"]))
            data = [["Campo", "Valor"]]
            for k in ("generado", "modelo", "motor", "hash_entradas_sha256"):
                if k in tz and tz[k]:
                    data.append([k, str(tz[k])[:60]])
            for lib, ver in (tz.get("versiones") or {}).items():
                data.append([f"version {lib}", str(ver)])
            out.append(_tabla_rl(data, col_widths=[2.7 * inch, 3.2 * inch]))
        else:
            aviso("Trazabilidad en resultados/inputs_metadata.json (se genera al correr).")

    elif "seguimiento" in n:
        # Plan de Seguimiento de Variables Ambientales (PSVA) embebido en el informe.
        umbral = None
        pred = res.prediccion
        if pred and pred.get("descenso") is not None:
            df = pred["descenso"]
            col = next((c for c in df.columns if "descenso" in c.lower() and "max" in c.lower()), None)
            col = col or next((c for c in df.columns if "descenso" in c.lower()), None)
            if col is not None and len(df):
                umbral = float(df[col].abs().max())
        out.append(Paragraph("Variables, puntos y criterios de seguimiento", styles["Heading4"]))
        u = f"{umbral:.2f} m (descenso máximo predicho)" if umbral is not None else "a definir según predicción"
        data = [
            ["Variable", "Punto de control", "Frecuencia", "Umbral de alerta"],
            ["Nivel freático", "Red de piezómetros de observación", "Mensual", u],
            ["Caudal base río–acuífero", "Tramo modelado del río", "Mensual",
             "Caudal base simulado de referencia"],
        ]
        out.append(_tabla_rl(data, col_widths=[1.5 * inch, 2.2 * inch, 1.0 * inch, 2.1 * inch]))
        out.append(Paragraph(
            "La localización de los puntos debe priorizar la ruta fuente–receptor y las zonas de "
            "mayor gradiente; la frecuencia se ajusta a la velocidad de respuesta del sistema "
            "(Guía SEA 2012, cap. 6). El detalle se entrega en plan_seguimiento.csv.", styles["BodyText"]))

    elif "marco normativo" in n:
        out.append(Paragraph("Normativa e instrumentos aplicables", styles["Heading4"]))
        data = [["Instrumento", "Alcance"]]
        for norma, desc in MARCO_NORMATIVO:
            data.append([norma, desc])
        out.append(_tabla_rl(data, col_widths=[1.9 * inch, 3.7 * inch]))

    elif "glosario" in n:
        out.append(Paragraph("Términos técnicos", styles["Heading4"]))
        data = [["Término", "Definición"]]
        for termino, desc in GLOSARIO:
            data.append([termino, desc])
        out.append(_tabla_rl(data, col_widths=[1.9 * inch, 3.7 * inch]))

    elif "conclusion" in n:
        # Conclusiones data-driven: RMSE de calibración + descenso máximo predicho.
        bullets = []
        crit = res.criterio_calibracion
        if crit:
            estado = ("cumple el criterio SEA" if crit.get("cumple")
                      else "no cumple el criterio SEA" if crit.get("cumple") is not None else "evaluado")
            bullets.append(
                f"La calibración alcanza un RMSE de {crit['rmse_m']:.2f} m y un MAE de "
                f"{crit['mae_m']:.2f} m ({estado}; umbral {crit['umbral_aceptable_m']:.2f} m).")
        if res.balance and res.balance.get("discrepancia_pct") is not None:
            disc = res.balance["discrepancia_pct"]
            bullets.append(f"El balance hídrico cierra con una discrepancia de {disc:.3g} % "
                           f"({'aceptable' if abs(disc) <= 1 else 'a revisar'}, criterio < 1 %).")
        if res.prediccion and res.prediccion.get("descenso") is not None:
            df = res.prediccion["descenso"]
            col = next((c for c in df.columns if "descenso" in c.lower()), None)
            if col is not None and len(df):
                bullets.append(f"El descenso máximo predicho en los escenarios evaluados es de "
                               f"{float(df[col].abs().max()):.2f} m.")
        if res.napa:
            s = res.napa["stats"]
            bullets.append(f"{s['celdas_someras']} celdas presentan napa somera (≤ {s['umbral_m']:.1f} m), "
                           f"relevantes para la evaluación de ecosistemas dependientes (GDE).")
        if bullets:
            out.append(Paragraph("Síntesis cuantitativa de resultados", styles["Heading4"]))
            for b in bullets:
                out.append(Paragraph(f"• {b}", styles["BodyText"]))

    return out


def write_pdf(
    output_path: Path,
    head: np.ndarray,
    times: list[float],
    *,
    titulo: str = "Informe tecnico de modelacion subterranea",
    autor: str = "yaku",
    perfil: str = "astm",
    resultados=None,
    textos_secciones: dict | None = None,
) -> Path:
    """Genera el PDF del informe segun el perfil (astm | sea).

    Si `resultados` (de report.resultados.recolectar_resultados) viene, cada seccion
    escribe contenido real (calibracion, balance, parametros, mapas, etc.). Si es None,
    usa la frase guia (comportamiento base). Si reportlab no esta, genera Markdown.
    """
    perfil = perfil if perfil in PERFILES else "astm"
    spec = PERFILES[perfil]

    if not HAS_REPORTLAB:
        markdown_output = output_path.with_suffix(".md")
        write_markdown(markdown_output, head, times, titulo=titulo, autor=autor, perfil=perfil)
        logger.warning("reportlab no disponible; se genero %s", markdown_output)
        return markdown_output

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="yaku_report_") as temp_dir:
        figure_path = Path(temp_dir) / "heads.png"
        build_figure(head, figure_path)

        doc = SimpleDocTemplate(
            str(output_path), pagesize=A4, rightMargin=54, leftMargin=54, topMargin=54, bottomMargin=48
        )
        styles = tema.estilos()
        # Portada + salto de página (tema azul, ficha de autor/fecha/herramienta).
        story = tema.portada(titulo, spec["subtitulo"], autor)
        story.append(PageBreak())

        data = [
            ["Parámetro", "Valor"],
            ["Capas", str(head.shape[0])],
            ["Filas", str(head.shape[1])],
            ["Columnas", str(head.shape[2])],
            ["Tiempos simulados", str(len(times))],
            ["Carga mínima (m)", f"{head.min():.2f}"],
            ["Carga máxima (m)", f"{head.max():.2f}"],
            ["Carga media (m)", f"{head.mean():.2f}"],
            ["Desviación estándar (m)", f"{head.std():.2f}"],
        ]
        table = Table(data, colWidths=[2.7 * inch, 2.5 * inch])
        table.setStyle(tema.estilo_tabla())

        for titulo_sec, guia in spec["secciones"]:
            story.append(Paragraph(titulo_sec, styles["Heading2"]))
            if resultados is not None:
                # Informe data-driven: cada seccion escribe su contenido real.
                story.extend(_bloques_seccion(titulo_sec, resultados, styles, guia, textos_secciones))
            else:
                # Base (sin resultados): frase guia + tabla/figura de estadisticos.
                story.append(Paragraph(guia, styles["BodyText"]))
                if titulo_sec == spec["insert_figura"]:
                    story.append(Spacer(1, 0.1 * inch))
                    story.append(table)
                    story.append(Spacer(1, 0.2 * inch))
                    story.append(Paragraph("Mapa de carga hidraulica final", styles["Heading3"]))
                    story.append(RLImage(str(figure_path), width=5.6 * inch, height=4.0 * inch))
            story.append(Spacer(1, 0.18 * inch))

        doc.build(story, canvasmaker=tema.NumberedCanvas)
    return output_path


def generar_informe(cfg, output_path: Path, perfil: str = "astm", formato: str = "pdf") -> Path:
    """Informe data-driven: recolecta los resultados del proyecto y escribe el informe.

    formato='pdf' usa reportlab (tema azul); formato='docx' usa el backend Word
    (report.docx_report) y lo convierte a PDF con LibreOffice.
    """
    from yaku.report.resultados import recolectar_resultados

    res = recolectar_resultados(cfg)
    if res.head is None:
        raise FileNotFoundError(
            f"No hay cargas en {cfg.resultados_dir} (corre 'yaku run' antes del informe)."
        )
    textos = leer_secciones_md(cfg.informe_dir / "secciones.md")
    if formato == "docx":
        from yaku.report.docx_report import write_docx
        return write_docx(Path(output_path), cfg, perfil=perfil, resultados=res, textos_secciones=textos)
    return write_pdf(
        Path(output_path),
        res.head,
        res.times,
        titulo=cfg.informe.get("titulo", f"Informe - {cfg.model_name}"),
        autor=cfg.proyecto.get("autor", "yaku"),
        perfil=perfil,
        resultados=res,
        textos_secciones=textos,
    )


def write_report_from_hds(
    hds_path: Path,
    output_path: Path,
    *,
    titulo: str = "Informe tecnico de modelacion subterranea",
    autor: str = "yaku",
    perfil: str = "astm",
) -> Path:
    """Atajo: carga el .hds y escribe el informe en output_path con el perfil dado."""
    hds_path = Path(hds_path)
    if not hds_path.exists():
        raise FileNotFoundError(f"No existe el archivo HDS: {hds_path}")
    head, times = load_heads(hds_path)
    return write_pdf(output_path, head, times, titulo=titulo, autor=autor, perfil=perfil)
