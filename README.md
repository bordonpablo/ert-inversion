# ert-inversion

Herramienta de línea de comandos para inversión de **Electrical Resistivity Tomography (ERT)** usando [pyGIMLi](https://www.pygimli.org/).

## Características

- Lee archivos `.dat` en formato RES2DINV-like con coordenadas absolutas
- Soporta datos de resistividad aparente (rhoa) y resistencia (r)
- Soporta chargeability (IP) opcional en mV/V
- Genera automáticamente una carpeta de salida con timestamp (`output/YYYYMMDDHHMM/`)
- Produce 5 figuras PNG y un log de la inversión
- Configurable via archivo YAML

## Requisitos

- Python >= 3.10
- pyGIMLi >= 1.5.0 (instalado via conda)
- click >= 8.0
- pyyaml >= 6.0

## Instalación

**1. Crear entorno conda con pyGIMLi:**

```bash
conda create -n pg -c gimli -c conda-forge "pygimli>=1.5.0"
conda activate pg
```

**2. Instalar el paquete en modo editable:**

```bash
pip install -e .
```

Esto registra el comando `ert-inversion` en el entorno.

> Ver `doc/INSTALL.md` para más detalles.

## Uso

```bash
# Con configuración y datos por defecto (config/base.yml + doc/ejemplo.dat)
ert-inversion

# Con configuración personalizada
ert-inversion --config config/mi_config.yml

# Sobreescribir solo el archivo de datos
ert-inversion --data path/to/otro.dat

# Ambos
ert-inversion --config config/mi_config.yml --data path/to/otro.dat
```

## Formato de datos (.dat)

Formato RES2DINV-like con coordenadas absolutas (x, z) por electrodo. Estructura del header:

| Línea | Contenido |
|-------|-----------|
| 0 | Nombre del archivo |
| 1 | Espaciado mínimo de electrodos |
| 2–3 | Parámetros internos (tipo de array) |
| 4 | Descripción del tipo de dato |
| 5 | Tipo: `0` = rhoa [Ohm·m], `1` = resistencia [Ohm] |
| 6 | Número de mediciones |
| 7 | Parámetro adicional |
| 8 | Flag IP: `0` = sin chargeability, `1` = con chargeability (mV/V) |

Si hay chargeability (`línea 8 == 1`), se agregan 3 líneas de header extra (nombre, unidad, ventana de integración) y los datos tienen 11 campos por fila:

```
4  x_A  z_A  x_B  z_B  x_M  z_M  x_N  z_N  rhoa  chargeability
```

Sin chargeability, los datos tienen 10 campos por fila:

```
4  x_A  z_A  x_B  z_B  x_M  z_M  x_N  z_N  valor
```

## Configuración (YAML)

El archivo por defecto es `config/base.yml`:

```yaml
data:
  path: doc/ejemplo.dat       # Path al archivo .dat de entrada

error:
  rel_error: 0.03             # Error relativo (fracción): 0.03 = 3%
  abs_u_error: 5.0e-5         # Umbral absoluto de voltaje [V]

mesh:
  para_dx: 0.3                # Densidad horizontal de celdas paramétricas
  para_max_cell_size: 10      # Tamaño máximo de celda [m²]
  para_depth: 40              # Profundidad máxima de investigación [m]
  quality: 33.6               # Calidad de triangulación — ángulo mínimo [°]

inversion:
  lambda: 20                  # Factor de regularización (mayor → más suave)
```

## Salidas

Cada ejecución genera una carpeta `output/YYYYMMDDHHMM/` con:

| Archivo | Descripción |
|---------|-------------|
| `01_electrodos.png` | Posición de los electrodos |
| `02_pseudoseccion.png` | Pseudosección de resistividad aparente |
| `03_errores.png` | Distribución del error estimado [%] |
| `04_resultado_y_ajuste.png` | Modelo resultante + ajuste de datos |
| `05_modelo_resistividad.png` | Modelo de resistividad (escala log, Spectral_r) |
| `inversion.log` | Log completo con chi², RMS y parámetros usados |

## Flujo de procesamiento

```
.dat → parseo → DataContainer → electrodos → factores geométricos
     → pseudosección → estimación de errores → inversión ERTManager
     → resultado + ajuste → modelo de resistividad
```

## Estructura del proyecto

```
ert-inversion/
├── config/
│   └── base.yml              # Configuración por defecto
├── doc/
│   ├── ejemplo.dat           # Archivo de datos de ejemplo
│   └── INSTALL.md            # Instrucciones de instalación
├── src/
│   └── ert_inversion/
│       ├── __init__.py
│       ├── cli.py            # Punto de entrada CLI (click)
│       └── inversion.py      # Clase Inversion con toda la lógica
├── output/                   # Generado al ejecutar (ignorado por git)
├── pyproject.toml
└── CLAUDE.md
```
