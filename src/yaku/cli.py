"""CLI `mfw` — interfaz de linea de comandos del workflow.

Subcomandos:
    new        Instancia un proyecto nuevo desde la plantilla.
    build      Construye el modelo MODFLOW 6 (etapa 3 ASTM).
    run        Construye y ejecuta la simulacion (etapa 3 ASTM).
    calibrate  Calibracion / sensibilidad (etapas 4-5 ASTM)  [Fase 5].
    predict    Prediccion + incertidumbre (etapa 6 ASTM)      [Fase 5/6].
    report     Genera el informe PDF (perfil astm | sea, etapa 7 ASTM).
    pipeline   build -> run -> report (equivalente a run_pipeline.py).
    datos      Asistente de datos: crea plantillas editables de las tablas que faltan.
    check      Revisa los insumos del proyecto (obligatorios/importantes/opcionales).
    onboard    Pantalla de inicio guiada (estado del proyecto + siguiente paso).
"""

from __future__ import annotations

import argparse
import shutil
import sys
from datetime import date
from pathlib import Path

from yaku import __version__


# ---------------------------------------------------------------------------
# Localizacion de la plantilla
# ---------------------------------------------------------------------------
def find_templates_dir() -> Path:
    """Localiza templates/proyecto_base subiendo desde el paquete o el cwd."""
    candidates = []
    # 1) relativo al paquete instalado en modo editable: <repo>/src/yaku
    pkg_root = Path(__file__).resolve()
    for parent in pkg_root.parents:
        candidates.append(parent / "templates" / "proyecto_base")
    # 2) relativo al directorio actual
    candidates.append(Path.cwd() / "templates" / "proyecto_base")
    for c in candidates:
        if c.is_dir():
            return c
    raise FileNotFoundError(
        "No se encontro templates/proyecto_base. Ejecuta mfw desde el repo del workflow."
    )


# ---------------------------------------------------------------------------
# new
# ---------------------------------------------------------------------------
# Perfiles por tipo de estudio: orientan objetivos/perfil del config.yaml.
TIPOS_ESTUDIO = {
    "general": {
        "proposito": "Describir el objetivo del modelo de aguas subterraneas.",
        "perfil": "sea", "escala": "local",
    },
    "dewatering": {
        "proposito": "Evaluar el descenso de niveles por bombeo/excavacion (dewatering) y su "
                     "efecto sobre pozos, caudales y ecosistemas asociados.",
        "perfil": "sea", "escala": "local",
    },
    "intrusion": {
        "proposito": "Evaluar el avance de la cuna salina (intrusion salina) ante el proyecto.",
        "perfil": "sea", "escala": "local",
    },
    "gde": {
        "proposito": "Evaluar la afeccion del proyecto a ecosistemas dependientes del agua "
                     "subterranea (vegas, bofedales, turberas) por descenso del nivel freatico.",
        "perfil": "sea", "escala": "local",
    },
}


def _aplicar_tipo(config_path: Path, tipo: str) -> None:
    """Ajusta objetivos/perfil del config.yaml segun el tipo de estudio."""
    spec = TIPOS_ESTUDIO.get(tipo)
    if not spec or not config_path.exists():
        return
    texto = config_path.read_text(encoding="utf-8")
    import re

    texto = re.sub(r'(\n  proposito: ")[^"]*(")', rf'\g<1>{spec["proposito"]}\g<2>', texto, count=1)
    texto = re.sub(r'(\n  escala: ")[^"]*(")', rf'\g<1>{spec["escala"]}\g<2>', texto, count=1)
    texto = re.sub(r'(\n  perfil: ")[^"]*(")', rf'\g<1>{spec["perfil"]}\g<2>', texto, count=1)
    config_path.write_text(texto, encoding="utf-8")


def cmd_new(args: argparse.Namespace) -> int:
    template = find_templates_dir()
    dest_root = Path(args.dest).resolve()
    dest = dest_root / args.nombre
    if dest.exists():
        print(f"[mfw] ERROR: ya existe {dest}", file=sys.stderr)
        return 1

    shutil.copytree(template, dest)

    replacements = {
        "{{nombre}}": args.nombre,
        "{{autor}}": args.autor,
        "{{fecha}}": args.fecha or date.today().isoformat(),
    }
    # Sustituir placeholders en archivos de texto (config, README, checklist)
    for path in dest.rglob("*"):
        if path.suffix.lower() in {".yaml", ".yml", ".md", ".txt"} and path.is_file():
            text = path.read_text(encoding="utf-8")
            for key, value in replacements.items():
                text = text.replace(key, value)
            path.write_text(text, encoding="utf-8")

    tipo = getattr(args, "tipo", "general")
    _aplicar_tipo(dest / "config.yaml", tipo)

    print(f"[mfw] Proyecto creado: {dest} (tipo: {tipo})")
    print(f"      Edita datos/tablas/*.csv y corre: mfw pipeline --project {dest}")

    if args.git:
        import subprocess

        subprocess.run(["git", "init", "-q"], cwd=dest, check=False)
        print("[mfw] Repositorio git inicializado en el proyecto.")
    return 0


