"""Tests del cargador de configuracion de proyecto."""

from mfworkflow.config import load_config


def test_demo_config_carga_y_valida(demo_config):
    cfg = load_config(demo_config)
    assert cfg.proyecto["nombre"] == "caso_demo"
    assert cfg.motor == "simple"
    assert cfg.perfil_informe == "astm"
    # rutas resueltas relativas al proyecto
    assert cfg.datos_dir.name == "tablas"
    assert cfg.datos_dir.exists()
    assert cfg.validate() == []


def test_motor_invalido_da_error(demo_config, tmp_path):
    cfg = load_config(demo_config)
    cfg.raw["motor"] = "inexistente"
    assert any("motor invalido" in e for e in cfg.validate())
