#!/usr/bin/env python3
"""Interactive demo mode for isp-network-monitor.

Seeds a temporary SQLite database with realistic synthetic network telemetry
and starts the Flask dashboard on http://127.0.0.1:8090 for evaluation.
No real network hardware or credentials required.
"""
import os
import sqlite3
import tempfile
import time
from pathlib import Path

# Create a temporary directory for demo data
DEMO_DIR = Path(tempfile.gettempdir()) / "isp_monitor_demo"
DEMO_DIR.mkdir(parents=True, exist_ok=True)
DEMO_DB = DEMO_DIR / "demo_monitoreo.db"

# Sample topology matching config.example.yaml
DEMO_CONFIG = {
    "db_path": str(DEMO_DB),
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


def seed_demo_database(db_path: Path):
    """Populates the database with realistic synthetic readings and history."""
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS readings (
            ts INTEGER NOT NULL,
            entity TEXT NOT NULL,
            metric TEXT NOT NULL,
            value REAL,
            text_value TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_readings_lookup ON readings(entity, metric, ts)")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS poller_runs (
            ts INTEGER NOT NULL,
            duration_ms INTEGER,
            errors TEXT
        )
    """)

    conn.execute("DELETE FROM readings")
    conn.execute("DELETE FROM poller_runs")

    now = int(time.time())
    # Generate 6 hours of historical data points every 15 minutes
    timestamps = [now - (i * 900) for i in range(24, -1, -1)]

    for ts in timestamps:
        # Router-Core metrics
        conn.execute("INSERT INTO readings VALUES (?, ?, ?, ?, ?)", (ts, "Router-Core", "cpu_percent", 14.5, None))
        conn.execute("INSERT INTO readings VALUES (?, ?, ?, ?, ?)", (ts, "Router-Core", "board_temp_c", 41.0, None))
        conn.execute("INSERT INTO readings VALUES (?, ?, ?, ?, ?)", (ts, "Router-Core", "psu1_voltage", 24.2, None))
        conn.execute("INSERT INTO readings VALUES (?, ?, ?, ?, ?)", (ts, "Router-Core", "psu2_voltage", 24.1, None))
        conn.execute("INSERT INTO readings VALUES (?, ?, ?, ?, ?)", (ts, "Router-Core", "uptime_seconds", 2592000, None))
        conn.execute("INSERT INTO readings VALUES (?, ?, ?, ?, ?)", (ts, "Router-Core", "sfp1_link_status", None, "up"))
        conn.execute("INSERT INTO readings VALUES (?, ?, ?, ?, ?)", (ts, "Router-Core", "sfp1_rx_power_dbm", -6.4, None))

        # Router-Distribution-1
        conn.execute("INSERT INTO readings VALUES (?, ?, ?, ?, ?)", (ts, "Router-Distribution-1", "cpu_percent", 26.0, None))
        conn.execute("INSERT INTO readings VALUES (?, ?, ?, ?, ?)", (ts, "Router-Distribution-1", "board_temp_c", 46.5, None))
        conn.execute("INSERT INTO readings VALUES (?, ?, ?, ?, ?)", (ts, "Router-Distribution-1", "voltage", 23.9, None))
        conn.execute("INSERT INTO readings VALUES (?, ?, ?, ?, ?)", (ts, "Router-Distribution-1", "uptime_seconds", 1209600, None))

        # AirControl-Tower1
        conn.execute("INSERT INTO readings VALUES (?, ?, ?, ?, ?)", (ts, "AirControl-Tower1", "total_devices", 48.0, None))
        conn.execute("INSERT INTO readings VALUES (?, ?, ?, ?, ?)", (ts, "AirControl-Tower1", "low_snr_count", 1.0, None))
        conn.execute("INSERT INTO readings VALUES (?, ?, ?, ?, ?)", (ts, "AirControl-Tower1", "offline_count", 0.0, None))

        # Netonix-SiteA
        conn.execute("INSERT INTO readings VALUES (?, ?, ?, ?, ?)", (ts, "Netonix-SiteA", "board_temp_c", 38.0, None))
        conn.execute("INSERT INTO readings VALUES (?, ?, ?, ?, ?)", (ts, "Netonix-SiteA", "fan1_rpm", 2450.0, None))
        conn.execute("INSERT INTO readings VALUES (?, ?, ?, ?, ?)", (ts, "Netonix-SiteA", "port_errors_active", 0.0, None))

        # OLTCloud-Central
        conn.execute("INSERT INTO readings VALUES (?, ?, ?, ?, ?)", (ts, "OLTCloud-Central", "total_onus", 312.0, None))
        conn.execute("INSERT INTO readings VALUES (?, ?, ?, ?, ?)", (ts, "OLTCloud-Central", "online_count", 308.0, None))
        conn.execute("INSERT INTO readings VALUES (?, ?, ?, ?, ?)", (ts, "OLTCloud-Central", "los_count", 2.0, None))
        conn.execute("INSERT INTO readings VALUES (?, ?, ?, ?, ?)", (ts, "OLTCloud-Central", "low_power_count", 2.0, None))

        # EdgeSwitch-SiteB
        conn.execute("INSERT INTO readings VALUES (?, ?, ?, ?, ?)", (ts, "EdgeSwitch-SiteB", "temperature_c", 39.0, None))
        conn.execute("INSERT INTO readings VALUES (?, ?, ?, ?, ?)", (ts, "EdgeSwitch-SiteB", "fan_state", None, "Operational"))
        conn.execute("INSERT INTO readings VALUES (?, ?, ?, ?, ?)", (ts, "EdgeSwitch-SiteB", "fcs_errors", 0.0, None))

    conn.execute("INSERT INTO poller_runs VALUES (?, ?, ?)", (now, 245, "None"))
    conn.commit()
    conn.close()


def create_demo_app():
    """Builds and returns a Flask application configured with demo data."""
    seed_demo_database(DEMO_DB)

    # Import app and inject demo config & database
    from src import app as dashboard_module
    dashboard_module.CFG = DEMO_CONFIG
    dashboard_module.DB_PATH = str(DEMO_DB)
    return dashboard_module.app


if __name__ == "__main__":
    print(f"[*] Initializing synthetic demo database at: {DEMO_DB}")
    app = create_demo_app()
    print("[*] Starting ISP Network Monitor Demo Dashboard...")
    print(" -> Access web UI at: http://127.0.0.1:8090/")
    print(" -> Press Ctrl+C to stop.")
    app.run(host="127.0.0.1", port=8090, debug=False)