# ---------------------------------------------------------------------------
# Helpers de proyecto (build / run / report / pipeline)
# ---------------------------------------------------------------------------
def _listar_proyectos() -> list[Path]:
    """Busca proyectos (carpetas con config.yaml) en proyectos/ y examples/."""
    encontrados: list[Path] = []
    for base in ("proyectos", "examples"):
        root = Path.cwd() / base
        if root.is_dir():
            encontrados.extend(sorted(p.parent for p in root.glob("*/config.yaml")))
    return encontrados


def _load(project: str):
    from yaku.config import resolve_project_config
    from yaku.logging_setup import setup_logging

    target = Path(project)
    config_path = target / "config.yaml" if target.is_dir() else target
    if not config_path.exists():
        print(f"[mfw] No se encontro config.yaml en '{project}'.", file=sys.stderr)
        print("      Indica el proyecto con --project <carpeta>. Por ejemplo:", file=sys.stderr)
        disponibles = _listar_proyectos()
        if disponibles:
            for p in disponibles:
                try:
                    rel = p.relative_to(Path.cwd())
                except ValueError:
                    rel = p
                print(f"        mfw {' '.join(sys.argv[1:2])} --project {rel}", file=sys.stderr)
        else:
            print("        mfw new mi_proyecto      # crea uno nuevo primero", file=sys.stderr)
        raise SystemExit(2)

    cfg = resolve_project_config(target)
    logger = setup_logging(cfg.log_dir)
    return cfg, logger


def _drapear(cfg) -> bool:
    """Lee modelo.drapear_dem del config (techo del modelo siguiendo el DEM)."""
    modelo = (getattr(cfg, "raw", {}) or {}).get("modelo", {}) or {}
    return bool(modelo.get("drapear_dem", False))


def _builder(cfg):
    from yaku.builder import ModflowModelBuilder

    return ModflowModelBuilder(
        data_dir=cfg.datos_dir,
        workspace=cfg.resultados_dir,
        model_name=cfg.model_name,
        drapear_dem=_drapear(cfg),
    )


def _validate(cfg, builder, logger) -> bool:
    """Valida config + insumos minimos + estructura + geometria/unidades."""
    from yaku.builder import validate_geometry_and_units
    from yaku.insumos import revisar_insumos

    ok = True
    for e in cfg.validate():
        logger.error("config: %s", e)
        ok = False

    # Gate de insumos: bloquea build/run si faltan las tablas minimas para correr.
    faltan = revisar_insumos(cfg).faltan_para_correr
    if faltan:
        logger.error("insumos: faltan tablas minimas para modelar: %s", ", ".join(faltan))
        logger.error("         revisa 'mfw check --project %s' (o genera tablas con 'mfw prep').",
                     cfg.project_dir.name)
        ok = False
    for e in builder.validate_input_data():
        logger.error("datos: %s", e)
        ok = False
    geo = validate_geometry_and_units(cfg.datos_dir)
    for w in geo.warnings:
        logger.warning("datos: %s", w)
    for e in geo.errors:
        logger.error("geometria: %s", e)
        ok = False
    return ok


def _stamp(cfg, logger) -> None:
    from yaku.setup import stamp_inputs

    out = stamp_inputs(
        cfg.resultados_dir,
        config_path=cfg.project_dir / "config.yaml",
        datos_dir=cfg.datos_dir,
        model_name=cfg.model_name,
        motor=cfg.motor,
    )
    logger.info("Trazabilidad escrita: %s", out.name)


def _build_mfsetup(cfg, logger, run: bool) -> int:
    from yaku.setup.mfsetup_runner import build_from_yaml, is_available

    if not is_available():
        logger.error("motor 'mfsetup' requiere modflow-setup (pip install modflow-setup).")
        return 1
    if not cfg.setup_yaml.exists():
        logger.error("Falta el YAML de modflow-setup: %s", cfg.setup_yaml)
        return 1
    build_from_yaml(cfg.setup_yaml, run=run)
    _stamp(cfg, logger)
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    cfg, logger = _load(args.project)
    if cfg.motor == "mfsetup":
        return _build_mfsetup(cfg, logger, run=False)
    builder = _builder(cfg)
    if not _validate(cfg, builder, logger):
        return 1
    builder.build_simulation()
    _stamp(cfg, logger)
    logger.info("Modelo '%s' construido en %s", cfg.model_name, cfg.resultados_dir)
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    cfg, logger = _load(args.project)
    if cfg.motor == "mfsetup":
        return _build_mfsetup(cfg, logger, run=True)
    builder = _builder(cfg)
    if not _validate(cfg, builder, logger):
        return 1
    builder.build_and_run(postprocess=not args.skip_viz)
    _stamp(cfg, logger)
    logger.info("Simulacion completada: %s", cfg.resultados_dir)
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    cfg, logger = _load(args.project)
    from yaku.report import generar_informe

    hds = cfg.resultados_dir / f"{cfg.model_name}.hds"
    if not hds.exists():
        logger.error("No existe %s. Corre 'mfw run' primero.", hds)
        return 1
    perfil = (args.perfil or cfg.perfil_informe).lower()
    formato = getattr(args, "formato", "pdf") or "pdf"
    cfg.informe_dir.mkdir(parents=True, exist_ok=True)
    out = cfg.informe_dir / f"informe_{cfg.model_name}_{perfil}.pdf"
    written = generar_informe(cfg, out, perfil=perfil, formato=formato)
    logger.info("Informe data-driven (perfil %s, formato %s) generado: %s", perfil, formato, written)
    return 0


