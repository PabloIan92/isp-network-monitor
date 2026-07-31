#!/usr/bin/env python3
"""Poller de monitoreo de red ISP: Mikrotik (SSH) + AirControl + Netonix +
Ubiquiti EdgeSwitch + MikroTik SwOS + OLTCloud, todo en un solo demonio.

Corre como demonio (systemd), NO por cron. Mantiene abierta UNA conexion SSH
por router (se reconecta solo si se corta) en vez de loguearse de nuevo en
cada ciclo -- evita llenar el log de los routers con "user X logged in" cada
2 minutos. Usa una cuenta de solo lectura para los routers, nunca la cuenta
admin. Ver docs/mikrotik.md, docs/aircontrol.md, docs/netonix.md,
docs/edgeswitch.md, docs/swos.md y docs/oltcloud.md para el detalle de cada
integracion (auth, endpoints, gotchas).

Toda la topologia/credenciales viven en config.yaml (ver config.example.yaml),
NUNCA hardcodeadas en este archivo.
"""
import json
import re
import sqlite3
import sys
import time
import traceback

import paramiko
import requests
from requests.auth import HTTPDigestAuth
from requests.packages.urllib3.exceptions import InsecureRequestWarning

from config import load_config

requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

CFG = load_config()

DB_PATH = CFG["db_path"]
RETENTION_DAYS = CFG.get("retention_days", 7)
POLL_INTERVAL_SECONDS = CFG.get("poll_interval_seconds", 120)
SESSION_MAX_AGE = CFG.get("session_max_age_seconds", 600)

THRESHOLDS = CFG.get("thresholds", {})
LOW_POWER_THRESHOLD_DBM = THRESHOLDS.get("low_power_dbm", -28.0)
LOW_SNR_THRESHOLD_DB = THRESHOLDS.get("low_snr_db", 18.0)
FAN_FAIL_RPM_THRESHOLD = THRESHOLDS.get("fan_fail_rpm", 100)

ROUTERS = CFG.get("routers", [])
AIRCONTROL_INSTANCES = CFG.get("aircontrol_instances", [])
NETONIX_SWITCHES = CFG.get("netonix_switches", [])
EDGESWITCHES = CFG.get("edgeswitches", [])
SWOS_SWITCHES = CFG.get("swos_switches", [])
OLTCLOUD = CFG.get("oltcloud") or {}


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
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


def record(conn, ts, entity, metric, value=None, text_value=None):
    conn.execute(
        "INSERT INTO readings (ts, entity, metric, value, text_value) VALUES (?,?,?,?,?)",
        (ts, entity, metric, value, text_value),
    )


def prune(conn, ts):
    cutoff = ts - RETENTION_DAYS * 86400
    conn.execute("DELETE FROM readings WHERE ts < ?", (cutoff,))
    conn.execute("DELETE FROM poller_runs WHERE ts < ?", (cutoff,))


# ---------------------------------------------------------------------------
# Mikrotik polling (conexion SSH persistente, una por router). Ver docs/mikrotik.md
# ---------------------------------------------------------------------------

_ssh_clients = {}  # entity -> paramiko.SSHClient


def health_get_expr(ros_major, name):
    # RouterOS v7 devuelve una tabla y hay que buscar la fila por "name=";
    # v6 tiene la propiedad directa en el get. Confirmar version real por
    # router, no asumir por "es nuevo/viejo".
    if ros_major >= 7:
        return f'[/system health get [find name={name}] value]'
    return f'[/system health get {name}]'


