"""
Inversión ERT completa para archivo WS_3_20_cor.dat
Configuración Wenner-Schlumberger con roll-along
Sin topografía (z = 0 para todos los electrodos)
Incluye datos de chargeability (IP) en mV/V

Flujo:
    1. Parseo del .dat  → coordenadas absolutas + rhoa + chargeability
    2. Construcción del DataContainer de pyGIMLi
    3. Factores geométricos (analíticos, sin topo)
    4. Estimación de errores
    5. Inversión con ERTManager
    6. Visualización de resultados
"""

import os
import numpy as np
import matplotlib
matplotlib.use('Agg')   # non-interactive backend — avoids Qt/Wayland blocking
import matplotlib.pyplot as plt
import pygimli as pg
from pygimli.physics import ert


# ---------------------------------------------------------------------------
# CONFIGURACIÓN
# ---------------------------------------------------------------------------

DAT_FILE = os.path.join(os.path.dirname(__file__), '../data/greenland/WS_3_20_cor.dat')
IMG_DIR  = os.path.join(os.path.dirname(__file__), '../img')
os.makedirs(IMG_DIR, exist_ok=True)

# Parámetros de estimación de error
REL_ERROR    = 0.03    # 3 % error relativo
ABS_U_ERROR  = 5e-5   # umbral absoluto de voltaje

# Parámetros de la malla paramétrica
PARA_DX            = 0.3    # densidad horizontal relativa de celdas
PARA_MAX_CELL_SIZE = 10     # tamaño máximo de celda [m²]
PARA_DEPTH         = 40     # profundidad máxima de investigación [m]
QUALITY            = 33.6   # calidad de la triangulación (ángulo mínimo)

# Parámetros de inversión
LAMBDA = 20     # factor de regularización (mayor → más suave)


# ---------------------------------------------------------------------------
# 1. PARSEO DEL ARCHIVO .dat
# ---------------------------------------------------------------------------

def parse_dat(filepath):
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
    print(f"\n{'='*60}")
    print(f"  Leyendo: {os.path.basename(filepath)}")
    print(f"{'='*60}")

    with open(filepath, 'r', encoding='latin-1') as f:
        lines = [l.strip() for l in f.readlines()]

    meas_type   = int(lines[5])   # 0=rhoa, 1=resistencia
    n_data      = int(lines[6])
    has_ip      = int(lines[8])   # 0=sin IP, 1=con chargeability
    data_start  = 12 if has_ip else 9
    n_fields    = 11 if has_ip else 10

    print(f"  Tipo de dato   : {'resistividad aparente [Ohm·m]' if meas_type == 0 else 'resistencia [Ohm]'}")
    print(f"  Mediciones     : {n_data}")
    print(f"  Chargeability  : {'sí (mV/V)' if has_ip else 'no'}")

    raw_meas = []
    for line in lines[data_start:]:
        parts = line.split()
        if len(parts) == n_fields and parts[0] == '4':
            xA, zA = float(parts[1]), float(parts[2])
            xB, zB = float(parts[3]), float(parts[4])
            xM, zM = float(parts[5]), float(parts[6])
            xN, zN = float(parts[7]), float(parts[8])
            val     = float(parts[9])
            ip      = float(parts[10]) if has_ip else None
            raw_meas.append(((xA, zA), (xB, zB), (xM, zM), (xN, zN), val, ip))

    if len(raw_meas) != n_data:
        print(f"  ADVERTENCIA: se esperaban {n_data} mediciones pero se parsearon {len(raw_meas)}")

    # Extraer posiciones únicas de electrodos y ordenarlas por x
    all_positions = set()
    for m in raw_meas:
        for pos in m[:4]:
            all_positions.add(pos)

    sensors = sorted(all_positions, key=lambda p: (p[0], p[1]))
    pos_to_idx = {p: i for i, p in enumerate(sensors)}

    spacings = np.unique(np.diff([s[0] for s in sensors]))
    print(f"  Electrodos     : {len(sensors)}")
    print(f"  Rango X        : {sensors[0][0]:.1f} m → {sensors[-1][0]:.1f} m")
    print(f"  Espaciado      : {spacings} m")

    # Convertir coordenadas a índices 0-based
    meas = []
    for (pA, pB, pM, pN, val, ip) in raw_meas:
        meas.append({
            'a':    pos_to_idx[pA],
            'b':    pos_to_idx[pB],
            'm':    pos_to_idx[pM],
            'n':    pos_to_idx[pN],
            'rhoa': val if meas_type == 0 else None,
            'r':    val if meas_type == 1 else None,
            'ip':   ip,
        })

    return sensors, meas, meas_type, has_ip