def cmd_entregables(args: argparse.Namespace) -> int:
    cfg, logger = _load(args.project)
    from yaku.report import armar_entregables

    hds = cfg.resultados_dir / f"{cfg.model_name}.hds"
    if not hds.exists():
        logger.error("No existe %s. Corre 'mfw run' primero.", hds)
        return 1
    perfil = (args.perfil or cfg.perfil_informe).lower()
    dest = armar_entregables(cfg, perfil=perfil)
    logger.info("Paquete de entregables SEIA generado: %s", dest)
    return 0


def cmd_pipeline(args: argparse.Namespace) -> int:
    rc = cmd_run(args)
    if rc != 0:
        return rc
    if not args.skip_report:
        return cmd_report(args)
    return 0


def cmd_calibrate(args: argparse.Namespace) -> int:
    cfg, logger = _load(args.project)
    from yaku.calibration import evaluate_fit, run_pest, setup_pest

    hds = cfg.resultados_dir / f"{cfg.model_name}.hds"
    if not hds.exists():
        logger.error("No existe %s. Corre 'mfw run' primero.", hds)
        return 1

    # Etapa 4: evaluacion de ajuste (siempre)
    obs_path = cfg.calib_path("observaciones", "datos/tablas/observaciones_nivel.csv")
    out_dir = cfg.resultados_dir / "calibracion"
    metrics = evaluate_fit(hds, obs_path, out_dir)
    logger.info("Ajuste evaluado:\n%s", metrics.to_string(index=False))

    # Setup/corrida PEST++ formal (opcional)
    if args.setup_pest or args.run:
        calib_path = cfg.calib_path("parametros", "datos/tablas/parametros_calibracion.csv")
        engine = args.engine
        pst = setup_pest(
            out_dir / "pest_control",
            cfg.datos_dir,
            obs_path,
            calib_path,
            max_params=args.max_params,
            noptmax=args.noptmax,
            engine=engine,
        )
        logger.info("Caso PEST++ generado: %s (motor %s)", pst, engine)
        if args.run:
            logger.info("Ejecutando %s ... (puede tardar)", engine)
            ok = run_pest(pst, engine=engine, timeout=args.timeout)
            logger.info("PEST++ %s", "OK" if ok else "fallo (revisa el .rec)")
            return 0 if ok else 1
    return 0


def cmd_sensibilidad(args: argparse.Namespace) -> int:
    cfg, logger = _load(args.project)
    from yaku.calibration.sensibilidad import sensibilidad_oat

    obs = cfg.calib_path("observaciones", "datos/tablas/observaciones_nivel.csv")
    calib = cfg.calib_path("parametros", "datos/tablas/parametros_calibracion.csv")
    if not calib.exists() or not obs.exists():
        logger.error("Faltan parametros_calibracion.csv u observaciones_nivel.csv.")
        return 1
    df = sensibilidad_oat(cfg.datos_dir, calib, obs, cfg.resultados_dir / "sensibilidad",
                          model_name=cfg.model_name, delta=args.delta, drapear_dem=_drapear(cfg))
    logger.info("Sensibilidad (mas influyente arriba):\n%s", df.to_string(index=False))
    return 0


def cmd_transport(args: argparse.Namespace) -> int:
    cfg, logger = _load(args.project)
    from yaku.transport import gwt

    out = gwt.run(cfg.resultados_dir / "transporte")
    logger.info("Transporte GWT generado: %s", out)
    return 0


def cmd_salina(args: argparse.Namespace) -> int:
    cfg, logger = _load(args.project)
    from yaku.transport import seawater

    out = seawater.run(cfg.resultados_dir / "intrusion_salina")
    logger.info("Intrusion salina (GWT+BUY) generada: %s", out)
    return 0


