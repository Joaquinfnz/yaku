"""yaku — motor replicable de modelacion de aguas subterraneas MODFLOW 6 + FloPy.

Paquete que convierte el workflow original (carpetas numeradas) en un motor
instalable + sistema de plantilla por proyecto, alineado al protocolo de
modelacion ASTM (D5447 / D5981) con informe de perfil seleccionable (astm | sea).

Submodulos principales:
    builder      Motor simple: CSV -> MODFLOW 6 (ModflowModelBuilder).
    setup        Motor profesional (modflow-setup) + version stamping.
    calibration  Evaluacion de ajuste, busqueda simple y PEST++/pyemu.
    transport    Transporte de solutos (GWT) e intrusion salina (BUY).
    pathlines    Trayectorias aproximadas por gradiente de Darcy.
    gis          Preproceso GIS (GeoJSON/shapefile/raster -> grilla).
    viz          Visualizaciones 2D / 3D.
    report       Generacion de informe PDF (perfiles astm | sea).
    config       Carga y validacion de config.yaml de proyecto.
    cli          Interfaz de linea de comandos `mfw`.
"""

__version__ = "2.0.0"

__all__ = ["__version__"]
