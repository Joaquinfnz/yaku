#!/usr/bin/env python3
"""Tema visual del informe PDF (paleta azul, portada y numeración de página).

Centraliza la identidad gráfica del informe de modelación para que `report/pdf.py`
(y un eventual backend docx) compartan la misma paleta y estilos. La paleta azul es
coherente con el tema del tutorial Word (docs/_tools/docx_helpers.py).
"""

from __future__ import annotations

from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

# Paleta azul/agua (coherente con el tutorial Word).
AZUL_OSCURO = colors.HexColor("#1F4E79")
AZUL_MEDIO = colors.HexColor("#2E75B6")
AZUL_CLARO = colors.HexColor("#DEEAF1")
GRIS = colors.HexColor("#9E9E9E")


class NumberedCanvas(canvas.Canvas):
    """Canvas que dibuja 'Página X de Y' y una línea de pie en cada página."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states: list[dict] = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self._dibujar_pie(total)
            super().showPage()
        super().save()

    def _dibujar_pie(self, total: int) -> None:
        ancho = A4[0]
        self.setStrokeColor(AZUL_MEDIO)
        self.setLineWidth(0.6)
        self.line(54, 30, ancho - 54, 30)
        self.setFont("Helvetica", 8)
        self.setFillColor(AZUL_OSCURO)
        self.drawRightString(ancho - 54, 20, f"Página {self._pageNumber} de {total}")
        self.drawString(54, 20, "yaku — informe de modelación de aguas subterráneas")


def estilos():
    """Hoja de estilos con encabezados en azul y cuerpo justificado."""
    styles = getSampleStyleSheet()
    styles["Title"].textColor = AZUL_OSCURO
    for h, size in (("Heading1", 16), ("Heading2", 13), ("Heading3", 11), ("Heading4", 10)):
        styles[h].textColor = AZUL_OSCURO if h in ("Heading1", "Heading2") else AZUL_MEDIO
        styles[h].spaceBefore = 8
    if "PortadaTitulo" not in styles:
        styles.add(ParagraphStyle("PortadaTitulo", parent=styles["Title"], fontSize=24,
                                  leading=28, textColor=AZUL_OSCURO, alignment=TA_CENTER))
        styles.add(ParagraphStyle("PortadaSub", parent=styles["Italic"], fontSize=12,
                                  textColor=AZUL_MEDIO, alignment=TA_CENTER))
    return styles


def estilo_tabla(encabezado=AZUL_MEDIO, filas=AZUL_CLARO) -> TableStyle:
    """TableStyle del tema: encabezado azul, filas alternadas claras."""
    return TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), encabezado),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, GRIS),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, filas]),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ])


def portada(titulo: str, subtitulo: str, autor: str, *, fecha: str | None = None) -> list:
    """Flowables de la portada: banda azul, título, subtítulo, autor y fecha."""
    fecha = fecha or datetime.now().strftime("%Y-%m-%d")
    styles = estilos()
    banda = Table([[""]], colWidths=[A4[0] - 108], rowHeights=[0.18 * inch])
    banda.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), AZUL_MEDIO)]))
    ficha = Table([["Autor", autor], ["Fecha", fecha],
                   ["Herramienta", "yaku (MODFLOW 6 + FloPy)"]],
                  colWidths=[1.6 * inch, 3.8 * inch])
    ficha.setStyle(estilo_tabla())
    return [
        Spacer(1, 1.6 * inch),
        banda,
        Spacer(1, 0.4 * inch),
        Paragraph(titulo, styles["PortadaTitulo"]),
        Spacer(1, 0.2 * inch),
        Paragraph(subtitulo, styles["PortadaSub"]),
        Spacer(1, 0.8 * inch),
        ficha,
    ]
