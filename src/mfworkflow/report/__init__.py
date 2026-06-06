"""Generacion de informes (PDF / Markdown)."""

from mfworkflow.report.entregables import armar_entregables
from mfworkflow.report.pdf import generar_informe, write_pdf, write_report_from_hds
from mfworkflow.report.resultados import recolectar_resultados

__all__ = [
    "write_pdf", "write_report_from_hds", "generar_informe",
    "recolectar_resultados", "armar_entregables",
]
