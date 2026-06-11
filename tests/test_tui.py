"""Tests de la terminal guiada (mfw tui).

No prueban la interaccion real; verifican el armado de etapas/namespace y que el
bucle principal salga limpio cuando el usuario elige salir (input mockeado).
"""

import builtins

from yaku import tui


def test_ns_tiene_defaults():
    ns = tui._ns("examples/caso_demo")
    assert ns.project == "examples/caso_demo"
    # defaults usados por los cmd_* de la CLI
    assert ns.perfil is None and ns.nlay == 1 and ns.engine == "pestpp-glm"
    # override
    ns2 = tui._ns("p", nlay=3, mesh=True)
    assert ns2.nlay == 3 and ns2.mesh is True


def test_build_stages_cubre_etapas_clave():
    stages = tui._build_stages()
    claves = {s["k"] for s in stages}
    for esperada in {"doctor", "prep", "build", "run", "calibrate", "report", "pipeline"}:
        assert esperada in claves
    # cada etapa trae titulo, descripcion, datos y runner callable
    for s in stages:
        assert s["t"] and s["d"] and s["datos"] and callable(s["run"])


def test_estado_entorno_lista_componentes():
    filas = tui._estado_entorno()
    nombres = {n for n, _, _ in filas}
    assert "flopy" in nombres and "mf6" in nombres
    assert all(isinstance(ok, bool) for _, ok, _ in filas)


def test_run_tui_sale_limpio(monkeypatch):
    # El usuario "no elige proyecto": run_tui debe terminar con 0 sin reventar.
    monkeypatch.setattr(builtins, "input", lambda *a, **k: "")
    monkeypatch.setattr(tui, "_seleccionar_proyecto", lambda ui, ini: None)
    assert tui.run_tui() == 0


def test_menu_salir_inmediato(monkeypatch):
    # Con un proyecto dado, elegir 'q' sale del menu sin ejecutar etapas.
    monkeypatch.setattr(builtins, "input", lambda *a, **k: "q")
    ui = tui.UI()
    stages = tui._build_stages()
    # no debe lanzar excepcion
    tui._menu(ui, "examples/caso_demo", stages)


def test_estado_proyecto_devuelve_sugerencia():
    estado, sugerencia = tui._estado_proyecto("examples/caso_demo")
    assert any("Insumos" in linea for linea in estado)
    assert isinstance(sugerencia, str) and sugerencia  # siempre sugiere un siguiente paso


def test_home_sale_limpio(monkeypatch):
    # Pantalla de inicio: elegir 0 (salir) retorna 0.
    monkeypatch.setattr(builtins, "input", lambda *a, **k: "0")
    assert tui.run_home() == 0


def test_home_abrir_proyecto(monkeypatch):
    # Opcion 2 (abrir existente) -> menu del proyecto -> 'q' -> 0 (salir home).
    respuestas = iter(["2", "q", "0"])
    monkeypatch.setattr(builtins, "input", lambda *a, **k: next(respuestas))
    monkeypatch.setattr(tui, "_seleccionar_proyecto", lambda ui, ini: "examples/caso_demo")
    assert tui.run_home() == 0
