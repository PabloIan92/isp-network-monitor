"""Configuration loader for isp-network-monitor poller and web dashboard."""
import os
import tempfile
from pathlib import Path
import yaml

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CONFIG_PATH = os.path.join(REPO_ROOT, "config.yaml")
CONFIG_PATH = os.environ.get("MONITOREO_CONFIG", DEFAULT_CONFIG_PATH)


def get_demo_config():
    """Generates an ephemeral configuration for testing or demo mode."""
    demo_db = Path(tempfile.gettempdir()) / "isp_monitor_demo" / "demo_monitoreo.db"
    return {
        "db_path": str(demo_db),
        "poll_interval_seconds": 60,
        "retention_days": 7,
        "routers": [
            {
                "name": "Router-Core",
                "host": "192.0.2.1",
                "psu_style": "psu_voltage",
                "uplinks": [{"key": "sfp1", "label": "sfp1 - Primary Uplink", "match": "sfp1"}],
            },
            {
                "name": "Router-Distribution-1",
                "host": "192.0.2.2",
                "psu_style": "simple_voltage",
                "uplinks": [],
            },
        ],
        "aircontrol_instances": [{"name": "AirControl-Tower1", "host": "192.0.2.10"}],
        "netonix_switches": [{"name": "Netonix-SiteA", "host": "192.0.2.20"}],
        "edgeswitches": [{"name": "EdgeSwitch-SiteB", "host": "192.0.2.30"}],
        "swos_switches": [{"name": "SwOS-Switch-01", "host": "192.0.2.40"}],
        "oltcloud": {"name": "OLTCloud-Central"},
    }


def load_config():
    """Loads configuration from yaml file, with demo fallback for easy onboarding."""
    if os.environ.get("MONITOREO_DEMO") == "1":
        return get_demo_config()

    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    # If config.yaml is missing, check if config.example.yaml exists
    example_path = os.path.join(REPO_ROOT, "config.example.yaml")
    if os.path.exists(example_path):
        # Notify developer and return fallback demo configuration
        return get_demo_config()

    raise FileNotFoundError(
        f"Configuration file not found at {CONFIG_PATH}. "
        "Copy config.example.yaml to config.yaml or run 'python src/demo.py' for demo mode."
    )


def public_config(cfg):
    """Sanitized configuration exposed to the frontend (topology and names only, no secrets)."""
    def strip(entries, keep):
        return [{k: e.get(k) for k in keep} for e in (entries or [])]

    return {
        "routers": strip(cfg.get("routers"), ["name", "psu_style", "uplinks"]),
        "netonix_switches": [e["name"] for e in cfg.get("netonix_switches", []) if isinstance(e, dict) and "name" in e],
        "edgeswitches": [e["name"] for e in cfg.get("edgeswitches", []) if isinstance(e, dict) and "name" in e],
        "swos_switches": [e["name"] for e in cfg.get("swos_switches", []) if isinstance(e, dict) and "name" in e],
    }