def build_router_script(r):
    ros_major = r["ros_major"]
    # Cada :put es una lectura "clave=valor" que se parsea del stdout. Las
    # sentencias se encadenan con ";" -- un solo comando suelto sobre exec_command
    # falla con "expected command name" en RouterOS.
    stmts = [
        ':put ("cpu_load=" . [/system resource get cpu-load])',
        ':put ("uptime=" . [/system resource get uptime])',
        f':put ("cpu_temp=" . {health_get_expr(ros_major, "cpu-temperature")})',
    ]

    psu_style = r.get("psu_style")
    if psu_style == "simple_voltage":
        stmts.append(f':put ("voltage=" . {health_get_expr(ros_major, "voltage")})')
    elif psu_style == "psu_voltage":
        stmts.append(f':put ("psu1_voltage=" . {health_get_expr(ros_major, "psu1-voltage")})')
        stmts.append(f':put ("psu2_voltage=" . {health_get_expr(ros_major, "psu2-voltage")})')
    elif psu_style == "psu_state":
        stmts.append(f':put ("psu1_state=" . {health_get_expr(ros_major, "psu1-state")})')
        stmts.append(f':put ("psu2_state=" . {health_get_expr(ros_major, "psu2-state")})')

    for up in r.get("uplinks", []):
        key, match = up["key"], up["match"]
        stmts.append(f':put ("{key}_status=" . [/interface ethernet monitor [find name~"{match}"] once as-value]->"status")')
        stmts.append(f':put ("{key}_fcs=" . [/interface ethernet get [find name~"{match}"] rx-fcs-error])')
        stmts.append(f':put ("{key}_code=" . [/interface ethernet get [find name~"{match}"] rx-code-error])')
        stmts.append(f':put ("{key}_rxpkt=" . [/interface ethernet get [find name~"{match}"] rx-packet])')

    return "; ".join(stmts)


def parse_uptime_to_seconds(s):
    m = re.match(r"(?:(\d+)w)?(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?$", s)
    if m and any(m.groups()):
        w, d, h, mi, se = (int(x) if x else 0 for x in m.groups())
        return w * 604800 + d * 86400 + h * 3600 + mi * 60 + se
    m2 = re.match(r"(?:(\d+)w)?(?:(\d+)d)?(\d+):(\d+):(\d+)$", s)
    if m2:
        w, d, h, mi, se = (int(x) if x else 0 for x in m2.groups())
        return w * 604800 + d * 86400 + h * 3600 + mi * 60 + se
    return None


def get_ssh_client(r):
    """Devuelve una conexion SSH viva para el router, reconectando solo si hace falta."""
    entity = r["name"]
    client = _ssh_clients.get(entity)
    if client is not None:
        transport = client.get_transport()
        if transport is not None and transport.is_active():
            return client
        try:
            client.close()
        except Exception:
            pass
        _ssh_clients.pop(entity, None)

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        r["host"], port=r.get("port", 22), username=r["user"], password=r["password"],
        timeout=8, banner_timeout=8, auth_timeout=8, look_for_keys=False, allow_agent=False,
    )
    _ssh_clients[entity] = client
    return client


def poll_router(conn, ts, r, errors):
    entity = r["name"]
    try:
        client = get_ssh_client(r)
        script = build_router_script(r)
        stdin, stdout, stderr = client.exec_command(script, timeout=15)
        out = stdout.read().decode("utf-8", "ignore")
        err = stderr.read().decode("utf-8", "ignore")

        record(conn, ts, entity, "reachable", value=1)
        record(conn, ts, entity, "ip", text_value=r["host"])

        kv = {}
        for line in out.splitlines():
            line = line.strip()
            if "=" in line:
                k, v = line.split("=", 1)
                kv[k.strip()] = v.strip()

        # RouterOS v6 devuelve los health de voltaje en decivoltios (raw/10);
        # v7 ya devuelve voltios reales. Verificar en vivo por router, no asumir.
        volt_divisor = 10.0 if r["ros_major"] < 7 else 1.0

        if "cpu_load" in kv:
            record(conn, ts, entity, "cpu_load", value=float(kv["cpu_load"]))
        if "cpu_temp" in kv:
            record(conn, ts, entity, "cpu_temp", value=float(kv["cpu_temp"]))
        if "voltage" in kv:
            try:
                record(conn, ts, entity, "voltage", value=float(kv["voltage"]) / volt_divisor)
            except ValueError:
                pass
        for psu_key in ("psu1_voltage", "psu2_voltage"):
            if psu_key in kv:
                try:
                    record(conn, ts, entity, psu_key, value=float(kv[psu_key]) / volt_divisor)
                except ValueError:
                    pass
        for psu_key in ("psu1_state", "psu2_state"):
            if psu_key in kv:
                record(conn, ts, entity, psu_key, text_value=kv[psu_key])
        if "uptime" in kv:
            secs = parse_uptime_to_seconds(kv["uptime"])
            if secs is not None:
                record(conn, ts, entity, "uptime_seconds", value=secs)

        for up in r.get("uplinks", []):
            key = up["key"]
            if f"{key}_status" in kv:
                record(conn, ts, entity, f"{key}_status", text_value=kv[f"{key}_status"])
            for m in ("fcs", "code", "rxpkt"):
                mkey = f"{key}_{m}"
                if mkey in kv:
                    try:
                        record(conn, ts, entity, mkey, value=float(kv[mkey]))
                    except ValueError:
                        pass

        if err.strip():
            errors.append(f"{entity}: stderr={err.strip()[:200]}")
    except Exception as e:
        record(conn, ts, entity, "reachable", value=0)
        errors.append(f"{entity}: {type(e).__name__}: {e}")
        _ssh_clients.pop(entity, None)