# ---------------------------------------------------------------------------
# 2. CONSTRUCCIÓN DEL DataContainer
# ---------------------------------------------------------------------------

def build_data_container(sensors, meas, meas_type, has_ip=False):
    """
    Construye un pg.DataContainer con sensores e índices de electrodos.

    API relevante:
        data.registerSensorIndex('campo')       registra campo como índice de sensor
        data.createSensor(pg.RVector3(x,y,z))   agrega un electrodo
        data.resize(n)                           reserva n filas de datos
        data['campo'] = pg.Vector(arr)           asigna un campo vectorial
        data.markValid(condicion)                marca mediciones como válidas
    """
    print(f"\n{'='*60}")
    print(f"  Construyendo DataContainer")
    print(f"{'='*60}")

    data = pg.DataContainerERT()

    # Registrar a, b, m, n como índices de sensores
    # (pyGIMLi necesita saber cuáles campos son referencias a electrodos)
    data.registerSensorIndex('a')
    data.registerSensorIndex('b')
    data.registerSensorIndex('m')
    data.registerSensorIndex('n')

    # Cargar sensores (electrodos)
    # pg.RVector3(x, y, z): en perfiles 2D usamos y=0, z=elevación topográfica
    # Como no hay topografía → z=0 para todos
    for (x, z) in sensors:
        data.createSensor(pg.RVector3(x, 0.0, z))

    # Reservar espacio para todas las mediciones
    n = len(meas)
    data.resize(n)

    # Cargar arrays de índices y valores
    a_arr = np.array([m['a'] for m in meas], dtype=float)
    b_arr = np.array([m['b'] for m in meas], dtype=float)
    m_arr = np.array([m['m'] for m in meas], dtype=float)
    n_arr = np.array([m['n'] for m in meas], dtype=float)

    data['a'] = pg.Vector(a_arr)
    data['b'] = pg.Vector(b_arr)
    data['m'] = pg.Vector(m_arr)
    data['n'] = pg.Vector(n_arr)

    if meas_type == 0:
        rhoa_arr = np.array([m['rhoa'] for m in meas], dtype=float)
        data['rhoa'] = pg.Vector(rhoa_arr)
    else:
        r_arr = np.array([m['r'] for m in meas], dtype=float)
        data['r'] = pg.Vector(r_arr)

    # Cargar chargeability si está presente
    if has_ip:
        ip_arr = np.array([m['ip'] for m in meas], dtype=float)
        data['ip'] = pg.Vector(ip_arr)

    # Marcar como válidas las mediciones con valor positivo
    if meas_type == 0:
        data.markValid(data['rhoa'] > 0)
    else:
        data.markValid(data['r'] > 0)

    print(f"  {data}")
    return data


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