def cmd_pathlines(args: argparse.Namespace) -> int:
    cfg, logger = _load(args.project)
    from yaku.binaries import resolve_exe

    out_dir = cfg.resultados_dir / "trayectorias"
    hds = cfg.resultados_dir / f"{cfg.model_name}.hds"

    if not args.aprox and resolve_exe("mp7"):
        from yaku.pathlines import modpath7

        try:
            out = modpath7.run(cfg.resultados_dir, cfg.datos_dir, out_dir,
                               model_name=cfg.model_name, direction=args.direction)
            logger.info("MODPATH 7 (%s): %s", args.direction, out.get("figura"))
            if "resumen" in out:
                logger.info("Tiempos de viaje (zonas de captura): %s", out["resumen"])
            return 0
        except Exception as exc:
            logger.warning("MODPATH 7 fallo (%s); uso aproximacion por gradiente.", exc)

    from yaku.pathlines import darcy_gradient

    out = darcy_gradient.run(hds, cfg.datos_dir, out_dir)
    logger.info("Trayectorias aproximadas (gradiente) generadas: %s", out)
    return 0


def cmd_gis(args: argparse.Namespace) -> int:
    cfg, logger = _load(args.project)
    from yaku.gis import preprocess

    out = preprocess.run(cfg.gis_dir, cfg.datos_dir, cfg.resultados_dir / "gis")
    logger.info("Preproceso GIS completado: %s", out["figura"])
    return 0


def cmd_export_gis(args: argparse.Namespace) -> int:
    cfg, logger = _load(args.project)
    from yaku.gis.export import exportar_rasters

    out = exportar_rasters(cfg)
    if not out:
        return 1
    logger.info("Export GIS listo (%d rasters). Abrelos en QGIS/ArcGIS.", len(out))
    return 0


def cmd_predict(args: argparse.Namespace) -> int:
    cfg, logger = _load(args.project)
    from yaku.calibration import monte_carlo, scenario_drawdown

    hds = cfg.resultados_dir / f"{cfg.model_name}.hds"
    if not hds.exists():
        logger.error("No existe %s. Corre 'mfw run' primero.", hds)
        return 1
    out_dir = cfg.resultados_dir / "prediccion"

    drapear = _drapear(cfg)
    scen = scenario_drawdown(cfg.datos_dir, out_dir, factor=args.factor, model_name=cfg.model_name,
                             drapear_dem=drapear)
    logger.info("Escenario con/sin proyecto (factor %.2f): %s", args.factor, scen["mapa"])

    if args.uncertainty:
        calib = cfg.calib_path("parametros", "datos/tablas/parametros_calibracion.csv")
        mc = monte_carlo(cfg.datos_dir, calib, out_dir, n=args.uncertainty, model_name=cfg.model_name,
                         drapear_dem=drapear)
        logger.info("Incertidumbre Monte Carlo (n=%d): %s", args.uncertainty, mc["mapa"])
    return 0


def cmd_mesh(args: argparse.Namespace) -> int:
    cfg, logger = _load(args.project)
    from yaku.gis.preprocess import find_vector
    from yaku.mesh import build_voronoi

    dom = find_vector(cfg.gis_dir, "dominio")
    if dom is None:
        logger.error("Falta dominio (shapefile) en %s.", cfg.gis_dir)
        return 1
    out = build_voronoi(dom, cfg.gis_dir, cfg.resultados_dir / "malla",
                        cell_size=args.cell_size, refine_factor=args.refine)
    logger.info("Malla Voronoi (%d celdas): %s", out["ncpl"], out["figura"])
    if args.run:
        _correr_disv(cfg, out["gridprops"], logger)
    return 0


def _correr_disv(cfg, gridprops, logger) -> None:
    """Corre el DISV: multicapa geologia-driven si hay capas_modelo + DEM; si no, 1 capa."""
    import pandas as pd

    from yaku.gis.preprocess import find_vector
    from yaku.mesh.voronoi import build_disv_model, run_disv_flow, zonas_geologicas

    malla = cfg.resultados_dir / "malla"
    capas_csv = cfg.datos_dir / "capas_modelo.csv"
    dem = cfg.project_dir / "datos" / "fuente" / "dem.tif"

    if not capas_csv.exists() or not dem.exists():
        png = run_disv_flow(gridprops, malla)
        logger.info("Modelo DISV (1 capa, verificacion) listo: %s", png)
        return

    df = pd.read_csv(capas_csv).sort_values("layer")
    capas = [{"espesor": float(r.top_m) - float(r.botm_m), "k": float(r.kx_m_d)}
             for r in df.itertuples(index=False)]

    # Parametros globales (recarga base)
    recharge = 5e-4
    pm = cfg.datos_dir / "parametros_modelo.csv"
    if pm.exists():
        p = pd.read_csv(pm)
        if {"clave", "valor"} <= set(p.columns):
            d = {str(r.clave): r.valor for r in p.itertuples(index=False)}
            recharge = float(d.get("recharge", recharge))

    # Geologia opcional -> K y recarga por celda
    k_celda = rch_celda = None
    geo = find_vector(cfg.gis_dir, "geologia") or find_vector(cfg.project_dir / "datos" / "fuente", "geologia")
    if geo is not None:
        try:
            z = zonas_geologicas(geo, gridprops)
            k_celda = z["k"]
            if z["coef_inf"] is not None:
                clima = cfg.project_dir / "datos" / "fuente" / "clima.csv"
                if clima.exists() and "precip_mm" in pd.read_csv(clima).columns:
                    precip_m_d = float(pd.read_csv(clima)["precip_mm"].mean()) / 1000.0 / 30.0
                    rch_celda = z["coef_inf"] * precip_m_d
            logger.info("Geologia aplicada: K por unidad (%d celdas)", len(k_celda) if k_celda is not None else 0)
        except Exception as exc:  # noqa: BLE001
            logger.warning("No se pudo aplicar geologia (%s); uso K por capa.", exc)

    fuente = cfg.project_dir / "datos" / "fuente"
    pozos = find_vector(cfg.gis_dir, "pozos") or find_vector(fuente, "pozos")
    rio = find_vector(cfg.gis_dir, "rio") or find_vector(fuente, "rio")
    res = build_disv_model(gridprops, malla, dem_path=dem, capas=capas, recharge=recharge,
                           k_por_celda=k_celda, recarga_por_celda=rch_celda,
                           pozos_path=pozos, rio_path=rio)
    logger.info("Modelo DISV multicapa drapeado: nlay=%d, ncpl=%d -> %s",
                res["nlay"], res["ncpl"], res["png"].name)


