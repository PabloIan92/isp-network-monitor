#!/usr/bin/env python3
"""Backend del dashboard de monitoreo. Sirve la API de estado/historico (lee el
SQLite que llena poller_daemon.py) + el frontend estatico."""
import os
import sqlite3
import time

from flask import Flask, jsonify, request, send_from_directory

from config import load_config, public_config
from demo import CONFIG as DEMO_CONFIG, history as demo_history, state as demo_state

DEMO_MODE = os.environ.get("MONITOREO_DEMO") == "1"
CFG = None if DEMO_MODE else load_config()
DB_PATH = None if DEMO_MODE else CFG["db_path"]

app = Flask(__name__, static_folder="static", static_url_path="")


def query(sql, params=()):
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA busy_timeout=30000")
    conn.row_factory = sqlite3.Row
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
    """Topologia (nombres, estilo de PSU, uplinks) sin credenciales - el
    frontend la usa para saber que tarjetas/campos dibujar."""
    return jsonify(DEMO_CONFIG if DEMO_MODE else public_config(CFG))


@app.route("/api/state")
def api_state():
    if DEMO_MODE:
        return jsonify(demo_state())
    latest_ts_row = query("SELECT MAX(ts) as ts FROM readings")
    latest_ts = latest_ts_row[0]["ts"] if latest_ts_row and latest_ts_row[0]["ts"] else None
    if latest_ts is None:
        return jsonify({"ts": None, "readings": [], "server_now": int(time.time())})
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
    entity = request.args.get("entity", "")
    metric = request.args.get("metric", "")
    try:
        hours = float(request.args.get("hours", 6))
    except ValueError:
        return jsonify({"error": "hours must be a positive number"}), 400
    if not 0 < hours <= 168:
        return jsonify({"error": "hours must be between 0 and 168"}), 400
    if DEMO_MODE:
        return jsonify(demo_history(entity, metric, hours))
    since = int(time.time() - hours * 3600)
    rows = query(
        "SELECT ts, value FROM readings WHERE entity=? AND metric=? AND ts>=? ORDER BY ts",
        (entity, metric, since),
    )
    return jsonify(rows)


if __name__ == "__main__":
    app.run(host=os.environ.get("MONITOREO_HOST", "127.0.0.1"), port=8090, threaded=True)
