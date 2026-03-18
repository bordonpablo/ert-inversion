# Instrucciones de instalacion

* Instalar Conda con MiniForge
* Instalar PyGIMLi [aca](https://www.pygimli.org/installation.html)

```bash
conda create -n pg -c gimli -c conda-forge "pygimli>=1.5.0"
```
* cargar datos del proyecto en **data/greenland/WS_3_20_cor.dat**
* Ejecutar 

```bash
conda activate pg
python src/inversion.py
```