def cmd_prep(args: argparse.Namespace) -> int:
    cfg, logger = _load(args.project)
    from yaku.prep import prepare_from_sources

    source_dir = cfg.project_dir / "datos" / "fuente"
    if not source_dir.is_dir():
        logger.error("No existe %s. Pon ahi tu DEM (dem.tif), dominio.shp, pozos.shp y caudales.csv.", source_dir)
        return 1
    resumen = prepare_from_sources(
        source_dir, cfg.datos_dir, cfg.gis_dir,
        cellsize=args.cellsize, nlay=args.nlay, espesor=args.espesor,
    )
    logger.info("Preparacion lista. Grilla: %s", resumen.get("grilla"))
    logger.info("Revisa y edita datos/tablas/*.csv; luego: mfw pipeline --project %s", args.project)
    return 0


def cmd_recarga(args: argparse.Namespace) -> int:
    cfg, logger = _load(args.project)
    from yaku.prep.recarga import calcular_recarga

    clima = cfg.project_dir / "datos" / "fuente" / "clima.csv"
    if not clima.exists():
        logger.error("No existe %s. Pon ahi tu serie climatica (fecha, precip_mm, temp_c, et0_mm).", clima)
        return 1
    res = calcular_recarga(clima, cfg.datos_dir, metodo=args.metodo, cc_mm=args.cc,
                           coef_infiltracion=args.coef_inf, coef_escorrentia=args.escorrentia,
                           k_percolacion=args.k_percolacion, transiente=args.transiente)
    logger.info("Recarga (%s): %s (%d periodos, recarga total ~%.0f mm).",
                res["metodo"], res["archivo"].name, res["n_periodos"], res["recarga_total_mm"])
    return 0


def cmd_indices(args: argparse.Namespace) -> int:
    cfg, logger = _load(args.project)
    from yaku.report.indices_clima import calcular_indices

    out = calcular_indices(cfg)
    if out is None:
        logger.error("Faltan datos de clima (datos/fuente/clima.csv) para los indices.")
        return 1
    logger.info("Indices clima-hidrogeologia (%d indicadores):\n%s",
                len(out["tabla"]), out["tabla"].to_string(index=False))
    return 0


