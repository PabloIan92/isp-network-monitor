# isp-network-monitor

> **Unified Network Telemetry & Dashboard for Multi-Vendor WISP/FTTH Infrastructure**  
> An open-source reference architecture and telemetry dashboard consolidating MikroTik (RouterOS/SwOS), Ubiquiti (AirControl/EdgeSwitch), Netonix, and OLTCloud into a unified SQLite-backed interface.

Un dashboard unificado y motor de telemetría open source para monitorear infraestructura de red WISP/FTTH multimarca (routers, antenas, switches, OLTs), diseñado como una arquitectura de referencia modular que consolida MikroTik + Ubiquiti AirControl + Netonix + OLTCloud + Ubiquiti EdgeSwitch + MikroTik SwOS en un solo lugar.

No es un producto genérico empaquetado — es una referencia funcional y desacoplada con documentación técnica de cómo interactuar con cada plataforma (auth, endpoints, sesiones persistentes y manejo de telemetría), pensado para adaptar a cualquier topología de red.

## Demostración local (Modo Demo)

El proyecto incluye un modo demo con topología y métricas sintéticas de laboratorio. No abre conexiones externas, no requiere hardware físico ni carga credenciales reales. Permite ejecutar y desarrollar sobre el dashboard y su API con datos simulados de forma inmediata:

```powershell
python -m pip install flask pyyaml
$env:MONITOREO_DEMO = "1"
python src/app.py
# Abrir http://127.0.0.1:8090
```

En Linux/macOS:
```bash
MONITOREO_DEMO=1 python3 src/app.py
```

El servidor escucha en `127.0.0.1:8090` por defecto. Para despliegues con proxy o VPN, se puede configurar `MONITOREO_HOST` explícitamente.

## Arquitectura

```
                    ┌─────────────────────┐
   MikroTik (SSH) ──┤                     │
   AirControl (API)─┤                     │      SQLite       ┌──────────┐
   Netonix (API) ───┤  poller_daemon.py   │──── (readings) ───┤  app.py  │──── dashboard web
   EdgeSwitch (API)─┤  (systemd, corre    │                    │ (Flask)  │     (auto-refresh 30s)
   SwOS (API) ──────┤   cada N segundos)  │                    └──────────┘
   OLTCloud (API) ──┤                     │
                    └─────────────────────┘
```

- **`poller_daemon.py`**: un solo proceso persistente (no cron) que consulta
  cada plataforma cada `poll_interval_seconds` y guarda lecturas en SQLite
  (tabla `readings`, esquema `ts, entity, metric, value, text_value`).
  Reusa conexiones/sesiones entre ciclos (SSH persistente, cookies de sesión,
  tokens) para no generar ruido de "login" constante en los logs de los
  equipos.
- **`app.py`**: Flask, sirve el dashboard estático y tres endpoints JSON:
  `/api/state` (última lectura de todo), `/api/history` (histórico de una
  métrica puntual, para gráficos/tendencia), `/api/config` (topología sin
  credenciales, para que el frontend sepa qué tarjetas dibujar).
- **`src/static/index.html`**: dashboard de una sola página, sin build step
  (JS vanilla), con semáforo verde/amarillo/rojo por equipo.

## Por qué SQLite + polling en vez de SNMP/Zabbix/LibreNMS

Todas las plataformas de este README exponen HTTP/SSH pero **no
necesariamente SNMP útil** (o el soporte es parcial/inconsistente entre
modelos). Este proyecto prioriza "andar rápido con lo que ya tenés acceso"
sobre una plataforma de monitoreo genérica. Si tu red sí tiene buen soporte
SNMP en todo el parque, considerá LibreNMS/Zabbix en su lugar — este
proyecto sigue siendo útil como referencia de cómo autenticarse a cada
plataforma propietaria.

## Instalación

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp config.example.yaml config.yaml
$EDITOR config.yaml   # completar hosts/credenciales reales - ver docs/

# Probar en foreground antes de instalar como servicio:
MONITOREO_CONFIG=$(pwd)/config.yaml python3 src/poller_daemon.py
MONITOREO_CONFIG=$(pwd)/config.yaml python3 src/app.py
```

`config.yaml` está en `.gitignore` — nunca se commitea, tiene credenciales.

### Como servicio (systemd)

Copiá `systemd/*.service` a `/etc/systemd/system/`, ajustá los paths si no
usás `/opt/monitoreo`, y:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now monitoreo-poller.service monitoreo-dashboard.service
```

Corré el poller y el dashboard con un usuario de servicio dedicado (sin
privilegios de más), no como root.

### Exponer el dashboard

El dashboard escucha en `0.0.0.0:8090` sin autenticación propia — no lo
expongas directo a Internet. Opciones simples: un túnel/VPN existente
(Tailscale Funnel, WireGuard), un reverse proxy con auth básica, o dejarlo
solo accesible dentro de tu red interna.

## Qué falta / lo dejamos afuera a propósito

- **Sin autenticación en el dashboard.** Agregala vos según tu entorno (proxy
  con basic auth, o Flask-Login si necesitás usuarios).
- **Sin alertas push (Telegram/Slack/etc).** El dashboard es pull (lo mirás
  vos); si querés alertas activas, es un cron/script aparte que lea la misma
  SQLite y dispare un webhook cuando algo cruce el umbral.
- **Sin autodescubrimiento de equipos.** La topología es la que pongas en
  `config.yaml` a mano.

## Documentación por plataforma

- [`docs/mikrotik.md`](docs/mikrotik.md) — RouterOS por SSH, v6 vs v7, PSU/voltaje, firewall.
- [`docs/aircontrol.md`](docs/aircontrol.md) — Ubiquiti AirControl, login, reglas de auto-reboot.
- [`docs/netonix.md`](docs/netonix.md) — login por form POST, telemetría, umbrales de fan/temp.
- [`docs/oltcloud.md`](docs/oltcloud.md) — estados de ONU (online/sin energía/loss/etc), potencia óptica.
- [`docs/edgeswitch.md`](docs/edgeswitch.md) — Ubiquiti EdgeSwitch, token de sesión.
- [`docs/swos.md`](docs/swos.md) — MikroTik SwOS, formato propietario, digest auth.

## Skill de Asistencia

Este repo incluye un [skill](.claude/skills/isp-network-monitor/SKILL.md) que
guía el proceso de configuración y adaptación de este proyecto a diferentes
topologías y entornos de red multimarca (paso a paso de integraciones, verificación
de conectividad y buenas prácticas). Copiá la carpeta
`.claude/skills/isp-network-monitor/` a tu propio entorno de desarrollo.

## Licencia

MIT — ver `LICENSE`.
