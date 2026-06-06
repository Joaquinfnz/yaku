#!/usr/bin/env python3
"""Setup de calibracion formal PEST++ / pyEMU por proyecto (Etapas 4-6 ASTM).

Parametriza los CSV de entrada (definidos en parametros_calibracion.csv) en vez de
los arrays internos de MODFLOW: cada parametro es un valor por capa/zona o un
multiplicador global. El forward model reconstruye el modelo desde los CSV con
ModflowModelBuilder. Soporta motores:

    pestpp-glm  estimacion determinista (gradiente) + sensibilidad.
    pestpp-ies  ensemble (history matching) + cuantificacion de incertidumbre.

Migrado y generalizado desde 08_calibracion/preparar_pest.py (que producia una
corrida PEST++ real). A diferencia del original, el forward_run importa el motor
desde el paquete instalado (sin hacks de sys.path).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pandas as pd

try:
    import pyemu

    HAS_PYEMU = True
except Exception:  # pragma: no cover
    HAS_PYEMU = False


# Forward model usado por PEST++. Las rutas del proyecto se inyectan al generar.
FORWARD_TEMPLATE = '''#!/usr/bin/env python3
"""Forward model de PEST++ (generado por mfworkflow). No editar a mano."""

from __future__ import annotations

import shutil
from pathlib import Path

import flopy
import pandas as pd

from mfworkflow.builder import ModflowModelBuilder

PEST_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(r"{data_dir}")
OBS_FILE = Path(r"{obs_file}")
CALIB_FILE = Path(r"{calib_file}")
RUN_DIR = PEST_DIR / "model_run"
RUN_DATA = RUN_DIR / "datos"
RUN_MODEL = RUN_DIR / "modelo"
PARAM_FILE = PEST_DIR / "parametros_pest.csv"
OUT_FILE = PEST_DIR / "simulados_pest.csv"
MODEL_NAME = "pest_model"


def apply_parameter(data_dir, definition, value):
    path = data_dir / str(definition["archivo"])
    field = str(definition["campo"])
    selector = str(definition["selector"])
    kind = str(definition["tipo"])
    frame = pd.read_csv(path)
    if selector == "all":
        mask = pd.Series(True, index=frame.index)
    elif "=" in selector:
        key, raw = selector.split("=", 1)
        mask = frame[key.strip()].astype(str) == raw.strip()
    else:
        raise ValueError(f"Selector no soportado: {{selector}}")
    if kind == "multiplicador":
        frame.loc[mask, field] = frame.loc[mask, field].astype(float) * value
    elif kind == "valor_capa":
        frame.loc[mask, field] = value
    else:
        raise ValueError(f"Tipo no soportado: {{kind}}")
    frame.to_csv(path, index=False)


def main():
    if RUN_DIR.exists():
        shutil.rmtree(RUN_DIR)
    shutil.copytree(DATA_DIR, RUN_DATA)
    RUN_MODEL.mkdir(parents=True, exist_ok=True)

    definitions = pd.read_csv(CALIB_FILE).set_index("nombre")
    for _, row in pd.read_csv(PARAM_FILE).iterrows():
        name = str(row["nombre"])
        apply_parameter(RUN_DATA, definitions.loc[name], float(row["valor"]))

    builder = ModflowModelBuilder(data_dir=RUN_DATA, workspace=RUN_MODEL, model_name=MODEL_NAME)
    builder.run_simulation(builder.build_simulation())

    observations = pd.read_csv(OBS_FILE)
    hds = flopy.utils.HeadFile(str(RUN_MODEL / f"{{MODEL_NAME}}.hds"), precision="double")
    times = hds.get_times()
    head = hds.get_data(totim=times[-1]) if times else hds.get_data()
    rows = []
    for _, obs in observations.iterrows():
        rows.append({{
            "nombre": str(obs["nombre"]).lower(),
            "simulado_m": float(head[int(obs["layer"]) - 1, int(obs["row"]), int(obs["col"])]),
        }})
    pd.DataFrame(rows).to_csv(OUT_FILE, index=False, sep=" ")


if __name__ == "__main__":
    main()
'''


def _safe_obs_name(name: str) -> str:
    return str(name).strip().lower().replace(" ", "_")[:20]


def _safe_obs_names(names) -> list[str]:
    """Nombres de observacion seguros (<=20 chars) y UNICOS.

    El truncado a 20 chars puede colisionar (pozos con prefijo largo parecido); aqui
    se desambigua con un sufijo incremental para no perder observaciones en el .pst.
    """
    out: list[str] = []
    usados: set[str] = set()
    for raw in names:
        base = _safe_obs_name(raw)
        nombre = base
        i = 0
        while nombre in usados:
            i += 1
            sfx = f"_{i}"
            nombre = base[: 20 - len(sfx)] + sfx
        usados.add(nombre)
        out.append(nombre)
    return out


def _write_template(parameters: pd.DataFrame, tpl_path: Path, in_path: Path) -> None:
    tpl_lines = ["ptf ~", "nombre,valor"]
    in_lines = ["nombre,valor"]
    for _, row in parameters.iterrows():
        name = str(row["nombre"])
        tpl_lines.append(f"{name},~ {name:<18} ~")
        in_lines.append(f"{name},{float(row['valor_inicial']):.10g}")
    tpl_path.write_text("\n".join(tpl_lines) + "\n", encoding="utf-8")
    in_path.write_text("\n".join(in_lines) + "\n", encoding="utf-8")


def _write_instruction(observations: pd.DataFrame, ins_path: Path, out_path: Path) -> list[str]:
    obs_names = _safe_obs_names(observations["nombre"])
    ins_lines = ["pif ~", "l1"]
    out_lines = ["nombre simulado_m"]
    for obs_name, obs_value in zip(obs_names, observations["head_observado_m"]):
        ins_lines.append(f"l1 w !{obs_name}!")
        out_lines.append(f"{obs_name} {float(obs_value):.6f}")
    ins_path.write_text("\n".join(ins_lines) + "\n", encoding="utf-8")
    out_path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    return obs_names


def setup_pest(
    pest_dir: Path,
    datos_dir: Path,
    observations_path: Path,
    calib_params_path: Path,
    *,
    max_params: int = 2,
    noptmax: int = 2,
    engine: str = "pestpp-glm",
) -> Path:
    """Genera el caso PEST++ en pest_dir y devuelve la ruta del .pst."""
    if not HAS_PYEMU:
        raise RuntimeError("pyemu no esta instalado (pip install pyemu).")

    pest_dir = Path(pest_dir)
    pest_dir.mkdir(parents=True, exist_ok=True)
    datos_dir = Path(datos_dir).resolve()
    observations_path = Path(observations_path).resolve()
    calib_params_path = Path(calib_params_path).resolve()

    parameters = pd.read_csv(calib_params_path).head(max(1, int(max_params))).copy()
    observations = pd.read_csv(observations_path)

    tpl_path = pest_dir / "parametros_pest.tpl"
    in_path = pest_dir / "parametros_pest.csv"
    ins_path = pest_dir / "simulados_pest.ins"
    out_path = pest_dir / "simulados_pest.csv"
    pst_path = pest_dir / "calibracion.pst"

    _write_template(parameters, tpl_path, in_path)
    obs_names = _write_instruction(observations, ins_path, out_path)

    (pest_dir / "forward_run.py").write_text(
        FORWARD_TEMPLATE.format(
            data_dir=str(datos_dir),
            obs_file=str(observations_path),
            calib_file=str(calib_params_path),
        ),
        encoding="utf-8",
    )

    pst = pyemu.Pst.from_io_files(
        tpl_files=[str(tpl_path)],
        in_files=[str(in_path)],
        ins_files=[str(ins_path)],
        out_files=[str(out_path)],
        pst_filename=str(pst_path),
    )

    par = pst.parameter_data
    for _, row in parameters.iterrows():
        name = str(row["nombre"]).lower()
        if name not in par.index:
            continue
        par.loc[name, "parval1"] = float(row["valor_inicial"])
        par.loc[name, "parlbnd"] = float(row["limite_inferior"])
        par.loc[name, "parubnd"] = float(row["limite_superior"])
        par.loc[name, "partrans"] = "log" if str(row["transformacion"]).lower() == "log" else "none"
        par.loc[name, "pargp"] = "hidro"

    obs = pst.observation_data
    observations = observations.copy()
    observations["obsnme"] = obs_names
    for _, row in observations.iterrows():
        name = str(row["obsnme"]).lower()
        if name not in obs.index:
            continue
        grupo = str(row.get("grupo", "niveles"))
        # Validacion (split-sample): peso 0 -> no calibra, pero se computa y reporta
        # para verificar el modelo en datos no usados en el ajuste.
        peso = 0.0 if grupo.strip().lower() == "validacion" else float(row.get("peso", 1.0))
        obs.loc[name, "obsval"] = float(row["head_observado_m"])
        obs.loc[name, "weight"] = peso
        obs.loc[name, "obgnme"] = grupo

    pst.model_command = "python forward_run.py"
    pst.control_data.noptmax = int(noptmax)
    pst.write(str(pst_path), version=2)

    # Tablas de interfaz con rutas relativas (PEST++ corre desde pest_dir).
    (pest_dir / "calibracion.tplfile_data.csv").write_text(
        "pest_file,model_file\nparametros_pest.tpl,parametros_pest.csv\n", encoding="utf-8"
    )
    (pest_dir / "calibracion.insfile_data.csv").write_text(
        "pest_file,model_file\nsimulados_pest.ins,simulados_pest.csv\n", encoding="utf-8"
    )

    readme = [
        f"PEST++ preparado (motor sugerido: {engine})",
        f"Parametros ajustables: {len(parameters)}",
        f"Observaciones: {len(observations)}",
        f"Control file: {pst_path.name}",
        f"Ejecutar desde {pest_dir} (con el entorno activado):",
        f"  {engine} calibracion.pst",
    ]
    (pest_dir / "README_PEST.txt").write_text("\n".join(readme) + "\n", encoding="utf-8")
    return pst_path


def run_pest(pst_path: Path, engine: str = "pestpp-glm", timeout: int | None = None) -> bool:
    """Ejecuta PEST++ sobre el .pst. Devuelve True si el proceso retorna 0."""
    import logging

    logger = logging.getLogger("mfworkflow")
    pst_path = Path(pst_path)
    result = subprocess.run(
        [engine, pst_path.name],
        cwd=str(pst_path.parent),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        # Muestra el motivo en vez de obligar a abrir el .rec a mano.
        cola = (result.stderr or result.stdout or "").strip().splitlines()[-8:]
        logger.error("%s fallo (codigo %d). Ultimas lineas:\n%s",
                     engine, result.returncode, "\n".join(cola))
    return result.returncode == 0
