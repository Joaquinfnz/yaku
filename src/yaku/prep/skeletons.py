#!/usr/bin/env python3
"""Plantillas (skeletons) de las tablas del modelo, para ingresar datos a mano.

Cada plantilla trae el encabezado correcto, las **unidades** y una o dos filas de
ejemplo realistas, para que el usuario solo reemplace los valores. Las usa el
asistente `mfw datos`. Unidades: longitud m, conductividad m/día, caudal m³/día,
tiempo días, conductancia m²/día.
"""

from __future__ import annotations

from pathlib import Path

# Cada plantilla: contenido CSV con encabezado + ejemplo. Las columnas y unidades
# coinciden con templates/proyecto_base/datos/README.md (diccionario de datos).
PLANTILLAS: dict[str, str] = {
    "parametros_modelo.csv": (
        "clave,valor\n"
        "nlay,2\nnrow,20\nncol,20\n"
        "delr,100\ndelc,100\n"        # tamano de celda (m)
        "top,60\nbotm,0\n"            # techo y base del modelo (m)
        "starting_head,55\n"         # carga inicial (m)
        "k,8\n"                       # conductividad horizontal (m/dia) si no usas capas_modelo
        "recharge,0.0005\n"          # recarga base (m/dia)
    ),
    "capas_modelo.csv": (
        "layer,top_m,botm_m,kx_m_d,kz_m_d,sy,ss,iconvert\n"
        "1,60,35,8,1.5,0.12,1e-5,1\n"   # capa 1 (no confinada): relleno
        "2,35,0,1.5,0.2,0.04,1e-5,0\n"  # capa 2 (confinada): roca
    ),
    "contornos_carga.csv": (
        "lado,carga_m,layer,stress_period\n"
        "izquierdo,60,all,all\n"
        "derecho,45,all,all\n"
    ),
    "stress_periods.csv": (
        "stress_period,perlen_d,nstp,tsmult,steady_state\n"
        "0,1,1,1,1\n"                  # 1 periodo estacionario; usa varias filas para transiente
    ),
    "pozos.csv": (
        "nombre,layer,row,col,stress_period,rate_m3_dia\n"
        "Pozo_1,1,10,10,all,-250\n"    # rate negativo = extraccion
    ),
    "rio.csv": (
        "layer,row,col,stage_m,cond_m2_d,river_bottom_m,stress_period\n"
        "1,0,5,56,120,54,all\n"
    ),
    "observaciones_nivel.csv": (
        "nombre,layer,row,col,stress_period,head_observado_m,peso,grupo\n"
        "PZ_1,1,5,5,0,55.0,1,niveles\n"
        "PZ_2,1,15,12,0,49.5,1,validacion\n"  # grupo 'validacion' = split-sample
    ),
    "recarga_periodos.csv": (
        "stress_period,recharge_m_d\n"
        "0,0.0005\n"
    ),
    "parametros_calibracion.csv": (
        "nombre,tipo,archivo,campo,selector,valor_inicial,limite_inferior,limite_superior,transformacion,descripcion\n"
        "kx_layer_1,valor_capa,capas_modelo.csv,kx_m_d,layer=1,8,1,30,log,K horizontal capa 1\n"
        "recharge_mult,multiplicador,recarga_periodos.csv,recharge_m_d,all,1,0.3,3,log,Multiplicador de recarga\n"
    ),
    "sfr.csv": (
        "reach,row,col,length_m,mannings_n,upstream_width_m,slope,stage_m,inflow_m3_d,layer,stress_period\n"
        "1,7,2,500.0,0.035,5.0,0.001,55.0,0,1,all\n"
        "2,7,3,500.0,0.035,5.0,0.001,54.8,0,1,all\n"
        "3,7,4,500.0,0.035,5.0,0.001,54.5,0,1,all\n"
    ),
    "uzf.csv": (
        "row,col,layer,landflag,ivertcon,surfdep_m,vks_m_d,thtr,thts,thti,eps\n"
        "5,5,1,1,0,0.0,0.5,0.05,0.35,0.20,4.2\n"
        "6,6,1,1,0,0.0,0.3,0.08,0.30,0.15,3.5\n"
    ),
"uzf_periodos.csv": (
        "stress_period,infiltration_m_d,pet_m_d,et_extinction_depth_m,ext_water_content,ha,hroot,rootact\n"
        "0,0.001,0.001,2.0,0.15,0.0,0.0,0.0\n"
    ),
}


def crear_plantilla(tablas_dir: Path, nombre: str, *, sobrescribir: bool = False) -> Path | None:
    """Escribe la plantilla `nombre` en tablas_dir si existe en el catalogo.

    No sobrescribe por defecto (no pisa datos del usuario). Devuelve la ruta escrita o None.
    """
    if nombre not in PLANTILLAS:
        return None
    tablas_dir = Path(tablas_dir)
    tablas_dir.mkdir(parents=True, exist_ok=True)
    destino = tablas_dir / nombre
    if destino.exists() and not sobrescribir:
        return None
    destino.write_text(PLANTILLAS[nombre], encoding="utf-8")
    return destino
