# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Info about the project

Herramienta CLI para inversión de **Electrical Resistivity Tomography (ERT)** usando pyGIMLi.

### Stack y dependencias

- **Python >= 3.10**, gestionado con conda (entorno `pg`)
- **pyGIMLi >= 1.5.0** — instalado via conda (`-c gimli -c conda-forge`), NO via pip
- **click >= 8.0** — CLI
- **pyyaml >= 6.0** — configuración
- **matplotlib** — backend `Agg` (no interactivo, evita bloqueos Qt/Wayland)
- **numpy**

### Estructura de módulos

```
src/ert_inversion/
├── __init__.py       # vacío, solo marca el paquete
├── cli.py            # Punto de entrada: comando `ert-inversion` (click)
└── inversion.py      # Clase Inversion — toda la lógica de procesamiento
```

- `cli.py` carga configuración YAML, crea carpeta de salida con timestamp y llama a `Inversion.run()`
- `inversion.py` importa pygimli de forma tardía (dentro de `run()`) para no bloquear el CLI si pygimli no está instalado

### Formato de entrada

Archivos `.dat` en formato RES2DINV-like con coordenadas absolutas (x, z) por electrodo. El parseo completo está en `inversion.py:_parse_dat()`.

### Configuración

`config/base.yml` — cuatro secciones: `data`, `error`, `mesh`, `inversion`. Se puede sobreescribir con `--config` o solo el dato de entrada con `--data`.

### Salidas

Cada ejecución genera `output/YYYYMMDDHHMM/` con 5 PNGs y `inversion.log`.

### Comandos clave

```bash
# Instalar
conda activate pg
pip install -e .

# Ejecutar
ert-inversion
ert-inversion --config config/mi_config.yml --data path/to/otro.dat
```

### Notas importantes

- pyGIMLi **debe instalarse via conda** antes de `pip install -e .`
- El build backend es `setuptools.build_meta` (NO `setuptools.backends.legacy:build`, que requiere setuptools >= 68)
- `output/` está en `.gitignore`


## Development Guidelines for Claude

### Working Style

- *Incremental Changes Only*: Make small, focused modifications to single functions or files
- *No Bulk Refactoring*: Avoid large-scale changes or restructuring without explicit permission
- *Preserve Existing Logic*: Maintain current implementation patterns unless specifically asked to change
- *Step-by-Step Approach*: Break complex tasks into small, reviewable steps
- *Explicit Scope*: Only modify files/functions explicitly mentioned in the request

### Code Modification Rules

1. *Single Responsibility*: Each change should address one specific issue or feature
2. *Minimal Impact*: Prefer the smallest possible change that solves the problem
3. *Ask Before Expanding*: If a change requires touching multiple files, ask for confirmation first
4. *Preserve Comments*: Keep existing comments and TODOs unless specifically addressing them
5. *No Unsolicited Improvements*: Don't optimize or refactor code unless that's the specific request