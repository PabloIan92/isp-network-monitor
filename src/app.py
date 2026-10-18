#!/usr/bin/env python3
"""Backend for ISP network monitoring dashboard.

Serves the state/history REST API and single-page frontend.
Reads the SQLite database populated by poller_daemon.py or demo.py.
"""
import os
import sqlite3
import sys
import time
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

# Ensure src directory is in sys.path
SRC_DIR = str(Path(__file__).resolve().parent)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from config import load_config, public_config

CFG = load_config()
DB_PATH = CFG["db_path"]

app = Flask(__name__, static_folder="static", static_url_path="")


def get_db_connection():
    """Returns a thread-safe connection to the SQLite database."""
    # Ensure parent directory exists
    db_file = Path(DB_PATH)
    db_file.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.row_factory = sqlite3.Row
    # Ensure tables exist even if daemon hasn't started yet
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
    return conn


def query(sql, params=()):
    conn = get_db_connection()
    try:
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/api/config")
def api_config():
    """Sanitized topology (names, psu styles, uplinks) without credentials for frontend rendering."""
    return jsonify(public_config(CFG))


@app.route("/api/state")
def api_state():
    """Returns the latest reading snapshot across all monitored entities."""
    latest_ts_row = query("SELECT MAX(ts) as ts FROM readings")
    latest_ts = latest_ts_row[0]["ts"] if latest_ts_row and latest_ts_row[0]["ts"] else None
    if latest_ts is None:
        return jsonify({"ts": None, "readings": [], "server_now": int(time.time()), "last_run": None})
    rows = query("SELECT entity, metric, value, text_value FROM readings WHERE ts = ?", (latest_ts,))
    last_run = query("SELECT ts, duration_ms, errors FROM poller_runs ORDER BY ts DESC LIMIT 1")
    return jsonify({
        "ts": latest_ts,
        "readings": rows,
        "server_now": int(time.time()),
        "last_run": last_run[0] if last_run else None,
    })


@app.route("/api/history")
def api_history():
    """Returns historical time-series datapoints for an entity and metric."""
    entity = request.args.get("entity", "")
    metric = request.args.get("metric", "")
    hours = float(request.args.get("hours", 6))
    since = int(time.time() - hours * 3600)
    rows = query(
        "SELECT ts, value FROM readings WHERE entity=? AND metric=? AND ts>=? ORDER BY ts",
        (entity, metric, since),
    )
    return jsonify(rows)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8090, threaded=True)