def cmd_view3d(args: argparse.Namespace) -> int:
    cfg, logger = _load(args.project)
    from yaku.viz import plots_3d

    # --mesh: ver el modelo Voronoi/DISV generado por 'mfw mesh --run'
    if args.mesh:
        workspace = cfg.resultados_dir / "malla"
        model_name = "voronoi"
        sugerencia = "mfw mesh --project <p> --run"
    else:
        workspace = cfg.resultados_dir
        model_name = cfg.model_name
        sugerencia = "mfw run --project <p>"

    hds = workspace / f"{model_name}.hds"
    if not hds.exists():
        logger.error("No existe %s. Corre primero: %s", hds, sugerencia)
        return 1
    out = plots_3d.run(workspace, model_name, workspace / "vista_3d",
                       vertical_exageration=args.exageration)
    if "vtk" not in out:
        logger.error("No se pudo exportar el VTK 3D.")
        return 1
    logger.info("VTK 3D: %s", out["vtk"])
    if "png" in out:
        logger.info("PNG 3D: %s", out["png"])
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    """Chequea que el entorno tenga binarios y paquetes necesarios."""
    import importlib

    from yaku.binaries import resolve_exe

    print("mfw doctor — chequeo del entorno\n")
    ok = True

    binarios = {
        "mf6": "MODFLOW 6 (flujo/transporte)",
        "mp7": "MODPATH 7 (trayectorias)",
        "triangle": "Triangle (mallas Voronoi)",
        "pestpp-glm": "PEST++ GLM (calibracion)",
        "pestpp-ies": "PEST++ IES (incertidumbre)",
    }
    print("Binarios:")
    for exe, desc in binarios.items():
        path = resolve_exe(exe)
        marca = "OK " if path else "FALTA"
        if not path:
            ok = False
        print(f"  [{marca}] {exe:12s} {desc}" + (f"  -> {path}" if path else ""))

    paquetes = {
        "flopy": "nucleo MODFLOW/FloPy",
        "pyemu": "calibracion / incertidumbre",
        "mfsetup": "motor profesional (modflow-setup)",
        "geopandas": "GIS",
        "reportlab": "informe PDF",
        "pyvista": "visualizacion 3D",
    }
    print("\nPaquetes Python:")
    for mod, desc in paquetes.items():
        try:
            m = importlib.import_module(mod)
            ver = getattr(m, "__version__", "?")
            print(f"  [OK ] {mod:12s} {desc} (v{ver})")
        except Exception:
            print(f"  [FALTA] {mod:12s} {desc}")
            if mod in ("flopy",):
                ok = False

    missing_binaries = []
    for binary in ("mp7", "triangle"):
        if not shutil.which(binary):
            missing_binaries.append(binary)
    if missing_binaries:
        print(f"\nBinarios faltantes: {', '.join(missing_binaries)}")
        print("Sugerencia: instala binarios MODFLOW/MODPATH/Triangle con:")
        print("  get-modflow :flopy")
    print("\nEstado:", "todo OK" if ok else "faltan componentes (ver arriba)")
    return 0 if ok else 1


def cmd_datos(args: argparse.Namespace) -> int:
    """Asistente de datos: muestra qué falta y crea plantillas editables para llenarlas."""
    cfg, _ = _load(args.project)
    from yaku.insumos import IMPORTANTE, OBLIGATORIO, formatear, revisar_insumos
    from yaku.prep.skeletons import PLANTILLAS, crear_plantilla
    from yaku.tui import UI

    ui = UI()
    rep = revisar_insumos(cfg)
    ui.print("\n".join(formatear(rep, raiz=cfg.project_dir)))
    ui.print("\nVoy a ayudarte a completar lo que falta:\n")

    for nivel in (OBLIGATORIO, IMPORTANTE):
        for ins, ruta in rep.por_nivel(nivel):
            if ruta is not None:
                continue
            if ins.tabla and ins.tabla in PLANTILLAS:
                if ui.confirm(f"Falta '{ins.tabla}' ({ins.para_que}) ¿Creo una plantilla editable?",
                              default=(nivel == OBLIGATORIO)):
                    p = crear_plantilla(cfg.datos_dir, ins.tabla)
                    if p:
                        ui.print(f"  ✓ Creada {p.relative_to(cfg.project_dir)} — ábrela y reemplaza los valores de ejemplo.")
                    else:
                        ui.print(f"  (ya existía {ins.tabla})")
            else:  # dominio, dem, pozos.shp, geologia, clima...
                if getattr(ins, "fuente", None):       # archivo exacto (dem.tif, clima.csv, caudales.csv)
                    archivo, paso = ins.fuente, ("mfw recarga" if ins.fuente == "clima.csv" else "mfw prep")
                else:                                    # capa vectorial
                    archivo, paso = f"{ins.vector}.shp", "mfw prep"
                ui.print(f"  • {ins.clave}: pon '{archivo}' en datos/fuente/ y luego corre '{paso}'.")

    rep2 = revisar_insumos(cfg)
    if rep2.ok_minimos:
        ui.print("\n=> Mínimos completos. Edita las plantillas con tus datos y corre 'mfw run'.")
    else:
        ui.print(f"\n=> Aún faltan tablas mínimas: {', '.join(rep2.faltan_para_correr)}. "
                 "Vuelve a correr 'mfw datos' o créalas a mano.")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    """Revisa los insumos del proyecto (obligatorios / importantes / opcionales)."""
    cfg, _ = _load(args.project)
    from yaku.insumos import formatear, revisar_insumos

    rep = revisar_insumos(cfg)
    print(f"\nInsumos de '{cfg.proyecto.get('nombre', args.project)}':")
    for linea in formatear(rep, raiz=cfg.project_dir):
        print(linea)
    return 0 if rep.ok_minimos else 1


def cmd_onboard(args: argparse.Namespace) -> int:
    """Onboard: pantalla de inicio guiada (la misma que abre `mfw` sin argumentos)."""
    from yaku.tui import run_home

    return run_home()


