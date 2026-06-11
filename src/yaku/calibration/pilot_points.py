#!/usr/bin/env python3
"""Calibracion por PILOT POINTS (pyemu) — parametrizacion espacial de K.

En vez de un multiplicador por zona/capa (pest_setup), aqui la K horizontal de una
capa se describe con una grilla de puntos piloto: PEST++ ajusta el valor en cada
punto y el campo K(x, y) se obtiene interpolando en log10 al centro de cada celda.
Es el salto de "calibracion por zonas" a un mapa de K continuo y defendible
(GMDSI / White et al.), manteniendo la arquitectura CSV del workflow:

    pilot_points.csv  (nombre, row, col, x, y, valor)   <- PEST escribe `valor`
    k_field_capa{N}.csv (nrow x ncol, sin encabezado)   <- lo consume el builder

Interpolacion: kriging ordinario (pyemu, variograma exponencial) si esta
disponible; si no, interpolacion lineal (scipy) con relleno por vecino cercano.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from yaku.calibration.pest_setup import (
    _apply_caudal_observation_data,
    _apply_observation_data,
    _write_instruction,
    _write_instruction_caudales,
)

try:
    import pyemu

    HAS_PYEMU = True
except Exception:  # pragma: no cover
    HAS_PYEMU = False

logger = logging.getLogger("yaku")


# Forward model usado por PEST++ con pilot points. Rutas inyectadas al generar.
FORWARD_TEMPLATE_PP = '''#!/usr/bin/env python3
"""Forward model de PEST++ con pilot points (generado por yaku). No editar a mano."""

from __future__ import annotations

import shutil
from pathlib import Path

import flopy
import pandas as pd

from yaku.builder import ModflowModelBuilder
from yaku.calibration.pilot_points import aplicar_pilot_points

PEST_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(r"{data_dir}")
OBS_FILE = Path(r"{obs_file}")
CAPA = {capa}
RUN_DIR = PEST_DIR / "model_run"
RUN_DATA = RUN_DIR / "datos"
RUN_MODEL = RUN_DIR / "modelo"
PP_FILE = PEST_DIR / "pilot_points.csv"
OUT_FILE = PEST_DIR / "simulados_pest.csv"
AFOROS = r"{aforos_file}"
MODEL_NAME = "pest_model"


def main():
    if RUN_DIR.exists():
        shutil.rmtree(RUN_DIR)
    shutil.copytree(DATA_DIR, RUN_DATA)
    RUN_MODEL.mkdir(parents=True, exist_ok=True)

    # Pilot points (PEST escribio `valor`) -> campo K distribuido de la capa
    aplicar_pilot_points(RUN_DATA, PP_FILE, capa=CAPA)

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

    # Multi-objetivo: caudal base simulado (SFR/RIV) contra aforos
    if AFOROS:
        from yaku.calibration.caudales import escribir_simulados_caudal

        escribir_simulados_caudal(RUN_MODEL / f"{{MODEL_NAME}}.cbc", pd.read_csv(AFOROS),
                                  PEST_DIR / "simulados_caudal.csv")


if __name__ == "__main__":
    main()
'''


def _leer_parametros(data_dir: Path) -> dict[str, float]:
    frame = pd.read_csv(Path(data_dir) / "parametros_modelo.csv")
    return {str(row["clave"]): float(row["valor"]) for _, row in frame.iterrows()}


def generar_pilot_points(data_dir: Path, *, cada: int = 5, valor_inicial: float | None = None) -> pd.DataFrame:
    """Grilla regular de pilot points (uno cada `cada` celdas) sobre el dominio.

    `valor_inicial` por defecto es la K de parametros_modelo.csv, de modo que la
    corrida base reproduzca el modelo sin calibrar.
    """
    params = _leer_parametros(data_dir)
    nrow, ncol = int(params["nrow"]), int(params["ncol"])
    delr, delc = float(params["delr"]), float(params["delc"])
    if valor_inicial is None:
        valor_inicial = float(params.get("k", 1.0))
    cada = max(1, int(cada))

    filas = list(range(cada // 2, nrow, cada)) or [nrow // 2]
    cols = list(range(cada // 2, ncol, cada)) or [ncol // 2]
    rows = []
    i = 0
    for r in filas:
        for c in cols:
            rows.append({
                "nombre": f"ppk_{i:03d}",
                "row": r,
                "col": c,
                # Centro de celda en coordenadas locales de la grilla (y crece hacia abajo en row)
                "x": (c + 0.5) * delr,
                "y": (nrow - r - 0.5) * delc,
                "valor": float(valor_inicial),
            })
            i += 1
    return pd.DataFrame(rows)


def interpolar_a_grilla(pp: pd.DataFrame, nrow: int, ncol: int, delr: float, delc: float,
                        *, metodo: str = "auto") -> np.ndarray:
    """Interpola los pilot points (en log10) al centro de cada celda -> array (nrow, ncol).

    metodo: 'kriging' (pyemu, variograma exponencial), 'lineal' (scipy) o 'auto'
    (kriging si pyemu esta disponible; si falla, lineal).
    """
    xc = (np.arange(ncol) + 0.5) * delr
    yc = (nrow - np.arange(nrow) - 0.5) * delc
    XX, YY = np.meshgrid(xc, yc)

    logv = np.log10(pp["valor"].astype(float).to_numpy())
    px = pp["x"].astype(float).to_numpy()
    py = pp["y"].astype(float).to_numpy()

    if len(pp) == 1:
        return np.full((nrow, ncol), float(pp["valor"].iloc[0]))

    if metodo in ("kriging", "auto") and HAS_PYEMU:
        try:
            return _kriging_pyemu(px, py, logv, XX, YY)
        except Exception as exc:  # noqa: BLE001
            if metodo == "kriging":
                raise
            logger.warning("Kriging pyemu fallo (%s); se usa interpolacion lineal.", exc)

    from scipy.interpolate import griddata

    pts = np.column_stack([px, py])
    try:
        grid = griddata(pts, logv, (XX, YY), method="linear")
    except Exception:  # noqa: BLE001  # puntos colineales o muy pocos: QHull no triangula
        grid = np.full(XX.shape, np.nan)
    # Fuera del casco convexo de los puntos (o si no hubo triangulacion):
    # vecino mas cercano, sin extrapolar locuras
    faltan = np.isnan(grid)
    if faltan.any():
        grid[faltan] = griddata(pts, logv, (XX[faltan], YY[faltan]), method="nearest")
    return 10.0 ** grid


def _kriging_pyemu(px, py, logv, XX, YY) -> np.ndarray:
    """Kriging ordinario con pyemu sobre los centros de celda (valores en log10)."""
    rango = max(XX.max() - XX.min(), YY.max() - YY.min()) / 3.0
    vario = pyemu.geostats.ExpVario(contribution=float(np.var(logv)) or 1.0, a=rango)
    gs = pyemu.geostats.GeoStruct(variograms=[vario], nugget=0.0)
    krige = pyemu.geostats.OrdinaryKrige(
        gs, pd.DataFrame({"name": [f"p{i}" for i in range(len(px))], "x": px, "y": py, "value": logv})
    )
    res = krige.calc_factors(XX.ravel(), YY.ravel(), num_threads=1)
    # res: DataFrame con inames/ifacts por punto de la grilla
    out = np.empty(XX.size)
    vals = pd.Series(logv, index=[f"p{i}" for i in range(len(px))])
    for j, (_, row) in enumerate(res.iterrows()):
        out[j] = float(np.dot(row["ifacts"], vals.loc[row["inames"]].to_numpy()))
    return 10.0 ** out.reshape(XX.shape)


def aplicar_pilot_points(data_dir: Path, pp_path: Path, *, capa: int = 1, metodo: str = "auto") -> Path:
    """Interpola pilot_points.csv y escribe datos/.../k_field_capa{capa}.csv para el builder."""
    data_dir = Path(data_dir)
    pp = pd.read_csv(pp_path)
    params = _leer_parametros(data_dir)
    nrow, ncol = int(params["nrow"]), int(params["ncol"])
    campo = interpolar_a_grilla(pp, nrow, ncol, float(params["delr"]), float(params["delc"]), metodo=metodo)
    out = data_dir / f"k_field_capa{int(capa)}.csv"
    pd.DataFrame(campo).to_csv(out, index=False, header=False)
    return out


def setup_pest_pilot_points(
    pest_dir: Path,
    datos_dir: Path,
    observations_path: Path,
    *,
    cada: int = 5,
    capa: int = 1,
    rango_factor: float = 100.0,
    noptmax: int = 2,
    engine: str = "pestpp-ies",
    aforos_path: Path | None = None,
) -> Path:
    """Genera el caso PEST++ con pilot points en pest_dir y devuelve la ruta del .pst.

    Cada pilot point es un parametro log-transformado con limites
    [k_inicial / rango_factor, k_inicial * rango_factor].
    """
    if not HAS_PYEMU:
        raise RuntimeError("pyemu no esta instalado (pip install pyemu).")

    pest_dir = Path(pest_dir)
    pest_dir.mkdir(parents=True, exist_ok=True)
    datos_dir = Path(datos_dir).resolve()
    observations_path = Path(observations_path).resolve()
    if aforos_path is None and (datos_dir / "aforos.csv").exists():
        aforos_path = datos_dir / "aforos.csv"
    aforos = pd.read_csv(aforos_path) if aforos_path is not None else None

    pp = generar_pilot_points(datos_dir, cada=cada)
    pp_path = pest_dir / "pilot_points.csv"
    tpl_path = pest_dir / "pilot_points.tpl"
    ins_path = pest_dir / "simulados_pest.ins"
    out_path = pest_dir / "simulados_pest.csv"
    pst_path = pest_dir / "calibracion_pp.pst"

    pp.to_csv(pp_path, index=False)
    # Template: PEST reemplaza la columna `valor` de cada pilot point
    tpl_lines = ["ptf ~", "nombre,row,col,x,y,valor"]
    for _, row in pp.iterrows():
        tpl_lines.append(f"{row['nombre']},{int(row['row'])},{int(row['col'])},"
                         f"{float(row['x']):.3f},{float(row['y']):.3f},~ {row['nombre']:<14} ~")
    tpl_path.write_text("\n".join(tpl_lines) + "\n", encoding="utf-8")

    observations = pd.read_csv(observations_path)
    obs_names = _write_instruction(observations, ins_path, out_path)

    ins_files = [str(ins_path)]
    out_files = [str(out_path)]
    obs_names_caudal: list[str] = []
    if aforos is not None and not aforos.empty:
        ins_caudal = pest_dir / "simulados_caudal.ins"
        out_caudal = pest_dir / "simulados_caudal.csv"
        obs_names_caudal = _write_instruction_caudales(aforos, ins_caudal, out_caudal)
        ins_files.append(str(ins_caudal))
        out_files.append(str(out_caudal))

    (pest_dir / "forward_run.py").write_text(
        FORWARD_TEMPLATE_PP.format(
            data_dir=str(datos_dir),
            obs_file=str(observations_path),
            capa=int(capa),
            aforos_file=str(aforos_path.resolve()) if aforos_path is not None else "",
        ),
        encoding="utf-8",
    )

    pst = pyemu.Pst.from_io_files(
        tpl_files=[str(tpl_path)],
        in_files=[str(pp_path)],
        ins_files=ins_files,
        out_files=out_files,
        pst_filename=str(pst_path),
    )

    par = pst.parameter_data
    for _, row in pp.iterrows():
        name = str(row["nombre"]).lower()
        if name not in par.index:
            continue
        k0 = float(row["valor"])
        par.loc[name, "parval1"] = k0
        par.loc[name, "parlbnd"] = k0 / rango_factor
        par.loc[name, "parubnd"] = k0 * rango_factor
        par.loc[name, "partrans"] = "log"
        par.loc[name, "pargp"] = f"k_pp_capa{int(capa)}"

    _apply_observation_data(pst, observations, obs_names)
    if aforos is not None and obs_names_caudal:
        _apply_caudal_observation_data(pst, aforos, obs_names_caudal)

    pst.model_command = "python forward_run.py"
    pst.control_data.noptmax = int(noptmax)
    pst.write(str(pst_path), version=2)

    readme = [
        f"PEST++ con PILOT POINTS preparado (motor sugerido: {engine})",
        f"Pilot points (parametros K, capa {capa}): {len(pp)}  (uno cada {cada} celdas)",
        f"Observaciones: {len(observations)}",
        f"Control file: {pst_path.name}",
        f"Ejecutar desde {pest_dir} (con el entorno activado):",
        f"  {engine} {pst_path.name}",
        "",
        "El campo K calibrado queda en model_run/datos/k_field_capa{capa}.csv;",
        "copialo a datos/tablas/ del proyecto para que `yaku run` lo use.",
    ]
    (pest_dir / "README_PEST.txt").write_text("\n".join(readme) + "\n", encoding="utf-8")
    logger.info("Caso PEST++ pilot points: %d parametros, %d observaciones.", len(pp), len(observations))
    return pst_path