# ---------------------------------------------------------------------------
# AirControl polling (reusa la sesion mientras no expire). Ver docs/aircontrol.md
# ---------------------------------------------------------------------------

_aircontrol_sessions = {}  # name -> {"session": requests.Session, "created": ts}


def get_aircontrol_session(inst):
    name = inst["name"]
    now = time.time()
    cached = _aircontrol_sessions.get(name)
    if cached and (now - cached["created"]) < SESSION_MAX_AGE:
        return cached["session"]

    s = requests.Session()
    s.verify = False
    r = s.post(
        f"https://{inst['host']}:9082/api/v1/login",
        json={"username": inst["user"], "password": inst["password"],
              "eulaAccepted": True, "verifyCsrfToken": True},
        timeout=10,
    )
    r.raise_for_status()
    _aircontrol_sessions[name] = {"session": s, "created": now}
    return s


def poll_aircontrol(conn, ts, inst, errors):
    entity = inst["name"]
    try:
        s = get_aircontrol_session(inst)
        r2 = s.get(f"https://{inst['host']}:9082/api/v1/devices", params={"limit": 2000}, timeout=20)
        if r2.status_code in (401, 403):
            _aircontrol_sessions.pop(entity, None)
            s = get_aircontrol_session(inst)
            r2 = s.get(f"https://{inst['host']}:9082/api/v1/devices", params={"limit": 2000}, timeout=20)
        r2.raise_for_status()
        devices = r2.json().get("results", [])

        online = offline = low_snr = 0
        for d in devices:
            status = (d.get("status") or {})
            if status.get("online"):
                online += 1
            else:
                offline += 1
                continue
            props = d.get("overview") or d.get("properties") or {}
            snr = None
            if isinstance(props, dict):
                sig = None
                noise = None
                for k, v in props.items():
                    kl = k.lower()
                    if "signal" in kl and "~current" in kl and sig is None:
                        sig = v
                    if "noise" in kl and "~current" in kl and noise is None:
                        noise = v
                if sig is not None and noise is not None:
                    try:
                        snr = float(sig) - float(noise)
                    except (TypeError, ValueError):
                        snr = None
            if snr is not None and snr < LOW_SNR_THRESHOLD_DB:
                low_snr += 1

        record(conn, ts, entity, "reachable", value=1)
        record(conn, ts, entity, "devices_total", value=len(devices))
        record(conn, ts, entity, "devices_online", value=online)
        record(conn, ts, entity, "devices_offline", value=offline)
        record(conn, ts, entity, "devices_low_snr", value=low_snr)
    except Exception as e:
        record(conn, ts, entity, "reachable", value=0)
        errors.append(f"{entity}: {type(e).__name__}: {e}")
        _aircontrol_sessions.pop(entity, None)


# ---------------------------------------------------------------------------
# Netonix polling (login por form POST simple, sesion PHPSESSID reutilizada).
# Ver docs/netonix.md
# ---------------------------------------------------------------------------

_netonix_sessions = {}  # name -> {"session": requests.Session, "created": ts}


def netonix_base_url(inst):
    scheme = inst.get("scheme", "http")
    return f"{scheme}://{inst['host']}"


def get_netonix_session(inst):
    name = inst["name"]
    now = time.time()
    cached = _netonix_sessions.get(name)
    if cached and (now - cached["created"]) < SESSION_MAX_AGE:
        return cached["session"]

    s = requests.Session()
    if inst.get("scheme") == "https":
        s.verify = False
    r = s.post(f"{netonix_base_url(inst)}/index.php",
               data={"username": inst["user"], "password": inst["password"]}, timeout=10)
    r.raise_for_status()
    if "PHPSESSID" not in s.cookies.get_dict():
        raise RuntimeError("login no genero sesion (usuario/clave incorrectos?)")
    _netonix_sessions[name] = {"session": s, "created": now}
    return s


