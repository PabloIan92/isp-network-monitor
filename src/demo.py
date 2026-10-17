"""Datos sinteticos para mostrar el dashboard sin acceder a redes reales."""

import time


CONFIG = {
    "routers": [{
        "name": "Router-Lab",
        "psu_style": "simple_voltage",
        "uplinks": [{"key": "uplink", "label": "Uplink de prueba"}],
    }],
    "netonix_switches": ["Netonix-Lab"],
    "edgeswitches": ["EdgeSwitch-Lab"],
    "swos_switches": ["SwOS-Lab"],
}

METRICS = {
    "Router-Lab": {
        "reachable": 1, "cpu_load": 24, "cpu_temp": 42,
        "voltage": 24.2, "uptime_seconds": 86400,
        "uplink_status": "link-ok", "uplink_fcs": 2,
        "uplink_rxpkt": 250000,
    },
    "OLT-Lab": {
        "reachable": 1, "total": 20, "online": 18, "offline": 1,
        "sem_energia": 1, "loss": 0, "inativo": 0,
        "desabilitada": 0, "low_power": 1,
    },
    "AirControl-Lab": {
        "reachable": 1, "devices_total": 12, "devices_online": 11,
        "devices_offline": 1, "devices_low_snr": 1,
    },
    "Netonix-Lab": {
        "reachable": 1, "cpu_temp": 43, "board_temp": 38,
        "fan1_rpm": 3200, "uptime_seconds": 172800,
        "dcdc_input_voltage": 48.1, "dcdc_output_voltage": 48.0,
    },
    "EdgeSwitch-Lab": {
        "reachable": 1, "total_port_errors": 3,
        "total_port_packets": 400000, "uptime_seconds": 259200,
    },
    "SwOS-Lab": {
        "reachable": 1, "temp": 37, "fan1_rpm": 3100,
        "psu1_voltage": 24.0, "psu1_state": "ok",
        "uptime_seconds": 345600,
    },
}


def state(now=None):
    now = int(time.time()) if now is None else int(now)
    readings = []
    for entity, metrics in METRICS.items():
        for metric, value in metrics.items():
            readings.append({
                "entity": entity,
                "metric": metric,
                "value": value if isinstance(value, (int, float)) else None,
                "text_value": value if isinstance(value, str) else None,
            })
    return {
        "ts": now,
        "server_now": now,
        "readings": readings,
        "last_run": {"ts": now, "duration_ms": 0, "errors": "[]"},
    }


def history(entity, metric, hours=6, now=None):
    value = METRICS.get(entity, {}).get(metric)
    if not isinstance(value, (int, float)):
        return []
    now = int(time.time()) if now is None else int(now)
    step = max(1, int(hours * 3600 / 5))
    return [{"ts": now - step * (5 - i), "value": value}
            for i in range(6)]
