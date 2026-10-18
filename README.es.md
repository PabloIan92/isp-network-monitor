# isp-network-monitor

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python: 3.10+](https://img.shields.io/badge/Python-3.10%2B-brightgreen.svg)](https://www.python.org/)

Un dashboard de monitoreo de red y demonio de recolección liviano, diseñado para infraestructura WISP (enlaces inalámbricos) y FTTH (fibra óptica).

En vez de tener abiertas cinco pestañas distintas para revisar routers MikroTik, radioenlaces Ubiquiti, switches de torre Netonix, EdgeSwitches, equipos SwOS y OLTs GPON, este proyecto unifica la telemetría física y de salud en un panel único que se refresca solo.

> **Nota**: Documentación en inglés disponible en [English README](README.md).

---

## El problema que resuelve

Quien administra una red mixta sabe lo molesto que es lidiar con paneles separados:
- **MikroTik RouterOS**: Winbox o comandos por SSH.
- **Ubiquiti AirMax / LTU**: AirControl o UISP.
- **Switches Netonix**: Web propietaria en switches de torre.
- **Ubiquiti EdgeSwitch y MikroTik SwOS**: Consolas web con sus propios esquemas de autenticación.
- **OLTs GPON (ej. OLTCloud)**: Portales web con estados de ONUs y niveles ópticos.

Cuando una torre se queda sin 220V, una batería baja de 24V o un enlace pierde señal por clima, entrar a cinco sistemas distintos para saber qué pasó quita demasiado tiempo.

`isp-network-monitor` corre un único proceso en Python que consulta la salud física de los equipos (voltajes, temperaturas, RPM de coolers, potencia óptica de recepción, SNR inalámbrico, contadores de error en puertos) y guarda las lecturas en SQLite. Un backend minimalista en Flask sirve el dashboard oscuro en JS vanilla, sin pasos de compilación ni dependencias pesadas.

---

## Arquitectura

```
                    ┌────────────────────────┐
   MikroTik (SSH) ──┤                        │
   AirControl (API)─┤                        │      SQLite       ┌────────────┐
   Netonix (API) ───┤   poller_daemon.py     │──── (readings) ───┤   app.py   │──── Dashboard Web
   EdgeSwitch (API)─┤   (servicio de fondo   │    [modo WAL]     │  (Flask)   │     (auto-refresco 30s)
   SwOS (API) ──────┤    en systemd)         │                   └────────────┘
   OLTCloud (API) ──┤                        │
                    └────────────────────────┘
```

- **`poller_daemon.py`**: Proceso persistente (en systemd). Mantiene abiertas las sesiones SSH y reutiliza tokens HTTP entre ciclos para no llenar los logs de auditoría de los equipos con inicios de sesión constantes.
- **SQLite (Modo WAL)**: Almacenamiento rápido y sin mantenimiento externo. Usa dos tablas (`readings` y `poller_runs`) con índices compuestos para consultas de estado e histórico.
- **`app.py`**: Servicio Flask ligero con tres endpoints de solo lectura:
  - `/api/config`: Topología sanitizada (nombres de equipos, fuentes de poder, enlaces) sin contraseñas ni secretos.
  - `/api/state`: Últimas lecturas registradas para todos los equipos.
  - `/api/history`: Series temporales para gráficos de tendencia.
- **`src/static/index.html`**: Dashboard en HTML/CSS/JS vanilla. Sin Node.js ni build step, con carga instantánea y semáforo visual (verde / amarillo / rojo).

---

## ¿Por qué SQLite y polling directo en vez de Zabbix o SNMP?

Si en tu red contás con soporte SNMP completo y homogéneo en el 100% de tus equipos y ya tenés un cluster de Zabbix o LibreNMS andando, conviene mantenerlo.

Sin embargo, en despliegues reales de campo:
1. Varios equipos de torre (como ciertas versiones de SwOS o Netonix) tienen implementaciones SNMP incompletas, lentas o con bugs en sus MIBs.
2. Hacer consultas SNMP pesadas a través de enlaces inalámbricos saturados suele provocar pérdida de paquetes UDP y timeouts.
3. Métricas críticas como voltajes de doble fuente redundante o diagnósticos ópticos SFP (DDM) suelen obtenerse de forma mucho más directa y rápida consultando la API o la consola del equipo.

Este proyecto fue pensado para ser 100% autocontenido. No necesita bases de datos externas (ni MySQL, ni Postgres, ni InfluxDB, ni Redis), corre sin problemas en un VPS chico o en una Raspberry Pi, y completa el ciclo de recolección en menos de 3 segundos.

---

## Inicio rápido y Modo Demo

Podés probar el dashboard localmente en segundos con datos sintéticos, sin necesidad de hardware físico:

```bash
# 1. Clonar el repositorio
git clone https://github.com/PabloIan92/isp-network-monitor.git
cd isp-network-monitor

# 2. Configurar entorno virtual
python3 -m venv venv
source venv/bin/activate   # En Windows: .\venv\Scripts\activate
pip install -r requirements.txt

# 3. Iniciar modo demo interactivo
python3 src/demo.py
```

Abrí `http://localhost:8090` en tu navegador. Vas a ver el dashboard funcionando con métricas sintéticas realistas (voltajes de fuentes redundantes, potencias ópticas, enlaces y temperaturas).

### Ejecutar Pruebas Automatizadas

El proyecto incluye tests unitarios que validan las respuestas de la API, la sanitización de secretos y la serialización del estado:

```bash
python3 -m unittest discover tests
```

---

## Despliegue en Producción

### 1. Configuración

Copiá el archivo de ejemplo y completá las direcciones de tus equipos y credenciales de solo lectura:

```bash
cp config.example.yaml config.yaml
chmod 600 config.yaml
$EDITOR config.yaml
```

> **Buenas prácticas**: Creá siempre usuarios dedicados con permisos de solo lectura (por ejemplo, grupo `read` en MikroTik) para el monitoreo. Nunca uses usuarios con permisos de escritura.

### 2. Prueba en primer plano

Verificá la conectividad y las lecturas antes de crear los servicios del sistema:

```bash
# Probar el recolector
MONITOREO_CONFIG=$(pwd)/config.yaml python3 src/poller_daemon.py

# Probar el servidor web
MONITOREO_CONFIG=$(pwd)/config.yaml python3 src/app.py
```

### 3. Instalar como servicios de systemd

Los archivos de unidad se encuentran en la carpeta `systemd/`:

```bash
sudo cp systemd/*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now monitoreo-poller.service monitoreo-dashboard.service
```

Podés verificar el estado con `systemctl status monitoreo-poller`.

---

## Seguridad y Acceso

- **Red privada únicamente**: El dashboard escucha en el puerto `8090` sin autenticación integrada. Mantenelo accesible exclusivamente mediante una VPN segura de gestión (WireGuard, Tailscale) o detrás de un reverse proxy (Caddy / Nginx) con autenticación básica y HTTPS.
- **Recolección de solo lectura**: El demonio únicamente consulta telemetría de estado. En ningún momento ejecuta modificaciones de configuración ni escrituras en los equipos.
- **Privacidad por diseño**: El sistema monitorea variables físicas del equipamiento (voltajes, temperaturas, errores de paquetes, potencias ópticas, SNR). **No** inspecciona tráfico de usuarios ni almacena datos personales de clientes (cero PII).

---

## Documentación por Plataforma

Detalles técnicos, particularidades de autenticación y consejos prácticos para cada equipo:

- [docs/mikrotik.md](docs/mikrotik.md) — Comandos SSH en RouterOS, diferencias entre v6 y v7, fuentes redundantes.
- [docs/aircontrol.md](docs/aircontrol.md) — Sesiones en Ubiquiti AirControl, agrupamiento de radios, umbrales de SNR.
- [docs/netonix.md](docs/netonix.md) — Autenticación web en Netonix WS, monitoreo de RPM de fans, límites térmicos.
- [docs/oltcloud.md](docs/oltcloud.md) — Integración con OLTs GPON, estados de ONU (`Online`, `LOS`, `Sin energía`), potencias ópticas.
- [docs/edgeswitch.md](docs/edgeswitch.md) — Tokens de sesión en Ubiquiti EdgeSwitch, contadores de error en puertos.
- [docs/swos.md](docs/swos.md) — Autenticación digest y telemetría binaria en MikroTik SwOS.

---

## Licencia

Este proyecto está publicado bajo la [Licencia MIT](LICENSE) — libre para usar, modificar y adaptar a tu propia infraestructura.
