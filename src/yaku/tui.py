"""Terminal guiada de yaku (`yaku tui`).

Un menu interactivo que envuelve los subcomandos de la CLI para quien no se sabe
los comandos de memoria: detecta los proyectos, muestra el estado del entorno
(equivalente a `yaku doctor` en compacto), guia las etapas de modelacion en el
orden ASTM y, despues de cada accion, dice donde quedaron las salidas.

Diseno:
- No agrega dependencias: usa `rich` si esta instalado (paneles/tablas bonitas) y
  si no, cae a `print()` plano. La seleccion es siempre por numero (`input()`),
  para que funcione en cualquier terminal sin `questionary`/`prompt_toolkit`.
- No reimplementa logica: cada accion construye un `argparse.Namespace` y llama al
  `cmd_*` correspondiente de `yaku.cli`, asi la TUI y la CLI nunca divergen.
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

from yaku import __version__

# rich es opcional: si no esta, _Console cae a print() plano.
try:  # pragma: no cover - depende del entorno
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table

    _HAS_RICH = True
except Exception:  # pragma: no cover
    _HAS_RICH = False

try:  # questionary: menus con flechas (navegacion ↑↓) — opcional
    import questionary
    from questionary import Choice, Separator

    _HAS_QUESTIONARY = True
except Exception:  # pragma: no cover
    _HAS_QUESTIONARY = False


# ---------------------------------------------------------------------------
# Capa de salida (rich o plano)
# ---------------------------------------------------------------------------
class UI:
    """Envoltorio minimo: usa rich si esta disponible, si no print() plano."""

    def __init__(self) -> None:
        self.console = Console() if _HAS_RICH else None

    def print(self, *args) -> None:
        if self.console:
            self.console.print(*args)
        else:
            print(*[str(a) for a in args])

    def rule(self, titulo: str) -> None:
        if self.console:
            self.console.rule(f"[bold cyan]{titulo}")
        else:
            print(f"\n=== {titulo} ===")

    def panel(self, texto: str, titulo: str = "") -> None:
        if self.console:
            self.console.print(Panel(texto, title=titulo, border_style="cyan"))
        else:
            if titulo:
                print(f"\n[{titulo}]")
            print(texto)

    def ask(self, prompt: str) -> str:
        try:
            return input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            return "q"

    @property
    def interactivo(self) -> bool:
        """True si se puede usar questionary (flechas): hay questionary y terminal real."""
        return _HAS_QUESTIONARY and sys.stdin.isatty() and sys.stdout.isatty()

    def select(self, mensaje: str, opciones: list, *, default=None):
        """Menu de seleccion. `opciones` = lista de (etiqueta, valor) o Separator/None.

        Con questionary navega con flechas; si no, cae a una lista numerada (input).
        Devuelve el valor elegido, o None si se cancela.
        """
        if self.interactivo:
            choices = []
            for op in opciones:
                if op is None:
                    choices.append(Separator())
                elif isinstance(op, tuple):
                    choices.append(Choice(title=op[0], value=op[1]))
                else:  # Separator u objeto ya armado
                    choices.append(op)
            return questionary.select(mensaje, choices=choices, default=default,
                                      qmark="»", instruction="(↑↓ Enter)").ask()
        # Fallback numerado (tests / sin terminal)
        reales = [op for op in opciones if isinstance(op, tuple)]
        self.print("\n" + mensaje)
        for i, (etiqueta, _) in enumerate(reales, 1):
            self.print(f"  {i}. {etiqueta}")
        sel = self.ask("Elige (numero): ")
        if sel.isdigit() and 1 <= int(sel) <= len(reales):
            return reales[int(sel) - 1][1]
        return None

    def confirm(self, mensaje: str, *, default: bool = True) -> bool:
        if self.interactivo:
            return bool(questionary.confirm(mensaje, default=default).ask())
        r = self.ask(f"{mensaje} [{'S/n' if default else 's/N'}]: ").lower()
        return default if not r else r.startswith("s")

    def text(self, mensaje: str, *, default: str = "") -> str:
        if self.interactivo:
            return (questionary.text(mensaje, default=default).ask() or "").strip()
        return self.ask(f"{mensaje} ") or default


# ---------------------------------------------------------------------------
# Estado del entorno (doctor compacto)
# ---------------------------------------------------------------------------
def _estado_entorno() -> list[tuple[str, bool, str]]:
    """Devuelve [(componente, ok, detalle)] de binarios y paquetes clave."""
    from yaku.binaries import resolve_exe

    filas: list[tuple[str, bool, str]] = []
    binarios = {
        "mf6": "MODFLOW 6",
        "mp7": "MODPATH 7",
        "triangle": "mallas Voronoi",
        "pestpp-ies": "incertidumbre PEST++",
    }
    for exe, desc in binarios.items():
        p = resolve_exe(exe)
        filas.append((exe, bool(p), desc if p else f"{desc} (falta)"))
    for mod, desc in {"flopy": "nucleo", "pyemu": "calibracion",
                      "geopandas": "GIS", "reportlab": "informe PDF",
                      "pyvista": "3D"}.items():
        ok = importlib.util.find_spec(mod) is not None
        filas.append((mod, ok, desc if ok else f"{desc} (falta)"))
    return filas


def _mostrar_entorno(ui: UI) -> None:
    filas = _estado_entorno()
    if ui.console:
        tabla = Table(title="Entorno", show_header=True, header_style="bold")
        tabla.add_column("Componente")
        tabla.add_column("Estado")
        tabla.add_column("Para que")
        for nombre, ok, desc in filas:
            estado = "[green]OK[/green]" if ok else "[red]FALTA[/red]"
            tabla.add_row(nombre, estado, desc)
        ui.console.print(tabla)
    else:
        ui.print("Entorno:")
        for nombre, ok, desc in filas:
            ui.print(f"  [{'OK ' if ok else 'FALTA'}] {nombre:12s} {desc}")
    faltan = [n for n, ok, _ in filas if not ok]
    if faltan:
        ui.print(f"Sugerencia: faltan {', '.join(faltan)} -> revisa 'yaku doctor' / get-modflow :flopy")


# ---------------------------------------------------------------------------
# Seleccion de proyecto
# ---------------------------------------------------------------------------
def _seleccionar_proyecto(ui: UI, inicial: str | None) -> str | None:
    from yaku.cli import _listar_proyectos

    if inicial and (Path(inicial) / "config.yaml").exists() or (inicial and Path(inicial).name == "config.yaml"):
        return inicial

    proyectos = _listar_proyectos()
    if not proyectos:
        ui.print("No se detectaron proyectos (carpetas con config.yaml en proyectos/ o examples/).")
        return ui.text("Escribe la ruta a un proyecto (o Enter para crear uno con 'yaku new'):") or None

    opciones = []
    for p in proyectos:
        try:
            rel = p.relative_to(Path.cwd())
        except ValueError:
            rel = p
        opciones.append((str(rel), str(p)))
    opciones.append(("« cancelar", None))
    return ui.select("Elige un proyecto:", opciones)


# ---------------------------------------------------------------------------
# Construccion de Namespace y ejecucion de etapas
# ---------------------------------------------------------------------------
def _ns(project: str, **over) -> argparse.Namespace:
    """Namespace con los defaults de la CLI, sobreescribibles por etapa."""
    base = dict(
        project=project,
        skip_viz=False, skip_report=False, perfil=None,
        setup_pest=False, run=False, engine="pestpp-glm",
        max_params=2, noptmax=2, timeout=None,
        factor=1.5, uncertainty=0,
        direction="backward", aprox=False,
        cell_size=200.0, refine=6.0,
        cellsize=100.0, nlay=1, espesor=50.0,
        exageration=20.0, mesh=False,
    )
    base.update(over)
    return argparse.Namespace(**base)


def _salidas(ui: UI, project: str) -> None:
    """Lista informe(s) y figuras generadas del proyecto."""
    from yaku.config import resolve_project_config

    try:
        cfg = resolve_project_config(Path(project))
    except Exception:
        return
    inf = sorted(cfg.informe_dir.glob("*")) if cfg.informe_dir.exists() else []
    figs = sorted(cfg.resultados_dir.rglob("*.png")) if cfg.resultados_dir.exists() else []
    lineas = []
    if inf:
        lineas.append("Informe:")
        lineas += [f"  {p}" for p in inf]
    if figs:
        lineas.append(f"Figuras ({len(figs)}):")
        lineas += [f"  {p}" for p in figs[:8]]
        if len(figs) > 8:
            lineas.append(f"  ... y {len(figs) - 8} mas")
    if lineas:
        ui.panel("\n".join(lineas), titulo="Resultados disponibles")


def _estado_proyecto(project: str) -> tuple[list[str], str]:
    """Estado del proyecto (insumos / corrido / informe) y el siguiente paso sugerido."""
    from yaku.config import resolve_project_config
    from yaku.insumos import revisar_insumos

    lineas: list[str] = []
    try:
        cfg = resolve_project_config(Path(project))
    except Exception:  # noqa: BLE001
        return [], ""

    rep = revisar_insumos(cfg)
    ok_min = rep.ok_minimos
    hds = cfg.resultados_dir / f"{cfg.model_name}.hds"
    corrido = hds.exists()
    informes = [p for p in (cfg.informe_dir.glob("*.pdf") if cfg.informe_dir.exists() else [])]
    tiene_informe = bool(informes)

    def marca(ok):
        if ui_console_disponible():
            return "[green]OK[/green]" if ok else "[red]falta[/red]"
        return "OK" if ok else "falta"

    lineas.append(f"Insumos minimos: {marca(ok_min)}" + ("" if ok_min else f" (faltan: {', '.join(rep.faltan_para_correr)})"))
    lineas.append(f"Modelo corrido:  {marca(corrido)}")
    lineas.append(f"Informe:         {marca(tiene_informe)}")

    if not ok_min:
        sug = "Faltan insumos minimos -> 'Revisar insumos' y 'Preparar datos' (prep)."
    elif not corrido:
        sug = "Insumos listos -> corre el modelo: 'Pipeline completo' (o build + run)."
    elif not tiene_informe:
        sug = "Modelo corrido -> genera el 'Informe' o el paquete 'Entregables SEIA'."
    else:
        sug = "Todo listo. Mejora con 'Calibracion' y 'Prediccion', o revisa 'Ver resultados'."
    return lineas, sug


def ui_console_disponible() -> bool:
    return _HAS_RICH


# Cada etapa: (clave, titulo, descripcion, datos_requeridos, runner)
def _build_stages() -> list[dict]:
    from yaku import cli

    def run_doctor(ui, proj):
        return cli.cmd_doctor(_ns(proj))

    def run_check(ui, proj):
        return cli.cmd_check(_ns(proj))

    def run_datos(ui, proj):
        return cli.cmd_datos(_ns(proj))

    def run_prep(ui, proj):
        cs = ui.ask("  cellsize (m) [100]: ") or "100"
        nl = ui.ask("  n de capas [1]: ") or "1"
        return cli.cmd_prep(_ns(proj, cellsize=float(cs), nlay=int(nl)))

    def run_gis(ui, proj):
        return cli.cmd_gis(_ns(proj))

    def run_recarga(ui, proj):
        met = ui.ask("  Metodo (balance/coeficiente) [balance]: ").strip().lower() or "balance"
        return cli.cmd_recarga(_ns(proj, metodo=met, cc=100.0, coef_inf=0.15, escorrentia=0.1))

    def run_mesh(ui, proj):
        correr = (ui.ask("  Correr un DISV de prueba? [s/N]: ").lower() == "s")
        return cli.cmd_mesh(_ns(proj, run=correr))

    def run_build(ui, proj):
        return cli.cmd_build(_ns(proj))

    def run_run(ui, proj):
        sv = (ui.ask("  Omitir figuras (mas rapido)? [s/N]: ").lower() == "s")
        return cli.cmd_run(_ns(proj, skip_viz=sv))

    def run_calibrate(ui, proj):
        correr = (ui.ask("  Correr PEST++ (formal, lento)? [s/N]: ").lower() == "s")
        eng = "pestpp-ies" if correr and ui.ask("  Motor ies? [S/n]: ").lower() != "n" else "pestpp-glm"
        return cli.cmd_calibrate(_ns(proj, run=correr, engine=eng))

    def run_predict(ui, proj):
        unc = ui.ask("  N realizaciones de incertidumbre [0]: ") or "0"
        return cli.cmd_predict(_ns(proj, uncertainty=int(unc)))

    def run_pathlines(ui, proj):
        return cli.cmd_pathlines(_ns(proj))

    def run_transport(ui, proj):
        return cli.cmd_transport(_ns(proj))

    def run_salina(ui, proj):
        return cli.cmd_salina(_ns(proj))

    def run_view3d(ui, proj):
        m = (ui.ask("  Ver la malla Voronoi (--mesh) en vez del modelo? [s/N]: ").lower() == "s")
        return cli.cmd_view3d(_ns(proj, mesh=m))

    def run_report(ui, proj):
        perfil = ui.ask("  Perfil informe (astm/sea) [config]: ").lower() or None
        return cli.cmd_report(_ns(proj, perfil=perfil))

    def run_entregables(ui, proj):
        perfil = ui.ask("  Perfil informe (astm/sea) [config]: ").lower() or None
        return cli.cmd_entregables(_ns(proj, perfil=perfil))

    def run_pipeline(ui, proj):
        return cli.cmd_pipeline(_ns(proj))

    A = "A. Insumos y malla"
    B = "B. Modelo"
    C = "C. Calibracion e incertidumbre"
    D = "D. Procesos avanzados"
    E = "E. Resultados y entregables"
    return [
        {"k": "doctor", "paq": A, "t": "Revisar entorno", "d": "Chequea mf6, mp7, triangle, pestpp y paquetes.",
         "datos": "ninguno", "run": run_doctor},
        {"k": "datos", "paq": A, "t": "Asistente de datos", "d": "Crea plantillas editables de las tablas que faltan.",
         "datos": "—", "run": run_datos},
        {"k": "check", "paq": A, "t": "Revisar insumos", "d": "Lista obligatorios/importantes/opcionales y si estan.",
         "datos": "datos/ del proyecto", "run": run_check},
        {"k": "prep", "paq": A, "t": "Preparar datos", "d": "DEM + shapefiles + CSV crudos -> tablas del modelo.",
         "datos": "datos/fuente/ (dem.tif, dominio.shp, pozos.shp, caudales.csv)", "run": run_prep},
        {"k": "gis", "paq": A, "t": "Preproceso GIS", "d": "shapefile/GeoJSON -> tablas (grilla, pozos, rio).",
         "datos": "datos/gis/", "run": run_gis},
        {"k": "recarga", "paq": A, "t": "Recarga (clima)", "d": "clima.csv -> recarga por periodo (balance de suelo).",
         "datos": "datos/fuente/clima.csv", "run": run_recarga},
        {"k": "mesh", "paq": A, "t": "Malla Voronoi/DISV", "d": "Genera malla refinada en pozos (opcional: corre DISV).",
         "datos": "datos/gis/dominio.shp", "run": run_mesh},
        {"k": "build", "paq": B, "t": "Construir modelo", "d": "Arma el modelo MODFLOW 6 (etapa 3 ASTM).",
         "datos": "tablas minimas obligatorias", "run": run_build},
        {"k": "run", "paq": B, "t": "Correr simulacion", "d": "Construye y ejecuta MODFLOW 6 + postproceso.",
         "datos": "tablas minimas obligatorias", "run": run_run},
        {"k": "pipeline", "paq": B, "t": "Pipeline completo", "d": "build -> run -> report de una vez.",
         "datos": "tablas minimas obligatorias", "run": run_pipeline},
        {"k": "calibrate", "paq": C, "t": "Calibracion", "d": "Evalua ajuste (RMSE/MAE) y opcional PEST++.",
         "datos": "observaciones_nivel.csv + resultados de 'run'", "run": run_calibrate},
        {"k": "predict", "paq": C, "t": "Prediccion", "d": "Escenario con/sin proyecto + incertidumbre Monte Carlo.",
         "datos": "resultados de 'run'", "run": run_predict},
        {"k": "pathlines", "paq": D, "t": "Trayectorias", "d": "MODPATH 7 (zonas de captura) o aproximacion.",
         "datos": "resultados de 'run'", "run": run_pathlines},
        {"k": "transport", "paq": D, "t": "Transporte (GWT)", "d": "Transporte de solutos.",
         "datos": "resultados de 'run'", "run": run_transport},
        {"k": "salina", "paq": D, "t": "Intrusion salina", "d": "GWT + BUY (densidad).",
         "datos": "resultados de 'run'", "run": run_salina},
        {"k": "view3d", "paq": E, "t": "Ver en 3D", "d": "Exporta el modelo a VTK (ParaView) + PNG.",
         "datos": "resultados de 'run' (o malla)", "run": run_view3d},
        {"k": "report", "paq": E, "t": "Informe", "d": "Genera el informe PDF (perfil astm | sea).",
         "datos": "resultados de 'run'", "run": run_report},
        {"k": "entregables", "paq": E, "t": "Entregables SEIA", "d": "Arma la carpeta lista para el SEIA (pdf+figuras+tablas+modelo).",
         "datos": "resultados de 'run'", "run": run_entregables},
    ]


def _imprimir_menu(ui: UI, stages: list[dict]) -> None:
    """Imprime las etapas agrupadas por paquete, con numeración global."""
    paquete_actual = None
    if ui.console:
        tabla = Table(show_header=True, header_style="bold")
        tabla.add_column("#", justify="right")
        tabla.add_column("Etapa")
        tabla.add_column("Que hace")
        tabla.add_column("Datos que necesita", style="dim")
        for i, s in enumerate(stages, 1):
            if s["paq"] != paquete_actual:
                paquete_actual = s["paq"]
                tabla.add_section()
                tabla.add_row("", f"[bold cyan]{paquete_actual}[/bold cyan]", "", "")
            tabla.add_row(str(i), s["t"], s["d"], s["datos"])
        ui.console.print(tabla)
    else:
        for i, s in enumerate(stages, 1):
            if s["paq"] != paquete_actual:
                paquete_actual = s["paq"]
                ui.print(f"\n  -- {paquete_actual} --")
            ui.print(f"  {i:2d}. {s['t']:18s} {s['d']}  (datos: {s['datos']})")


def _puede_correr(ui: UI, project: str) -> bool:
    """Gate: avisa y bloquea si faltan las tablas minimas para modelar."""
    from yaku.config import resolve_project_config
    from yaku.insumos import revisar_insumos

    try:
        cfg = resolve_project_config(Path(project))
        faltan = revisar_insumos(cfg).faltan_para_correr
    except Exception as exc:  # noqa: BLE001
        ui.print(f"[red]No se pudo revisar insumos: {exc}[/red]" if ui.console else f"Error insumos: {exc}")
        return False
    if faltan:
        msg = ("Faltan tablas minimas para modelar: " + ", ".join(faltan) +
               ".\nUsa 'Revisar insumos' y 'Preparar datos' antes de construir/correr.")
        ui.print(f"[red]{msg}[/red]" if ui.console else msg)
        return False
    return True


def _menu(ui: UI, project: str, stages: list[dict]) -> None:
    try:
        rel = Path(project).resolve().relative_to(Path.cwd())
    except ValueError:
        rel = Path(project)
    while True:
        ui.rule(f"Proyecto: {rel}")
        estado, sugerencia = _estado_proyecto(project)
        if estado:
            ui.panel("\n".join(estado) + (f"\n\n=> Siguiente paso: {sugerencia}" if sugerencia else ""),
                     titulo="Estado del proyecto")

        # Menu de etapas agrupadas por paquete (navegacion con flechas) + acciones.
        opciones: list = []
        paq = None
        for s in stages:
            if s["paq"] != paq:
                paq = s["paq"]
                if ui.interactivo:
                    opciones.append(Separator(f"  {paq}"))
            opciones.append((s["t"], ("etapa", s)))
        if ui.interactivo:
            opciones.append(Separator(" "))
        opciones += [
            ("Cambiar de proyecto", ("accion", "cambiar")),
            ("Ver resultados", ("accion", "resultados")),
            ("Salir", ("accion", "salir")),
        ]
        elegido = ui.select("Elige una etapa o accion:", opciones)
        if elegido is None or elegido == ("accion", "salir"):
            return

        tipo, valor = elegido
        if tipo == "accion":
            if valor == "cambiar":
                nuevo = _seleccionar_proyecto(ui, None)
                if nuevo:
                    _menu(ui, nuevo, stages)
                return
            if valor == "resultados":
                _salidas(ui, project)
            continue

        etapa = valor
        # Gate de insumos: build/run/pipeline exigen las tablas minimas.
        if etapa["k"] in {"build", "run", "pipeline"} and not _puede_correr(ui, project):
            continue
        ui.rule(etapa["t"])
        ui.print(f"[dim]{etapa['d']}[/dim]" if ui.console else etapa["d"])
        try:
            rc = etapa["run"](ui, project)
            if rc == 0:
                ui.print("[green]OK[/green]" if ui.console else "OK")
                _salidas(ui, project)
            else:
                ui.print(f"[yellow]Termino con codigo {rc}[/yellow]" if ui.console
                         else f"Termino con codigo {rc}")
        except SystemExit as exc:
            ui.print(f"[red]No se pudo: faltan datos o config (codigo {exc.code}).[/red]"
                     if ui.console else f"No se pudo (codigo {exc.code}).")
        except Exception as exc:  # noqa: BLE001 - en TUI mostramos el error y seguimos
            ui.print(f"[red]Error: {exc}[/red]" if ui.console else f"Error: {exc}")


# ---------------------------------------------------------------------------
# Entrada
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Pantalla de inicio (logo + version + autor + menu principal)
# ---------------------------------------------------------------------------
_AUTOR = "Joaquín Fernández"

try:  # pyfiglet: titulo ASCII bonito (opcional)
    import pyfiglet  # noqa: F401
    _HAS_FIGLET = True
except Exception:  # pragma: no cover
    _HAS_FIGLET = False

# Montañita (simétrica) sobre la napa (~ aguas subterraneas) + lineas del banner.
_MONTANA = "\n".join([
    "      /\\",
    "     /  \\",
    "    / /\\ \\",
    "   /_/  \\_\\",
    " ≈≈≈≈≈≈≈≈≈≈≈≈≈",
])
_SUBTITULO = "Modelación de aguas subterráneas — MODFLOW 6 + FloPy"
_ECUACIONES = "q = -K·∇h      Ss·∂h/∂t = ∇·(K·∇h) + W"


def _titulo_ascii() -> str:
    """Titulo 'yaku' en ASCII (figlet 'slant' si esta pyfiglet; si no, texto simple)."""
    if _HAS_FIGLET:
        try:
            return pyfiglet.figlet_format("yaku", font="slant").rstrip("\n")
        except Exception:  # pragma: no cover
            pass
    return "m f w o r k f l o w"


def _banner(ui: UI) -> None:
    """Banner centrado: montañita sobre la napa + logo 'yaku' al medio + ecuaciones."""
    titulo = _titulo_ascii()
    version = f"v{__version__}   ·   Autor: {_AUTOR}"
    if ui.console:
        from rich.panel import Panel
        from rich.text import Text

        cuerpo = Text(justify="center")
        cuerpo.append(_MONTANA + "\n", style="green")
        cuerpo.append(titulo + "\n", style="bold cyan")
        cuerpo.append(_SUBTITULO + "\n", style="white")
        cuerpo.append(_ECUACIONES + "\n", style="cyan")
        cuerpo.append(version, style="dim")
        ui.console.print(Panel(cuerpo, border_style="cyan", title="yaku · onboard"))
    else:
        ui.print(_MONTANA)
        ui.print(titulo)
        ui.print(_SUBTITULO)
        ui.print(_ECUACIONES)
        ui.print(version)


def _crear_proyecto(ui: UI) -> str | None:
    """Crea un proyecto nuevo desde la plantilla y devuelve su ruta."""
    from yaku import cli

    nombre = ui.ask("  Nombre del proyecto nuevo (ej. mi_proyecto): ").strip()
    if not nombre:
        ui.print("Cancelado.")
        return None
    args = argparse.Namespace(nombre=nombre, dest="proyectos", autor=_AUTOR, fecha="", git=False)
    rc = cli.cmd_new(args)
    if rc != 0:
        return None
    proj = str(Path("proyectos") / nombre)
    ui.print(f"  Proyecto creado en {proj}. Pon tus datos en datos/fuente/ y usa 'Revisar insumos'.")
    return proj


def run_home() -> int:
    """Pantalla de inicio de yaku: banner + menu principal (nuevo / abrir / entorno)."""
    from yaku import cli

    ui = UI()
    stages = _build_stages()
    while True:
        _banner(ui)
        accion = ui.select("¿Qué quieres hacer?", [
            ("Crear un proyecto nuevo", "nuevo"),
            ("Abrir un proyecto existente", "abrir"),
            ("Revisar el entorno (yaku doctor)", "doctor"),
            ("Ver los comandos disponibles (ayuda)", "ayuda"),
            ("Salir", "salir"),
        ])
        if accion in (None, "salir"):
            ui.print("Hasta luego.")
            return 0
        if accion == "nuevo":
            proj = _crear_proyecto(ui)
            if proj:
                _menu(ui, proj, stages)
        elif accion == "abrir":
            proj = _seleccionar_proyecto(ui, None)
            if proj:
                _menu(ui, proj, stages)
        elif accion == "doctor":
            cli.cmd_doctor(argparse.Namespace())
        elif accion == "ayuda":
            cli.build_parser().print_help()


def run_tui(initial_project: str | None = None) -> int:
    ui = UI()
    ui.panel(
        "Terminal guiada de yaku.\n"
        "Te muestra el estado del entorno, eliges un proyecto y corres las etapas\n"
        "de modelacion en orden. Cada etapa dice que hace y que datos necesita.",
        titulo="yaku tui",
    )
    _mostrar_entorno(ui)
    project = _seleccionar_proyecto(ui, initial_project)
    if not project:
        ui.print("Sin proyecto. Crea uno con: yaku new <nombre>")
        return 0
    stages = _build_stages()
    _menu(ui, project, stages)
    ui.print("Listo.")
    return 0
