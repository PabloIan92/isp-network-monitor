# isp-network-monitor

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python: 3.10+](https://img.shields.io/badge/Python-3.10%2B-brightgreen.svg)](https://www.python.org/)

A lightweight, multi-vendor network monitoring dashboard and polling daemon designed for WISP (fixed wireless) and FTTH (fiber) infrastructure.

Instead of keeping five separate browser tabs open to check MikroTik routers, Ubiquiti radios, Netonix tower switches, EdgeSwitches, SwOS devices, and GPON OLTs, this project collects health and physical telemetry into a single-pane status board that refreshes automatically.

> **Note**: También disponible en español: [README en Español](README.es.md).

---

## The Problem It Solves

Operating a mixed-vendor network usually means dealing with fragmented management interfaces:
- **MikroTik RouterOS**: Managed via Winbox or SSH commands.
- **Ubiquiti AirMax / LTU**: Monitored through AirControl or UISP.
- **Netonix WISP Switches**: Tower power switches with a proprietary web interface.
- **Ubiquiti EdgeSwitch & MikroTik SwOS**: Web consoles with unique session auth models.
- **GPON OLTs (e.g. OLTCloud)**: Web portals showing ONU optical levels and loss-of-signal (LOS) events.

When a tower drops AC power, a backup battery drops below 24V, or a wireless link degrades during bad weather, having to log into five different systems to correlate what happened takes too long.

`isp-network-monitor` runs a single persistent Python daemon that polls hardware health (voltages, temperatures, fan RPMs, optical receive levels, wireless SNR, interface error counters) and writes readings to a local SQLite database. A lightweight Flask backend serves a fast, dark-mode dashboard without any external JavaScript build steps or heavy dependencies.

---

## Architecture

```
                    ┌────────────────────────┐
   MikroTik (SSH) ──┤                        │
   AirControl (API)─┤                        │      SQLite       ┌────────────┐
   Netonix (API) ───┤   poller_daemon.py     │──── (readings) ───┤   app.py   │──── Web Dashboard
   EdgeSwitch (API)─┤   (systemd background  │     [WAL mode]    │  (Flask)   │     (auto-refreshes 30s)
   SwOS (API) ──────┤    service)            │                   └────────────┘
   OLTCloud (API) ──┤                        │
                    └────────────────────────┘
```

- **`poller_daemon.py`**: Runs continuously in the background (via systemd). Reuses persistent SSH sessions and HTTP auth tokens across poll cycles to prevent spamming device auth logs.
- **SQLite (WAL Mode)**: Lightweight, zero-maintenance storage. Uses two clean tables (`readings` and `poller_runs`) with compound indexes for fast lookups and historical time-series queries.
- **`app.py`**: Minimal Flask service providing three read-only endpoints:
  - `/api/config`: Sanitized topology layout (device names, power supply types, uplinks) with all credentials stripped.
  - `/api/state`: Latest telemetry readings for all monitored devices.
  - `/api/history`: Time-series data points for metric trending and sparklines.
- **`src/static/index.html`**: Clean, vanilla HTML/CSS/JS dashboard. Zero NPM build steps, dark theme, instant load times, and simple color-coded status badges (green / yellow / red).

---

## Why SQLite + Direct Polling Instead of Zabbix or SNMP?

If your network already has complete, clean SNMP support across 100% of your equipment and you have a configured Zabbix or LibreNMS cluster, by all means stick with it.

In real-world field deployments, however:
1. Some tower hardware (like certain SwOS switches or Netonix revisions) has incomplete, undocumented, or buggy SNMP MIB implementations.
2. Querying wide SNMP trees over congested wireless backhauls often leads to UDP packet drops and timeouts.
3. Things like redundant dual-PSU input voltages or optical diagnostic monitors (DDM) are often easier and much faster to fetch directly through native CLI or HTTP endpoints.

This project was built to be completely self-contained. It requires no separate database servers (no MySQL, Postgres, InfluxDB, or Redis), runs comfortably on a $5 VPS or a small local Raspberry Pi, and finishes polling an entire fleet in under 3 seconds.

---

## Quickstart & Demo Mode

You can try the full dashboard locally in seconds with synthetic data without needing access to physical hardware:

```bash
# 1. Clone the repository
git clone https://github.com/PabloIan92/isp-network-monitor.git
cd isp-network-monitor

# 2. Set up virtual environment
python3 -m venv venv
source venv/bin/activate   # On Windows: .\venv\Scripts\activate
pip install -r requirements.txt

# 3. Launch interactive demo mode
python3 src/demo.py
```

Open `http://localhost:8090` in your browser. You will see the live dashboard populated with realistic telemetry (redundant PSU voltages, SFP optical levels, wireless link counts, and temperature trends).

### Running Tests

Automated tests verify API responses, topology sanitization, and state serialization:

```bash
python3 -m unittest discover tests
```

---

## Production Deployment

### 1. Configuration

Copy the example configuration file and fill in your device addresses and read-only credentials:

```bash
cp config.example.yaml config.yaml
chmod 600 config.yaml
$EDITOR config.yaml
```

> **Security Rule**: Always create a restricted, read-only user on your routers (e.g., MikroTik `read` group) and switches. Never use administrative credentials for monitoring.

### 2. Test in Foreground

Verify device connectivity and polling output before installing system services:

```bash
# Test poller run
MONITOREO_CONFIG=$(pwd)/config.yaml python3 src/poller_daemon.py

# Test web backend
MONITOREO_CONFIG=$(pwd)/config.yaml python3 src/app.py
```

### 3. Install as Systemd Services

Service unit files are provided in `systemd/`:

```bash
sudo cp systemd/*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now monitoreo-poller.service monitoreo-dashboard.service
```

Check status with `systemctl status monitoreo-poller`.

---

## Security & Network Access

- **Private Network Only**: The dashboard listens on port `8090` without built-in authentication. Keep it accessible only over a secure management VPN (WireGuard, Tailscale) or place it behind a reverse proxy (Caddy / Nginx) with basic auth or SSL client certificates.
- **Read-Only Telemetry**: The daemon exclusively queries read-only status and health metrics. It never performs configuration changes or firmware writes.
- **Privacy by Design**: This tool monitors physical hardware health (voltages, temperatures, interface packet errors, optical signal levels, wireless SNR). It does **not** inspect user payloads, track browsing activity, or store customer personally identifiable information (PII).

---

## Hardware Documentation

Detailed notes, authentications quirks, and real-world tips for each supported platform:

- [docs/mikrotik.md](docs/mikrotik.md) — RouterOS SSH commands, RouterOS v6 vs v7 health parsing, dual PSU monitoring.
- [docs/aircontrol.md](docs/aircontrol.md) — Ubiquiti AirControl session auth, antenna grouping, SNR thresholds.
- [docs/netonix.md](docs/netonix.md) — Netonix WS series form-based authentication, fan RPM monitoring, thermal limits.
- [docs/oltcloud.md](docs/oltcloud.md) — GPON OLT integration, ONU status tracking (`Online`, `LOS`, `Power Fail`), optical power levels.
- [docs/edgeswitch.md](docs/edgeswitch.md) — Ubiquiti EdgeSwitch session tokens, interface error counters.
- [docs/swos.md](docs/swos.md) — MikroTik SwOS digest authentication and binary telemetry structures.

---

## License

This project is licensed under the [MIT License](LICENSE) — free to use, modify, and adapt for your own infrastructure.