def cmd_todo(args: argparse.Namespace) -> int:
    print(f"[mfw] Subcomando '{args.command}' se implementa en una fase posterior.", file=sys.stderr)
    return 1


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mfw",
        description="Workflow replicable de modelacion de aguas subterraneas (MODFLOW 6 + FloPy)",
    )
    parser.add_argument("--version", action="version", version=f"yaku {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="<comando>")

    p_new = sub.add_parser("new", help="Instancia un proyecto nuevo desde la plantilla")
    p_new.add_argument("nombre", help="Nombre del proyecto (ej. mi_proyecto)")
    p_new.add_argument("--dest", default="proyectos", help="Carpeta donde crear el proyecto")
    p_new.add_argument("--autor", default="Joaquin Fernandez")
    p_new.add_argument("--tipo", choices=list(TIPOS_ESTUDIO), default="general",
                       help="Tipo de estudio: orienta objetivos y perfil (sea)")
    p_new.add_argument("--fecha", default="", help="Fecha ISO; por defecto hoy")
    p_new.add_argument("--git", action="store_true", help="Inicializa git en el proyecto")
    p_new.set_defaults(func=cmd_new)

    def add_project(p: argparse.ArgumentParser) -> None:
        p.add_argument("--project", default=".", help="Carpeta del proyecto o ruta a config.yaml")

    p_build = sub.add_parser("build", help="Construye el modelo MODFLOW 6")
    add_project(p_build)
    p_build.set_defaults(func=cmd_build)

    p_run = sub.add_parser("run", help="Construye y ejecuta la simulacion")
    add_project(p_run)
    p_run.add_argument("--skip-viz", action="store_true", help="Omitir postproceso/figuras")
    p_run.set_defaults(func=cmd_run)

    p_report = sub.add_parser("report", help="Genera el informe PDF")
    add_project(p_report)
    p_report.add_argument("--perfil", choices=["astm", "sea"], default=None, help="Perfil de informe")
    p_report.add_argument("--formato", choices=["pdf", "docx"], default="pdf",
                          help="Formato de salida: pdf (reportlab) o docx (Word -> PDF con LibreOffice)")
    p_report.set_defaults(func=cmd_report)

    p_ent = sub.add_parser("entregables", help="Arma el paquete de entregables SEIA (carpeta lista)")
    add_project(p_ent)
    p_ent.add_argument("--perfil", choices=["astm", "sea"], default=None, help="Perfil de informe")
    p_ent.set_defaults(func=cmd_entregables)

    p_pipe = sub.add_parser("pipeline", help="build -> run -> report")
    add_project(p_pipe)
    p_pipe.add_argument("--skip-viz", action="store_true")
    p_pipe.add_argument("--skip-report", action="store_true")
    p_pipe.add_argument("--perfil", choices=["astm", "sea"], default=None)
    p_pipe.set_defaults(func=cmd_pipeline)

    p_cal = sub.add_parser("calibrate", help="Evaluacion de ajuste + calibracion PEST++")
    add_project(p_cal)
    p_cal.add_argument("--setup-pest", action="store_true", help="Genera el caso PEST++ (no lo corre)")
    p_cal.add_argument("--run", action="store_true", help="Genera y ejecuta PEST++")
    p_cal.add_argument("--engine", choices=["pestpp-glm", "pestpp-ies"], default="pestpp-glm")
    p_cal.add_argument("--max-params", type=int, default=8,
                       help="Maximo de parametros del CSV a calibrar (toma los primeros N)")
    p_cal.add_argument("--noptmax", type=int, default=3, help="Iteraciones PEST++")
    p_cal.add_argument("--timeout", type=int, default=None, help="Timeout en segundos para PEST++")
    p_cal.set_defaults(func=cmd_calibrate)

    p_pred = sub.add_parser("predict", help="Prediccion: escenario con/sin proyecto + incertidumbre")
    add_project(p_pred)
    p_pred.add_argument("--factor", type=float, default=1.5, help="Factor de bombeo del escenario (con proyecto)")
    p_pred.add_argument("--uncertainty", type=int, default=0, metavar="N",
                        help="N realizaciones Monte Carlo de incertidumbre (0 = omitir)")
    p_pred.set_defaults(func=cmd_predict)

    # Modulos avanzados
    p_sens = sub.add_parser("sensibilidad", help="Analisis de sensibilidad OAT de los parametros")
    add_project(p_sens)
    p_sens.add_argument("--delta", type=float, default=0.1, help="Perturbacion relativa (0.1 = +/-10%)")
    p_sens.set_defaults(func=cmd_sensibilidad)

    p_tr = sub.add_parser("transport", help="Transporte de solutos (GWT)")
    add_project(p_tr)
    p_tr.set_defaults(func=cmd_transport)

    p_sal = sub.add_parser("salina", help="Intrusion salina (GWT + BUY)")
    add_project(p_sal)
    p_sal.set_defaults(func=cmd_salina)

    p_path = sub.add_parser("pathlines", help="Trayectorias (MODPATH 7 real o aproximacion)")
    add_project(p_path)
    p_path.add_argument("--direction", choices=["backward", "forward"], default="backward",
                        help="backward = zonas de captura desde pozos")
    p_path.add_argument("--aprox", action="store_true", help="Forzar aproximacion por gradiente")
    p_path.set_defaults(func=cmd_pathlines)

    p_gis = sub.add_parser("gis", help="Preproceso GIS (GeoJSON -> tablas)")
    add_project(p_gis)
    p_gis.set_defaults(func=cmd_gis)

    p_xgis = sub.add_parser("export-gis", help="Exporta cargas/napa a raster GeoTIFF (QGIS)")
    add_project(p_xgis)
    p_xgis.set_defaults(func=cmd_export_gis)

    p_mesh = sub.add_parser("mesh", help="Genera malla Voronoi/DISV (refinada en pozos)")
    add_project(p_mesh)
    p_mesh.add_argument("--cell-size", type=float, default=200.0, help="Tamano de celda gruesa (m)")
    p_mesh.add_argument("--refine", type=float, default=6.0, help="Factor de refinamiento en pozos")
    p_mesh.add_argument("--run", action="store_true", help="Construir y correr un modelo DISV de prueba")
    p_mesh.set_defaults(func=cmd_mesh)

    p_rec = sub.add_parser("recarga", help="Calcula la recarga desde clima.csv (balance de suelo) -> recarga_periodos.csv")
    add_project(p_rec)
    p_rec.add_argument("--metodo", choices=["balance", "coeficiente"], default="balance",
                       help="balance (suelo, usa precip+ET) | coeficiente (coef*precip)")
    p_rec.add_argument("--cc", type=float, default=100.0, help="Capacidad de campo del suelo (mm)")
    p_rec.add_argument("--coef-inf", type=float, default=0.15, help="Coef. de infiltracion (metodo coeficiente)")
    p_rec.add_argument("--escorrentia", type=float, default=0.1, help="Fraccion de escorrentia (metodo balance)")
    p_rec.add_argument("--k-percolacion", type=float, default=1.0,
                       help="Constante de percolacion 0-1 (diario): 1 = sin retardo, <1 difiere la recarga")
    p_rec.add_argument("--transiente", action="store_true",
                       help="Escribe tambien stress_periods.csv alineado (corre la serie como transiente)")
    p_rec.set_defaults(func=cmd_recarga)

    p_idx = sub.add_parser("indices", help="Indices clima-hidrogeologia (SPI/SPEI, aridez, recarga, flujo base, desfase napa-clima)")
    add_project(p_idx)
    p_idx.set_defaults(func=cmd_indices)

    p_prep = sub.add_parser("prep", help="Prepara tablas del modelo desde datos/fuente/ (DEM, shp, csv)")
    add_project(p_prep)
    p_prep.add_argument("--cellsize", type=float, default=100.0, help="Tamano de celda (m)")
    p_prep.add_argument("--nlay", type=int, default=1, help="Numero de capas")
    p_prep.add_argument("--espesor", type=float, default=50.0, help="Espesor del acuifero (m)")
    p_prep.set_defaults(func=cmd_prep)

    p_v3d = sub.add_parser("view3d", help="Exporta el modelo 3D a VTK (ParaView/PyVista) + PNG")
    add_project(p_v3d)
    p_v3d.add_argument("--exageration", type=float, default=20.0, help="Exageracion vertical")
    p_v3d.add_argument("--mesh", action="store_true",
                       help="Ver el modelo Voronoi/DISV (de 'mfw mesh --run') en vez del modelo regular")
    p_v3d.set_defaults(func=cmd_view3d)

    p_datos = sub.add_parser("datos", help="Asistente de datos: crea plantillas editables de lo que falta")
    add_project(p_datos)
    p_datos.set_defaults(func=cmd_datos)

    p_check = sub.add_parser("check", help="Revisa los insumos del proyecto (obligatorios/importantes/opcionales)")
    add_project(p_check)
    p_check.set_defaults(func=cmd_check)

    p_doc = sub.add_parser("doctor", help="Chequea el entorno (binarios y paquetes)")
    p_doc.set_defaults(func=cmd_doctor)

    p_onb = sub.add_parser("onboard", help="Pantalla de inicio guiada (estado del proyecto + siguiente paso)")
    add_project(p_onb)
    p_onb.set_defaults(func=cmd_onboard)

    # Alias historico: 'tui' hace lo mismo que 'onboard'.
    p_tui = sub.add_parser("tui", help="(alias de onboard)")
    add_project(p_tui)
    p_tui.set_defaults(func=cmd_onboard)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        # Sin subcomando: pantalla de inicio interactiva si hay terminal; si no, ayuda.
        if sys.stdin.isatty() and sys.stdout.isatty():
            from yaku.tui import run_home

            return run_home()
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