if __name__ == '__main__':

    # --- 1. Parseo ---
    sensors, meas, meas_type, has_ip = parse_dat(DAT_FILE)

    # --- 2. DataContainer ---
    data = build_data_container(sensors, meas, meas_type, has_ip)

    # --- 3. Visualización inicial: posición de electrodos ---
    fig, ax = plt.subplots(figsize=(12, 2))
    ax.plot(pg.x(data), pg.z(data), 'k|', markersize=14, markeredgewidth=1.5)
    ax.set_xlabel('x [m]')
    ax.set_ylabel('z [m]')
    ax.set_title(f'Posición de electrodos — {os.path.basename(DAT_FILE)}')
    ax.set_ylim(-1, 3)
    plt.tight_layout()
    plt.savefig(os.path.join(IMG_DIR, '01_electrodos.png'), dpi=150)
    plt.close('all')

    # --- 4. Factor geométrico ---
    # Sin topografía usamos la fórmula analítica (más rápido).
    # Con topografía usaríamos numerical=True (más preciso pero costoso).
    print(f"\n{'='*60}")
    print("  Calculando factores geométricos (analítico, sin topo)")
    print(f"{'='*60}")
    data['k'] = ert.createGeometricFactors(data)

    # Si el dato de entrada era rhoa, derivamos r = rhoa / k
    # Si era r directamente, lo usamos tal cual y calculamos rhoa = r * k
    if meas_type == 0:
        data['r'] = data['rhoa'] / data['k']
        print("  r = rhoa / k  (calculado)")
    else:
        data['rhoa'] = data['r'] * data['k']
        print("  rhoa = r * k  (calculado)")

    # --- 5. Pseudosección de resistividad aparente ---
    print("\n  Mostrando pseudosección de rhoa...")
    fig_ps, ax_ps = plt.subplots(figsize=(12, 5))
    data.show(ax=ax_ps)
    ax_ps.set_title('Pseudosección — resistividad aparente [Ohm·m]')
    plt.tight_layout()
    plt.savefig(os.path.join(IMG_DIR, '02_pseudoseccion.png'), dpi=150)
    plt.close('all')

    # --- 6. Estimación de errores ---
    # relativeError : fracción relativa del dato (3 % → 0.03)
    # absoluteUError: umbral de voltaje absoluto para datos pequeños [V]
    print(f"\n{'='*60}")
    print("  Estimando errores")
    print(f"{'='*60}")
    data.estimateError(relativeError=REL_ERROR, absoluteUError=ABS_U_ERROR)

    _ = data.show(data['err'] * 100, label='Error estimado [%]')
    plt.savefig(os.path.join(IMG_DIR, '03_errores.png'), dpi=150)
    plt.close('all')

    # --- 7. Inversión ---
    print(f"\n{'='*60}")
    print("  Iniciando inversión ERT")
    print(f"{'='*60}")

    # ERTManager gestiona la creación de malla, forward operator e inversión
    mgr = ert.ERTManager(data)

    # invert() crea la malla paramétrica internamente con los parámetros dados:
    #   lam              : factor de regularización (Occam's razor)
    #   paraDX           : resolución horizontal relativa de la malla
    #   paraMaxCellSize  : tamaño máximo de celda [m²]
    #   paraDepth        : profundidad máxima [m] (regla de thumb: L/4 a L/3)
    #   quality          : ángulo mínimo de los triángulos (33.6° es óptimo)
    mod = mgr.invert(
        data,
        lam             = LAMBDA,
        verbose         = True,
        paraDX          = PARA_DX,
        paraMaxCellSize = PARA_MAX_CELL_SIZE,
        paraDepth       = PARA_DEPTH,
        quality         = QUALITY,
    )

    # --- 8. Resultados ---
    print(f"\n{'='*60}")
    print("  Visualizando resultados")
    print(f"{'='*60}")

    # Resultado + ajuste (datos medidos vs calculados)
    _ = mgr.showResultAndFit()
    plt.savefig(os.path.join(IMG_DIR, '04_resultado_y_ajuste.png'), dpi=150)
    plt.close('all')

    # Modelo solo, con escala personalizada
    ax, cb = mgr.showResult(
        mod,
        cMin     = 10,
        cMax     = 5000,
        cMap     = 'Spectral_r',
        logScale = True,
    )
    ax.set_title('Modelo de resistividad — WS_3_20_cor')
    ax.set_xlabel('Distancia [m]')
    ax.set_ylabel('Profundidad [m]')
    plt.tight_layout()
    plt.savefig(os.path.join(IMG_DIR, '05_modelo_resistividad.png'), dpi=150)
    plt.close('all')

    # Resumen estadístico de la inversión
    print(f"\n  chi² final : {mgr.inv.chi2():.4f}  (ideal ≈ 1.0)")
    print(f"  RMS relativo: {mgr.inv.relrms():.4f}")
    print(f"\n  Figuras guardadas en {IMG_DIR}/")
    for f in ['01_electrodos', '02_pseudoseccion', '03_errores',
              '04_resultado_y_ajuste', '05_modelo_resistividad']:
        print(f"    {f}.png")