def poll_netonix(conn, ts, inst, errors):
    entity = inst["name"]
    try:
        base = netonix_base_url(inst)
        s = get_netonix_session(inst)
        bootid_resp = s.get(f"{base}/api/v1/bootid", timeout=10)
        if bootid_resp.status_code in (401, 403):
            _netonix_sessions.pop(entity, None)
            s = get_netonix_session(inst)
            bootid_resp = s.get(f"{base}/api/v1/bootid", timeout=10)
        bootid_resp.raise_for_status()
        bootid = bootid_resp.json()["BootID"]

        r = s.get(f"{base}/api/v1/status/30sec?{bootid}", timeout=10)
        r.raise_for_status()
        data = r.json()

        def get_float(key):
            v = data.get(key)
            try:
                return float(v) if v is not None else None
            except (TypeError, ValueError):
                return None

        record(conn, ts, entity, "reachable", value=1)
        record(conn, ts, entity, "ip", text_value=inst["host"])
        record(conn, ts, entity, "scheme", text_value=inst.get("scheme", "http"))
        for key, metric in (
            ("CPU_Temp", "cpu_temp"),
            ("Board_Temp", "board_temp"),
            ("Uptime", "uptime_seconds"),
            # No todos los modelos tienen los mismos campos: los DC-powered
            # traen DCDC_*, los AC-powered traen Board_48V/Board_24V en su
            # lugar. Usar get_float (con .get) para no reventar con KeyError.
            ("DCDC_Input_Voltage", "dcdc_input_voltage"),
            ("DCDC_Output_Voltage", "dcdc_output_voltage"),
            ("Board_48V", "board_48v"),
            ("Board_24V", "board_24v"),
        ):
            val = get_float(key)
            if val is not None:
                record(conn, ts, entity, metric, value=val)

        fan_speeds = [float(x) for x in data.get("Fan_Speeds", [])]
        for i, speed in enumerate(fan_speeds):
            record(conn, ts, entity, f"fan{i+1}_rpm", value=speed)
        fans_failed = sum(1 for sp in fan_speeds if sp < FAN_FAIL_RPM_THRESHOLD)
        record(conn, ts, entity, "fans_failed", value=fans_failed)
        record(conn, ts, entity, "fans_total", value=len(fan_speeds))
    except Exception as e:
        record(conn, ts, entity, "reachable", value=0)
        errors.append(f"{entity}: {type(e).__name__}: {e}")
        _netonix_sessions.pop(entity, None)


# ---------------------------------------------------------------------------
# EdgeSwitch polling (login JSON simple, token en header x-auth-token).
# Ver docs/edgeswitch.md
# ---------------------------------------------------------------------------

_edgeswitch_sessions = {}  # name -> {"session": requests.Session, "token": str, "created": ts}


def get_edgeswitch_session(inst):
    name = inst["name"]
    now = time.time()
    cached = _edgeswitch_sessions.get(name)
    if cached and (now - cached["created"]) < SESSION_MAX_AGE:
        return cached["session"], cached["token"]

    s = requests.Session()
    s.verify = False
    r = s.post(f"https://{inst['host']}/api/v1.0/user/login",
               json={"username": inst["user"], "password": inst["password"]}, timeout=10)
    r.raise_for_status()
    token = r.headers.get("x-auth-token")
    if not token:
        raise RuntimeError("login no devolvio x-auth-token (usuario/clave incorrectos?)")
    _edgeswitch_sessions[name] = {"session": s, "token": token, "created": now}
    return s, token


