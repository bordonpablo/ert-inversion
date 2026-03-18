"""Punto de entrada del comando ert-inversion."""

import logging
import sys
from datetime import datetime
from pathlib import Path

import click
import yaml


def _load_config(config_path: Path) -> dict:
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _setup_logger(log_file: Path) -> logging.Logger:
    logger = logging.getLogger("ert_inversion")
    logger.setLevel(logging.INFO)

    fmt = logging.Formatter("%(asctime)s  %(message)s", datefmt="%H:%M:%S")

    # Consola (salida incremental)
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    # Archivo de log en la carpeta de salida
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    return logger


@click.command()
@click.option(
    "--config",
    "config_path",
    default=None,
    type=click.Path(exists=True, dir_okay=False),
    help="Archivo de configuración YAML (por defecto: config/base.yml).",
)
@click.option(
    "--data",
    "data_path",
    default=None,
    type=click.Path(exists=True, dir_okay=False),
    help="Path al archivo .dat de entrada (sobreescribe el valor en la config).",
)
def main(config_path: str | None, data_path: str | None) -> None:
    """Inversión ERT usando pyGIMLi."""

    # --- Configuración ---
    if config_path:
        cfg_file = Path(config_path)
    else:
        cfg_file = Path(__file__).parent.parent.parent / "config" / "base.yml"

    config = _load_config(cfg_file)

    if data_path:
        config["data"]["path"] = data_path

    # --- Carpeta de salida: YYYYMMDDHHMM ---
    timestamp = datetime.now().strftime("%Y%m%d%H%M")
    output_dir = Path("output") / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)

    # --- Logger ---
    logger = _setup_logger(output_dir / "inversion.log")
    logger.info("Configuración: %s", cfg_file)
    logger.info("Carpeta de salida: %s", output_dir.resolve())

    # --- Inversión ---
    from .inversion import Inversion  # import tardío para no cargar pygimli hasta aquí

    inv = Inversion(config, output_dir, logger)
    inv.run()
