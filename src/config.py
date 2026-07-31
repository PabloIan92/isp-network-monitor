"""Carga config.yaml (rutas, credenciales, topologia) para poller y dashboard."""
import os

import yaml

CONFIG_PATH = os.environ.get(
    "MONITOREO_CONFIG",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.yaml"),
)


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def public_config(cfg):
    """Version de la config sin credenciales, para exponer al frontend (topologia,
    nombres, estilos de PSU/uplinks) sin filtrar passwords."""

    def strip(entries, keep):
        return [{k: e.get(k) for k in keep} for e in (entries or [])]

    return {
        "routers": strip(cfg.get("routers"), ["name", "psu_style", "uplinks"]),
        "netonix_switches": [e["name"] for e in cfg.get("netonix_switches", [])],
        "edgeswitches": [e["name"] for e in cfg.get("edgeswitches", [])],
        "swos_switches": [e["name"] for e in cfg.get("swos_switches", [])],
    }
