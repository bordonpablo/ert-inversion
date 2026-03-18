"""
Clase Inversion: encapsula toda la lógica de procesamiento ERT.

Flujo:
    1. Parseo del .dat  → coordenadas absolutas + rhoa + chargeability
    2. Construcción del DataContainer de pyGIMLi
    3. Visualización inicial de electrodos
    4. Factores geométricos (analíticos, sin topo)
    5. Pseudosección de resistividad aparente
    6. Estimación de errores
    7. Inversión con ERTManager
    8. Visualización de resultados
"""

import logging
import os
from pathlib import Path

import matplotlib
matplotlib.use("Agg")   # backend no interactivo — evita bloqueos con Qt/Wayland
import matplotlib.pyplot as plt
import numpy as np
import pygimli as pg
from pygimli.physics import ert


class Inversion:
    def __init__(self, config: dict, output_dir: Path, logger: logging.Logger) -> None:
        self.config = config
        self.output_dir = Path(output_dir)
        self.logger = logger

    # ------------------------------------------------------------------
    # Orquestador principal
    # ------------------------------------------------------------------

    def run(self) -> None:
        dat_file = Path(self.config["data"]["path"])

        # 1. Parseo
        sensors, meas, meas_type, has_ip = self._parse_dat(dat_file)

        # 2. DataContainer
        data = self._build_data_container(sensors, meas, meas_type, has_ip)

        # 3. Electrodos
        self._plot_electrodes(data, dat_file)

        # 4. Factores geométricos
        self._compute_geometric_factors(data, meas_type)

        # 5. Pseudosección
        self._plot_pseudosection(data)

        # 6. Errores
        self._estimate_errors(data)

        # 7. Inversión
        mgr = self._run_inversion(data)

        # 8. Resultados
        self._plot_results(mgr)

    # ------------------------------------------------------------------
    # 1. Parseo del archivo .dat
    # ------------------------------------------------------------------

    def _parse_dat(self, filepath: Path):
        """
        Lee el archivo .dat (formato RES2DINV-like con coordenadas absolutas).

        Estructura del header (líneas 0-8):
            0: nombre del archivo
            1: espaciado mínimo de electrodos
            2-3: parámetros internos (tipo de array, etc.)
            4: descripción del tipo de dato
            5: tipo (0 = rhoa, 1 = resistencia)
            6: número de mediciones
            7: parámetro adicional
            8: flag de chargeability (0 = sin IP, 1 = con IP en mV/V)

        Si hay chargeability (línea 8 == 1), hay 3 líneas extra de cabecera:
            9:  nombre del parámetro IP (e.g. "Chargeability")
            10: unidad (e.g. "mV/V")
            11: ventana de integración (e.g. "0.06,0.5")
        Y los datos empiezan en línea 12 con 11 campos:
            4  x_A  z_A  x_B  z_B  x_M  z_M  x_N  z_N  rhoa  chargeability

        Sin chargeability los datos empiezan en línea 9 con 10 campos:
            4  x_A  z_A  x_B  z_B  x_M  z_M  x_N  z_N  valor
        """
        log = self.logger
        log.info("=" * 60)
        log.info("  Leyendo: %s", filepath.name)
        log.info("=" * 60)

        with open(filepath, "r", encoding="latin-1") as f:
            lines = [l.strip() for l in f.readlines()]

        meas_type  = int(lines[5])   # 0=rhoa, 1=resistencia
        n_data     = int(lines[6])
        has_ip     = int(lines[8])   # 0=sin IP, 1=con chargeability
        data_start = 12 if has_ip else 9
        n_fields   = 11 if has_ip else 10

        log.info("  Tipo de dato   : %s",
                 "resistividad aparente [Ohm·m]" if meas_type == 0 else "resistencia [Ohm]")
        log.info("  Mediciones     : %d", n_data)
        log.info("  Chargeability  : %s", "sí (mV/V)" if has_ip else "no")

        raw_meas = []
        for line in lines[data_start:]:
            parts = line.split()
            if len(parts) == n_fields and parts[0] == "4":
                xA, zA = float(parts[1]), float(parts[2])
                xB, zB = float(parts[3]), float(parts[4])
                xM, zM = float(parts[5]), float(parts[6])
                xN, zN = float(parts[7]), float(parts[8])
                val    = float(parts[9])
                ip     = float(parts[10]) if has_ip else None
                raw_meas.append(((xA, zA), (xB, zB), (xM, zM), (xN, zN), val, ip))

        if len(raw_meas) != n_data:
            log.warning("  ADVERTENCIA: se esperaban %d mediciones pero se parsearon %d",
                        n_data, len(raw_meas))

        # Posiciones únicas de electrodos ordenadas por x
        all_positions = set()
        for m in raw_meas:
            for pos in m[:4]:
                all_positions.add(pos)

        sensors = sorted(all_positions, key=lambda p: (p[0], p[1]))
        pos_to_idx = {p: i for i, p in enumerate(sensors)}

        spacings = np.unique(np.diff([s[0] for s in sensors]))
        log.info("  Electrodos     : %d", len(sensors))
        log.info("  Rango X        : %.1f m → %.1f m", sensors[0][0], sensors[-1][0])
        log.info("  Espaciado      : %s m", spacings)

        # Coordenadas a índices 0-based
        meas = []
        for (pA, pB, pM, pN, val, ip) in raw_meas:
            meas.append({
                "a":    pos_to_idx[pA],
                "b":    pos_to_idx[pB],
                "m":    pos_to_idx[pM],
                "n":    pos_to_idx[pN],
                "rhoa": val if meas_type == 0 else None,
                "r":    val if meas_type == 1 else None,
                "ip":   ip,
            })

        return sensors, meas, meas_type, has_ip

    # ------------------------------------------------------------------
    # 2. Construcción del DataContainer
    # ------------------------------------------------------------------

    def _build_data_container(self, sensors, meas, meas_type, has_ip):
        log = self.logger
        log.info("=" * 60)
        log.info("  Construyendo DataContainer")
        log.info("=" * 60)

        data = pg.DataContainerERT()

        data.registerSensorIndex("a")
        data.registerSensorIndex("b")
        data.registerSensorIndex("m")
        data.registerSensorIndex("n")

        for (x, z) in sensors:
            data.createSensor(pg.RVector3(x, 0.0, z))

        n = len(meas)
        data.resize(n)

        a_arr = np.array([m["a"] for m in meas], dtype=float)
        b_arr = np.array([m["b"] for m in meas], dtype=float)
        m_arr = np.array([m["m"] for m in meas], dtype=float)
        n_arr = np.array([m["n"] for m in meas], dtype=float)

        data["a"] = pg.Vector(a_arr)
        data["b"] = pg.Vector(b_arr)
        data["m"] = pg.Vector(m_arr)
        data["n"] = pg.Vector(n_arr)

        if meas_type == 0:
            data["rhoa"] = pg.Vector(np.array([m["rhoa"] for m in meas], dtype=float))
        else:
            data["r"] = pg.Vector(np.array([m["r"] for m in meas], dtype=float))

        if has_ip:
            data["ip"] = pg.Vector(np.array([m["ip"] for m in meas], dtype=float))

        if meas_type == 0:
            data.markValid(data["rhoa"] > 0)
        else:
            data.markValid(data["r"] > 0)

        log.info("  %s", data)
        return data

    # ------------------------------------------------------------------
    # 3. Visualización inicial de electrodos
    # ------------------------------------------------------------------

    def _plot_electrodes(self, data, dat_file: Path) -> None:
        fig, ax = plt.subplots(figsize=(12, 2))
        ax.plot(pg.x(data), pg.z(data), "k|", markersize=14, markeredgewidth=1.5)
        ax.set_xlabel("x [m]")
        ax.set_ylabel("z [m]")
        ax.set_title(f"Posición de electrodos — {dat_file.name}")
        ax.set_ylim(-1, 3)
        plt.tight_layout()
        out = self.output_dir / "01_electrodos.png"
        plt.savefig(out, dpi=150)
        plt.close("all")
        self.logger.info("  Figura guardada: %s", out.name)

    # ------------------------------------------------------------------
    # 4. Factores geométricos
    # ------------------------------------------------------------------

    def _compute_geometric_factors(self, data, meas_type: int) -> None:
        log = self.logger
        log.info("=" * 60)
        log.info("  Calculando factores geométricos (analítico, sin topo)")
        log.info("=" * 60)

        data["k"] = ert.createGeometricFactors(data)

        if meas_type == 0:
            data["r"] = data["rhoa"] / data["k"]
            log.info("  r = rhoa / k  (calculado)")
        else:
            data["rhoa"] = data["r"] * data["k"]
            log.info("  rhoa = r * k  (calculado)")

    # ------------------------------------------------------------------
    # 5. Pseudosección de resistividad aparente
    # ------------------------------------------------------------------

    def _plot_pseudosection(self, data) -> None:
        self.logger.info("  Mostrando pseudosección de rhoa...")
        fig_ps, ax_ps = plt.subplots(figsize=(12, 5))
        data.show(ax=ax_ps)
        ax_ps.set_title("Pseudosección — resistividad aparente [Ohm·m]")
        plt.tight_layout()
        out = self.output_dir / "02_pseudoseccion.png"
        plt.savefig(out, dpi=150)
        plt.close("all")
        self.logger.info("  Figura guardada: %s", out.name)

    # ------------------------------------------------------------------
    # 6. Estimación de errores
    # ------------------------------------------------------------------

    def _estimate_errors(self, data) -> None:
        log = self.logger
        log.info("=" * 60)
        log.info("  Estimando errores")
        log.info("=" * 60)

        rel_error   = self.config["error"]["rel_error"]
        abs_u_error = self.config["error"]["abs_u_error"]
        data.estimateError(relativeError=rel_error, absoluteUError=abs_u_error)

        _ = data.show(data["err"] * 100, label="Error estimado [%]")
        out = self.output_dir / "03_errores.png"
        plt.savefig(out, dpi=150)
        plt.close("all")
        log.info("  Figura guardada: %s", out.name)

    # ------------------------------------------------------------------
    # 7. Inversión
    # ------------------------------------------------------------------

    def _run_inversion(self, data):
        log = self.logger
        log.info("=" * 60)
        log.info("  Iniciando inversión ERT")
        log.info("=" * 60)

        mesh_cfg = self.config["mesh"]
        inv_cfg  = self.config["inversion"]

        mgr = ert.ERTManager(data)
        mgr.invert(
            data,
            lam             = inv_cfg["lambda"],
            verbose         = True,
            paraDX          = mesh_cfg["para_dx"],
            paraMaxCellSize = mesh_cfg["para_max_cell_size"],
            paraDepth       = mesh_cfg["para_depth"],
            quality         = mesh_cfg["quality"],
        )
        return mgr

    # ------------------------------------------------------------------
    # 8. Resultados
    # ------------------------------------------------------------------

    def _plot_results(self, mgr) -> None:
        log = self.logger
        log.info("=" * 60)
        log.info("  Visualizando resultados")
        log.info("=" * 60)

        mod = mgr.model

        # Resultado + ajuste
        _ = mgr.showResultAndFit()
        out = self.output_dir / "04_resultado_y_ajuste.png"
        plt.savefig(out, dpi=150)
        plt.close("all")
        log.info("  Figura guardada: %s", out.name)

        # Modelo solo con escala personalizada
        ax, cb = mgr.showResult(
            mod,
            cMin     = 10,
            cMax     = 5000,
            cMap     = "Spectral_r",
            logScale = True,
        )
        ax.set_title("Modelo de resistividad")
        ax.set_xlabel("Distancia [m]")
        ax.set_ylabel("Profundidad [m]")
        plt.tight_layout()
        out = self.output_dir / "05_modelo_resistividad.png"
        plt.savefig(out, dpi=150)
        plt.close("all")
        log.info("  Figura guardada: %s", out.name)

        # Resumen estadístico
        log.info("")
        log.info("  chi² final  : %.4f  (ideal ≈ 1.0)", mgr.inv.chi2())
        log.info("  RMS relativo: %.4f", mgr.inv.relrms())
        log.info("")
        log.info("  Figuras guardadas en: %s", self.output_dir.resolve())