def poll_edgeswitch(conn, ts, inst, errors):
    entity = inst["name"]
    try:
        s, token = get_edgeswitch_session(inst)
        headers = {"x-auth-token": token}
        r = s.get(f"https://{inst['host']}/api/v1.0/statistics", headers=headers, timeout=10)
        if r.status_code in (401, 403):
            _edgeswitch_sessions.pop(entity, None)
            s, token = get_edgeswitch_session(inst)
            headers = {"x-auth-token": token}
            r = s.get(f"https://{inst['host']}/api/v1.0/statistics", headers=headers, timeout=10)
        r.raise_for_status()
        data = r.json()[0]

        record(conn, ts, entity, "reachable", value=1)
        record(conn, ts, entity, "ip", text_value=inst["host"])
        record(conn, ts, entity, "cpu_usage", value=float(data["device"]["cpu"][0]["usage"]))
        record(conn, ts, entity, "ram_usage", value=float(data["device"]["ram"]["usage"]))
        record(conn, ts, entity, "uptime_seconds", value=float(data["device"]["uptime"]))

        ports_with_errors = 0
        total_errors = 0
        total_packets = 0
        for iface in data.get("interfaces", []):
            stats = iface.get("statistics", {})
            errs = int(stats.get("errors", 0)) + int(stats.get("dropped", 0) or 0)
            if errs > 0:
                ports_with_errors += 1
            total_errors += errs
            total_packets += int(stats.get("rxPackets", 0) or 0) + int(stats.get("txPackets", 0) or 0)
        record(conn, ts, entity, "ports_with_errors", value=ports_with_errors)
        record(conn, ts, entity, "total_port_errors", value=total_errors)
        # Un contador crudo > 0 termina disparando tarde o temprano en
        # cualquier puerto con trafico real - guardamos tambien el total de
        # paquetes para que el frontend calcule tasa (errores/paquetes),
        # igual que con los uplinks Mikrotik, en vez de mirar el contador
        # absoluto.
        record(conn, ts, entity, "total_port_packets", value=total_packets)
    except Exception as e:
        record(conn, ts, entity, "reachable", value=0)
        errors.append(f"{entity}: {type(e).__name__}: {e}")
        _edgeswitch_sessions.pop(entity, None)


# ---------------------------------------------------------------------------
# MikroTik SwOS polling (formato hex propietario en /sys.b, HTTP Digest auth).
# Ver docs/swos.md
# ---------------------------------------------------------------------------

def parse_swos_blob(text):
    """SwOS no devuelve JSON: es un pseudo-objeto con claves sin comillas,
    strings hex-encoded entre comillas simples, y enteros en 0x... Parser
    minimo escrito a mano contra el formato real observado."""
    body = text.strip().strip("{}")
    result = {}
    for part in body.split(","):
        if ":" not in part:
            continue
        k, v = part.split(":", 1)
        k, v = k.strip(), v.strip()
        if v.startswith("'") and v.endswith("'"):
            result[k] = v[1:-1]
        elif v.startswith("0x"):
            try:
                result[k] = int(v, 16)
            except ValueError:
                result[k] = None
        else:
            result[k] = v
    return result


def poll_swos(conn, ts, inst, errors):
    entity = inst["name"]
    try:
        r = requests.get(f"http://{inst['host']}/sys.b",
                          auth=HTTPDigestAuth(inst["user"], inst["password"]), timeout=10)
        r.raise_for_status()
        data = parse_swos_blob(r.text)

        record(conn, ts, entity, "reachable", value=1)
        record(conn, ts, entity, "ip", text_value=inst["host"])
        if "temp" in data:
            record(conn, ts, entity, "temp", value=float(data["temp"]))
        if "upt" in data:
            record(conn, ts, entity, "uptime_seconds", value=data["upt"] / 10.0)
        # "fan_slots" filtra los indices crudos que son slots reales en esta
        # placa - verificar contra la UI real del equipo antes de asumir un
        # mapeo secuencial simple (algunos modelos tienen un fanN fantasma).
        for i in inst.get("fan_slots", [1, 2, 3, 4]):
            key = f"fan{i}"
            if key in data and data[key] is not None:
                record(conn, ts, entity, f"{key}_rpm", value=float(data[key]))
        for i in (1, 2):
            vkey, skey = f"p{i}v", f"p{i}s"
            if vkey in data and data[vkey] is not None:
                record(conn, ts, entity, f"psu{i}_voltage", value=data[vkey] / 1000.0)
            if skey in data and data[skey] is not None:
                record(conn, ts, entity, f"psu{i}_state", text_value="ok" if data[skey] == 1 else "fail")
    except Exception as e:
        record(conn, ts, entity, "reachable", value=0)
        errors.append(f"{entity}: {type(e).__name__}: {e}")


# ---------------------------------------------------------------------------
# OLTCloud polling (token bearer reusado mientras no expire). Ver docs/oltcloud.md
# ---------------------------------------------------------------------------

_oltcloud_token = {"token": None, "created": 0}


def get_oltcloud_token():
    now = time.time()
    if _oltcloud_token["token"] and (now - _oltcloud_token["created"]) < SESSION_MAX_AGE:
        return _oltcloud_token["token"]
    r = requests.post(f"{OLTCLOUD['base_url']}/api/token",
                       json={"username": OLTCLOUD["user"], "password": OLTCLOUD["password"]}, timeout=10)
    r.raise_for_status()
    token = r.json()["access"]
    _oltcloud_token["token"] = token
    _oltcloud_token["created"] = now
    return token


