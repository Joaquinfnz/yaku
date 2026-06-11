#!/usr/bin/env python3
"""Condiciones de borde y forzantes (mixin del builder): CHD, WEL, RIV, DRN,
    GHB, EVT, SFR, UZF y recarga (uniforme, zonal o por periodos)."""

from __future__ import annotations

import logging
from pathlib import Path  # noqa: F401  (usado en anotaciones/typing de los metodos)

import flopy
import numpy as np
import pandas as pd

logger = logging.getLogger("yaku")


class BordesMixin:
    def build_chd_data(self, frame: pd.DataFrame, nrow: int, ncol: int, periods: list[int],
                       active: "np.ndarray | None" = None, nlay: int = 1) -> dict[int, list[list[object]]]:
        def on(r: int, c: int) -> bool:
            return active is None or active[r, c] == 1

        # Convencion de filas: row 0 = primera fila del arreglo (sur, y=miny; los plots
        # usan origin='lower'). Por eso 'superior' = row 0 e 'inferior' = ultima fila.
        # Es consistente en todo el stack (prep, gis, plots); se documenta para evitar
        # confusion al leer 'superior/inferior'. Recomendado usar izquierdo/derecho.
        chd_spd = {period: [] for period in periods}
        for _, row in frame.iterrows():
            side = str(row["lado"]).strip().lower()
            head = float(row["carga_m"])
            # 'layer = all' aplica la carga de borde a TODAS las capas (borde lateral
            # completo); si no, a la capa indicada (por defecto la 1).
            raw = str(row.get("layer", 1)).strip().lower()
            target_layers = list(range(nlay)) if raw in {"all", "*", "todas"} else [self.layer_target(row.get("layer", 1))]
            cells: list[list[object]] = []
            for layer in target_layers:
                if side == "izquierdo":
                    cells += [[(layer, r, 0), head] for r in range(nrow) if on(r, 0)]
                elif side == "derecho":
                    cells += [[(layer, r, ncol - 1), head] for r in range(nrow) if on(r, ncol - 1)]
                elif side == "superior":
                    cells += [[(layer, 0, c), head] for c in range(1, ncol - 1) if on(0, c)]
                elif side == "inferior":
                    cells += [[(layer, nrow - 1, c), head] for c in range(1, ncol - 1) if on(nrow - 1, c)]
                else:
                    raise ValueError(f"Lado no soportado en contornos_carga.csv: {side}")

            for period in self.stress_period_targets(row.get("stress_period"), periods):
                chd_spd[period].extend(cells)
        return chd_spd

    def build_wel_data(self, frame: pd.DataFrame | None, periods: list[int],
                       active: "np.ndarray | None" = None) -> dict[int, list[list[object]]]:
        wel_spd = {period: [] for period in periods}
        if frame is None:
            return wel_spd

        for _, row in frame.iterrows():
            r = self.row_target(row.get("row", 1))
            c = self.col_target(row.get("col", 1))
            if active is not None and active[r, c] == 0:
                logger.warning("pozos.csv: pozo en celda inactiva (row=%d, col=%d) omitido.", r + 1, c + 1)
                continue
            entry = [(self.layer_target(row.get("layer", 1)), r, c), float(row["rate_m3_dia"])]
            for period in self.stress_period_targets(row.get("stress_period"), periods):
                wel_spd[period].append(entry)
        return wel_spd

    def build_riv_data(self, frame: pd.DataFrame | None, periods: list[int],
                       active: "np.ndarray | None" = None) -> dict[int, list[list[object]]]:
        riv_spd = {period: [] for period in periods}
        if frame is None:
            return riv_spd

        for _, row in frame.iterrows():
            r = self.row_target(row.get("row", 1))
            c = self.col_target(row.get("col", 1))
            if active is not None and active[r, c] == 0:
                continue
            entry = [
                (self.layer_target(row.get("layer", 1)), r, c),
                float(row["stage_m"]),
                float(row["cond_m2_d"]),
                float(row["river_bottom_m"]),
            ]
            for period in self.stress_period_targets(row.get("stress_period"), periods):
                riv_spd[period].append(entry)
        return riv_spd

    def build_drn_data(self, frame: pd.DataFrame | None, periods: list[int],
                       active: "np.ndarray | None" = None) -> dict[int, list[list[object]]]:
        """Drenes (DRN): drenan agua solo cuando la napa supera la cota del dren.

        drn.csv: row, col, [layer], elev_m (cota del dren), cond_m2_d, [stress_period].
        Util para manantiales, drenes de mina, afloramientos y rebose de vegas/humedales.
        """
        drn_spd: dict[int, list] = {period: [] for period in periods}
        if frame is None:
            return drn_spd
        for _, row in frame.iterrows():
            r = self.row_target(row.get("row", 1))
            c = self.col_target(row.get("col", 1))
            if active is not None and active[r, c] == 0:
                continue
            entry = [(self.layer_target(row.get("layer", 1)), r, c),
                     float(row["elev_m"]), float(row["cond_m2_d"])]
            for period in self.stress_period_targets(row.get("stress_period"), periods):
                drn_spd[period].append(entry)
        return drn_spd

    def build_ghb_data(self, frame: pd.DataFrame | None, periods: list[int],
                       active: "np.ndarray | None" = None) -> dict[int, list[list[object]]]:
        """Borde de carga general (GHB): borde regional con conductancia (semi-permeable).

        ghb.csv: row, col, [layer], head_m (carga externa), cond_m2_d, [stress_period].
        Mas realista que CHD para representar el aporte/salida del acuifero regional.
        """
        ghb_spd: dict[int, list] = {period: [] for period in periods}
        if frame is None:
            return ghb_spd
        for _, row in frame.iterrows():
            r = self.row_target(row.get("row", 1))
            c = self.col_target(row.get("col", 1))
            if active is not None and active[r, c] == 0:
                continue
            entry = [(self.layer_target(row.get("layer", 1)), r, c),
                     float(row["head_m"]), float(row["cond_m2_d"])]
            for period in self.stress_period_targets(row.get("stress_period"), periods):
                ghb_spd[period].append(entry)
        return ghb_spd

    def add_evt(self, gwf, params: dict, periods: list[int], nrow: int, ncol: int) -> bool:
        """Evapotranspiracion freatica (EVT): descarga del acuifero cuando la napa es somera.

        evt_periodos.csv: stress_period, rate_m_d (ET maxima), extinction_depth_m. La superficie
        es el terreno (top_dem_grid o top). Es el mecanismo fisico de las vegas/bofedales/GDE:
        cuando la napa esta cerca de la superficie, el acuifero pierde agua por evapotranspiracion.
        Opt-in: solo si existe evt_periodos.csv.
        """
        frame = self.csv_if_exists("evt_periodos.csv")
        if frame is None:
            return False
        surface = self._dem_grid(nrow, ncol)
        surf_obj: object = surface if surface is not None else float(params["top"])
        rate = {period: 0.0 for period in periods}
        depth = {period: 2.0 for period in periods}
        for _, row in frame.iterrows():
            for period in self.stress_period_targets(row.get("stress_period"), periods):
                rate[period] = float(row["rate_m_d"])
                depth[period] = float(row.get("extinction_depth_m", 2.0))
        flopy.mf6.ModflowGwfevta(gwf, surface=surf_obj, rate=rate, depth=depth)
        logger.info("EVT (evapotranspiracion freatica) activada: ET maxima %.2g m/d, "
                    "profundidad de extincion %.1f m.", max(rate.values()), max(depth.values()))
        return True

    def build_sfr_data(self, frame: pd.DataFrame, params: dict,
                       periods: list[int], nrow: int, ncol: int,
                       active: "np.ndarray | None" = None) -> "dict | None":
        """Construye datos para el paquete SFR (Streamflow Routing).

        sfr.csv columnas: reach, row, col, length_m, mannings_n, upstream_width_m,
                           slope, stage_m, inflow_m3_d, [layer], [stress_period]

        Cada fila es un reach. Se numeran secuencialmente y se conectan
        aguas abajo (reach N desagua al reach N+1). El ultimo reach es outlet.

        Formato FloPy 3.10 packagedata (12 columnas):
          ifno, cellid, rlen, rwid, rgrd, rtp, rbth, rhk, man, ncon, ustrf, ndv
        perioddata usa setting name/value:
          [ifno, 'INFLOW'|'STAGE'|..., valor]
        """
        if frame is None:
            return None
        nreaches = len(frame)
        if nreaches == 0:
            return None

        reach_data = []
        for idx, row in frame.iterrows():
            r = self.row_target(row.get("row", 1))
            c = self.col_target(row.get("col", 1))
            layer = self.layer_target(row.get("layer", 1))
            if active is not None and active[r, c] == 0:
                logger.warning("sfr.csv: reach %d en celda inactiva omitido.", idx + 1)
                continue
            length = float(row.get("length_m", params.get("delr", 100.0)))
            mannings = float(row.get("mannings_n", 0.035))
            width = float(row.get("upstream_width_m", 5.0))
            slope_val = float(row.get("slope", 0.001))
            stage = float(row.get("stage_m", float(params.get("top", 50.0)) - 1.0))
            inflow = float(row.get("inflow_m3_d", 0.0))
            bed_k = float(row.get("bed_k_m_d", params.get("k", 1.0)))
            bed_thick = float(row.get("bed_thickness_m", 1.0))
            reach_data.append({
                "cellid": (layer, r, c),
                "rno": idx,
                "length": length,
                "mannings": mannings,
                "width": width,
                "slope": slope_val,
                "stage": stage,
                "inflow": inflow,
                "bed_k": bed_k,
                "bed_thick": bed_thick,
            })

        if not reach_data:
            return None

        # FloPy 3.10 SFR packagedata: 12 columnas
        # ifno, cellid, rlen, rwid, rgrd, rtp, rbth, rhk, man, ncon, ustrf, ndv
        # ncon = numero TOTAL de conexiones del reach (aguas arriba + aguas abajo).
        # Cadena lineal: extremos ncon=1, reaches intermedios ncon=2, reach unico=0.
        n = len(reach_data)
        package_data = []
        for i, rd in enumerate(reach_data):
            if n == 1:
                ncon = 0
            elif i == 0 or i == n - 1:
                ncon = 1
            else:
                ncon = 2
            package_data.append([
                rd["rno"], rd["cellid"], rd["length"], rd["width"],
                rd["slope"], rd["stage"], rd["bed_thick"], rd["bed_k"],
                rd["mannings"], ncon, 1.0, 0,
            ])

        # connectiondata: una fila por reach con TODAS sus conexiones.
        # Convencion MODFLOW 6: el reach conectado aguas abajo se escribe con
        # signo NEGATIVO (este reach descarga hacia el); aguas arriba positivo.
        # Las conexiones deben ser reciprocas o MF6 falla al armar IA/JA.
        # FloPy convierte 0-based -> 1-based (v>=0: v+1; v<0: v-1) preservando
        # el signo, asi que pasamos rno 0-based con la convencion de signo.
        connection_data = []
        for i, rd in enumerate(reach_data):
            conns = [rd["rno"]]
            if i > 0:
                conns.append(reach_data[i - 1]["rno"])      # aguas arriba (+)
            if i < n - 1:
                conns.append(-reach_data[i + 1]["rno"])     # aguas abajo (-)
            connection_data.append(conns)

        # perioddata: [[ifno, 'INFLOW', valor], [ifno, 'STAGE', valor], ...]
        sfr_spd = {}
        for period in periods:
            period_entries = []
            for i, row in frame.iterrows():
                sp_val = row.get("stress_period", "all")
                if sp_val == "all" or pd.isna(sp_val):
                    if reach_data[i]["inflow"] != 0.0:
                        period_entries.append([reach_data[i]["rno"], "INFLOW",
                                               reach_data[i]["inflow"]])
                    period_entries.append([reach_data[i]["rno"], "STAGE",
                                          reach_data[i]["stage"]])
                elif int(float(sp_val)) == period:
                    if reach_data[i]["inflow"] != 0.0:
                        period_entries.append([reach_data[i]["rno"], "INFLOW",
                                               reach_data[i]["inflow"]])
                    period_entries.append([reach_data[i]["rno"], "STAGE",
                                          reach_data[i]["stage"]])
            if period_entries:
                sfr_spd[period] = period_entries

        logger.info("SFR activado: %d reaches, %d periodos.", len(reach_data), len(sfr_spd))
        return {"package_data": package_data, "connection_data": connection_data,
                "stress_period_data": sfr_spd, "nreaches": len(reach_data)}

    def add_uzf(self, gwf, params: dict, periods: list[int],
                    nrow: int, ncol: int, nlay: int) -> bool:
            """Zona vadosa (UZF): infiltracion y ET desde la superficie con retardo.

            uzf.csv: row, col, [layer], landflag, ivertcon, surfdep_m, vks_m_d,
                      thtr, thts, thti, eps
            uzf_periodos.csv: stress_period, infiltration_m_d, pet_m_d,
                              et_extinction_depth_m, ext_water_content, ha, hroot, rootact

            UZF reemplaza RCH+EVT simple cuando esta presente. La capa superior debe ser
            convertible (icelltype=1).
            Formato FloPy 3.10: packagedata 10 columnas, perioddata 8 columnas.
            """
            uzf_cells = self.csv_if_exists("uzf.csv")
            if uzf_cells is None:
                return False

            # FloPy 3.10 UZF packagedata: 10 columnas
            # [ifno, cellid, landflag, ivertcon, surfdep, vks, thtr, thts, thti, eps]
            package_data = []
            for idx, row in uzf_cells.iterrows():
                # ifno 0-based: FloPy 3.10 suma 1 al escribir (-> 1-based en archivo).
                ifno = idx
                r = self.row_target(row.get("row", 1))
                c = self.col_target(row.get("col", 1))
                layer = self.layer_target(row.get("layer", 1))
                landflag = int(row.get("landflag", 1))
                ivertcon = int(row.get("ivertcon", 0))
                surfdep = float(row.get("surfdep_m", 0.0))
                vks_val = float(row.get("vks_m_d", 0.5))
                thtr_val = float(row.get("thtr", 0.05))
                thts_val = float(row.get("thts", 0.35))
                thti_val = float(row.get("thti", 0.20))
                eps_val = float(row.get("eps", 4.2))
                package_data.append([ifno, (layer, r, c), landflag, ivertcon,
                                     surfdep, vks_val, thtr_val, thts_val,
                                     thti_val, eps_val])

            nuzfcells = len(package_data)

            uzf_periodos = self.csv_if_exists("uzf_periodos.csv")
            if uzf_periodos is None:
                uzf_periodos = pd.DataFrame([{"stress_period": periods[0],
                                              "infiltration_m_d": params.get("recharge", 0.0005),
                                              "pet_m_d": 0.001,
                                              "et_extinction_depth_m": 2.0,
                                              "ext_water_content": 0.15,
                                              "ha": 0.0, "hroot": 0.0, "rootact": 0.0}])

            # perioddata: 8 columnas (simulate_et=True)
            # [ifno, finf, pet, extdp, extwc, ha, hroot, rootact]
            uzf_spd = {period: [] for period in periods}
            for _, prow in uzf_periodos.iterrows():
                target_periods = self.stress_period_targets(prow.get("stress_period"), periods)
                finf = float(prow.get("infiltration_m_d", params.get("recharge", 0.0005)))
                pet_val = float(prow.get("pet_m_d", 0.001))
                extdp = float(prow.get("et_extinction_depth_m", 2.0))
                extwc = float(prow.get("ext_water_content", 0.15))
                ha_val = float(prow.get("ha", 0.0))
                hroot_val = float(prow.get("hroot", 0.0))
                rootact_val = float(prow.get("rootact", 0.0))
                for period in target_periods:
                    for ifno in range(nuzfcells):  # 0-based (FloPy escribe 1-based)
                        uzf_spd[period].append([ifno, finf, pet_val, extdp, extwc,
                                                ha_val, hroot_val, rootact_val])

            # simulate_gwseep esta deprecado desde MF6 6.5.0 (usar DRN si se requiere
            # descarga a la superficie); se omite para evitar el warning.
            flopy.mf6.ModflowGwfuzf(
                gwf,
                simulate_et=True,
                nuzfcells=nuzfcells,
                packagedata=package_data,
                perioddata=uzf_spd,
            )

            logger.info("UZF activado: %d celdas, infiltracion base %.2g m/d.",
                        nuzfcells, finf)
            return True

    def _recarga_multiplicador(self, nrow: int, ncol: int) -> "np.ndarray | None":
        """Multiplicador de recarga por celda desde recarga_zonas.csv (coef. de infiltración).

        Distribuye la recarga segun el coeficiente de infiltracion de cada unidad geologica
        (rasterizado por `prep`). Se normaliza a media 1 sobre las celdas con dato, de modo que
        la recarga MEDIA de la cuenca se conserva y solo cambia su reparto espacial. Celdas sin
        unidad reciben la recarga media (multiplicador 1).
        """
        path = self.data_dir / "recarga_zonas.csv"
        if not path.exists():
            return None
        try:
            coef = pd.read_csv(path, header=None).to_numpy(dtype=float)
        except Exception:  # noqa: BLE001
            return None
        if coef.shape != (nrow, ncol):
            logger.warning("recarga_zonas.csv no calza con la grilla (%s vs %dx%d); recarga uniforme.",
                           coef.shape, nrow, ncol)
            return None
        valido = np.isfinite(coef) & (coef > 0)
        if not valido.any():
            return None
        media = float(coef[valido].mean())
        if media <= 0:
            return None
        return np.where(valido, coef / media, 1.0)

    def build_recharge_data(self, params: dict[str, float], periods: list[int]):
        frame = self.csv_if_exists("recarga_periodos.csv")
        mult = self._recarga_multiplicador(int(params["nrow"]), int(params["ncol"]))

        # Valor base (escalar) por periodo
        base = {period: float(params["recharge"]) for period in periods}
        if frame is not None:
            for _, row in frame.iterrows():
                for period in self.stress_period_targets(row.get("stress_period"), periods):
                    base[period] = float(row["recharge_m_d"])

        if mult is not None:                       # recarga distribuida por coef. de infiltracion
            logger.info("Recarga distribuida espacialmente por coef. de infiltracion (recarga_zonas.csv).")
            return {period: float(valor) * mult for period, valor in base.items()}
        if frame is None:                          # comportamiento previo: escalar uniforme
            return float(params["recharge"])
        return base                                # dict de escalares uniformes por periodo
