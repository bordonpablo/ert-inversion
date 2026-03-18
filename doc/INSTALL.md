# Instrucciones de instalacion

## Instalar python y pyGIMLi

* Instalar Conda con MiniForge
* Instalar PyGIMLi. Mas info [aca](https://www.pygimli.org/installation.html)

```bash
conda create -n pg -c gimli -c conda-forge "pygimli>=1.5.0"
conda activate pg
```

## Instalar Comando

Esto instala el comando **ert-inversion** en el entorno de la maquina. Sobre la carpeta del proyecto ejecutar

```bash
pip install -e .  
```

## Ejecutar el comando

```bash
# con config por defecto (config/base.yml) y dato por defecto (doc/ejemplo.dat)
ert-inversion
  
# con config personalizada
ert-inversion --config config/mi_config.yml 
  
# sobreescribir el dato de entrada 
ert-inversion --data path/to/otro.dat
  
#ambos
ert-inversion --config config/mi_config.yml --data path/to/otro.dat
```
