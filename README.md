# isp-network-monitor

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)

> **[English](README.md) | [Español](README.es.md)**

A unified network telemetry daemon and real-time web dashboard for multi-vendor WISP & FTTH infrastructure. It consolidates health metrics, optical levels, temperature, voltages, and link states across diverse platforms into a single interface:

- **MikroTik RouterOS** (v6 / v7 via persistent SSH)
- **MikroTik SwOS** (Digest auth, proprietary binary telemetry format)
- **Ubiquiti AirControl** (Wireless CPE & AP cluster monitoring via REST API)
- **Ubiquiti EdgeSwitch** (Session-authenticated switch telemetry)
- **Netonix WISP Switches** (DC-DC voltage, fans, temperature, port power)
- **OLTCloud** (GPON/EPON ONU states, optical power levels, dying gasp detection)

---

## 🛡️ Project Ownership & Data Privacy

- **Sole Personal Ownership:** This is an independent open-source personal project and homelab reference architecture authored solely by Pablo Ian Laurino. It is not affiliated with, commissioned by, or derived from any employer, client, startup, or institutional work. All code is independently developed and published under the [MIT License](LICENSE).
- **Zero Subscriber Data / No PII:** The system collects strictly physical device-level telemetry (CPU load, temperatures, PSU voltages, fan RPMs, optical power levels, interface error counters). It does not collect, store, or process any subscriber names, personal information, or customer traffic.
- **Isolated Synthetic Demo:** All examples and tests use synthetic topology with RFC 5737 documentation IP ranges (`192.0.2.0/24`) and dummy placeholders. No real network credentials or configurations are stored in this repository.

---

## ⚡ Quickstart (Synthetic Demo Mode)

Run the dashboard immediately with mock lab topology and metrics — **no physical hardware or database setup required**:

```bash
# Install dependencies
python -m pip install flask pyyaml

# Run demo mode (PowerShell):
$env:MONITOREO_DEMO = "1"
python src/app.py

# Run demo mode (Linux / macOS):
MONITOREO_DEMO=1 python3 src/app.py
```

Open your browser at **`http://127.0.0.1:8090`**.

Unit tests verifying the demo environment:
```bash
python tests/test_demo.py
```

---

## 🏛️ Architecture

```
                    ┌─────────────────────┐
   MikroTik (SSH) ──┤                     │
   AirControl (API)─┤                     │      SQLite       ┌──────────┐
   Netonix (API) ───┤  poller_daemon.py   │──── (readings) ───┤  app.py  │──── Web Dashboard
   EdgeSwitch (API)─┤  (Persistent daemon │                    │ (Flask)  │     (30s auto-refresh)
   SwOS (API) ──────┤   every N seconds)  │                    └──────────┘
   OLTCloud (API) ──┤                     │
                    └─────────────────────┘
```

- **`poller_daemon.py`**: Persistent telemetry collector. Polls target platforms every `poll_interval_seconds` and records measurements into a lightweight SQLite database (`ts, entity, metric, value, text_value`). Reuses sessions, cookies, and SSH tunnels across cycles to avoid log spam on embedded devices.
- **`app.py`**: Lightweight Flask backend serving the static UI and three clean JSON API endpoints:
  - `/api/state`: Latest system-wide readings.
  - `/api/history`: Time-series historical data for trends and graphing.
  - `/api/config`: Sanitized topology layout (no credentials exposed to the frontend).
- **`src/static/index.html`**: Zero-build vanilla JavaScript single-page application with responsive status indicators (Green / Yellow / Red).

---

## 💡 Why Direct Polling + SQLite instead of Generic SNMP?

Many carrier and wireless appliances expose HTTP/SSH management APIs with richer telemetry than their vendor SNMP MIB implementations (which are often incomplete or inconsistent across firmware revisions). 

This project provides a functional reference implementation for communicating with proprietary interfaces directly, storing historical metrics in SQLite without requiring a heavy monitoring stack (e.g. Zabbix, LibreNMS).

---

## 📦 Installation & Configuration

1. **Clone the repository:**
   ```bash
   git clone https://github.com/PabloIan92/isp-network-monitor.git
   cd isp-network-monitor
   ```

2. **Set up virtual environment:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: .\venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

3. **Configure devices:**
   ```bash
   cp config.example.yaml config.yaml
   # Edit config.yaml with your device credentials
   ```
   *(Note: `config.yaml` is excluded by `.gitignore` to prevent committing secrets).*

4. **Run locally:**
   ```bash
   MONITOREO_CONFIG=$(pwd)/config.yaml python3 src/poller_daemon.py
   MONITOREO_CONFIG=$(pwd)/config.yaml python3 src/app.py
   ```

### Running as a Systemd Service

Copy service definitions to `/etc/systemd/system/`:
```bash
sudo cp systemd/*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now monitoreo-poller.service monitoreo-dashboard.service
```

---

## 📚 Platform Integration Guides

Technical notes, gotchas, and authentication flows documented in [`docs/`](docs/):
- [`docs/mikrotik.md`](docs/mikrotik.md) — RouterOS SSH commands, v6 vs v7 health parsing, PSU voltage.
- [`docs/aircontrol.md`](docs/aircontrol.md) — Ubiquiti AirControl session authentication and CPE cluster rules.
- [`docs/netonix.md`](docs/netonix.md) — Netonix form POST login, telemetry endpoints, fan/temperature thresholds.
- [`docs/oltcloud.md`](docs/oltcloud.md) — ONU lifecycle states (Online, Sem Energia / Dying Gasp, Loss), optical power.
- [`docs/edgeswitch.md`](docs/edgeswitch.md) — Ubiquiti EdgeSwitch token-based authentication.
- [`docs/swos.md`](docs/swos.md) — MikroTik SwOS digest auth and proprietary binary format decoding.

---

## 🤖 Agentic Assistance Skill

This repository includes an agentic skill at [`.claude/skills/isp-network-monitor/SKILL.md`](.claude/skills/isp-network-monitor/SKILL.md) providing step-by-step guidance for testing device connectivity, adding new vendor platforms, and diagnosing network alerts.

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