def poll_oltcloud(conn, ts, errors):
    try:
        token = get_oltcloud_token()
        headers = {"Authorization": f"Bearer {token}"}

        per_olt = {}
        page = 1
        while True:
            resp = requests.get(f"{OLTCLOUD['base_url']}/api/v2/ftth/equipment/list",
                                 headers=headers, params={"page": page}, timeout=20)
            if resp.status_code in (401, 403):
                _oltcloud_token["token"] = None
                headers = {"Authorization": f"Bearer {get_oltcloud_token()}"}
                resp = requests.get(f"{OLTCLOUD['base_url']}/api/v2/ftth/equipment/list",
                                     headers=headers, params={"page": page}, timeout=20)
            resp.raise_for_status()
            data = resp.json()
            items = data.get("results", data if isinstance(data, list) else [])
            if not items:
                break
            for it in items:
                olt = it.get("olt") or "desconocida"
                d = per_olt.setdefault(olt, {"total": 0, "online": 0, "offline": 0,
                                              "sem_energia": 0, "loss": 0, "inativo": 0,
                                              "desabilitada": 0, "low_power": 0})
                d["total"] += 1
                # Estados reales observados en OLTCloud (pueden variar segun
                # firmware/idioma del vendor): Online, Sem Energia, LOSS,
                # Inativo, Desabilitada. Sem Energia = corte de luz del lado
                # del cliente (dying gasp), no es un problema de red/fibra.
                # LOSS = perdida de senal optica con el ONU energizado, ese si
                # es un problema real de fibra/OLT. Inativo/Desabilitada son
                # estados administrativos (baja/deshabilitado a proposito).
                status = (it.get("status") or "").lower()
                if "online" in status:
                    d["online"] += 1
                elif "sem energia" in status or "energia" in status:
                    d["sem_energia"] += 1
                elif "loss" in status:
                    d["loss"] += 1
                elif "inativ" in status:
                    d["inativo"] += 1
                elif "desabilit" in status:
                    d["desabilitada"] += 1
                else:
                    d["offline"] += 1
                rx = it.get("device_rx")
                if rx is not None:
                    try:
                        rxf = float(rx)
                        if rxf != -99.99 and rxf <= LOW_POWER_THRESHOLD_DBM:
                            d["low_power"] += 1
                    except (TypeError, ValueError):
                        pass
            if not data.get("next"):
                break
            page += 1
            if page > 200:
                break

        record(conn, ts, "OLTCloud", "reachable", value=1)
        for olt, d in per_olt.items():
            entity = f"OLT-{olt}"
            for metric, val in d.items():
                record(conn, ts, entity, metric, value=val)
        record(conn, ts, "OLTCloud", "olts_json", text_value=json.dumps(per_olt, ensure_ascii=False))
    except Exception as e:
        record(conn, ts, "OLTCloud", "reachable", value=0)
        errors.append(f"OLTCloud: {type(e).__name__}: {e}")


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def run_once():
    start = time.time()
    ts = int(start)
    conn = get_db()
    errors = []

    for r in ROUTERS:
        poll_router(conn, ts, r, errors)

    for inst in AIRCONTROL_INSTANCES:
        poll_aircontrol(conn, ts, inst, errors)

    for inst in NETONIX_SWITCHES:
        poll_netonix(conn, ts, inst, errors)

    for inst in EDGESWITCHES:
        poll_edgeswitch(conn, ts, inst, errors)

    for inst in SWOS_SWITCHES:
        poll_swos(conn, ts, inst, errors)

    if OLTCLOUD.get("base_url"):
        poll_oltcloud(conn, ts, errors)

    prune(conn, ts)
    duration_ms = int((time.time() - start) * 1000)
    conn.execute("INSERT INTO poller_runs (ts, duration_ms, errors) VALUES (?,?,?)",
                 (ts, duration_ms, json.dumps(errors, ensure_ascii=False)))
    conn.commit()
    conn.close()

    if errors:
        print(f"[{ts}] poll finished in {duration_ms}ms with {len(errors)} errors:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
    else:
        print(f"[{ts}] poll finished in {duration_ms}ms, no errors")


def main():
    while True:
        cycle_start = time.time()
        try:
            run_once()
        except Exception:
            traceback.print_exc()
        elapsed = time.time() - cycle_start
        time.sleep(max(1, POLL_INTERVAL_SECONDS - elapsed))


if __name__ == "__main__":
    main()
