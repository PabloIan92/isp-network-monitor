---
name: isp-network-monitor
description: Build or extend a unified network monitoring dashboard for an ISP (MikroTik RouterOS/SwOS, Ubiquiti AirControl, Ubiquiti EdgeSwitch, Netonix, OLTCloud) that consolidates status/health of routers, antennas, switches and OLTs into one place instead of logging into each vendor platform separately. Use when the user wants to monitor their ISP infrastructure, add a new device/platform to an existing monitoring setup, or investigate a network alert.
---

# ISP Network Monitor

Este skill empaqueta el conocimiento (y el código de referencia) para armar
un dashboard de monitoreo unificado de la red de un ISP, integrando
plataformas que normalmente viven cada una en su propia UI: MikroTik
(RouterOS y SwOS), Ubiquiti AirControl, Ubiquiti EdgeSwitch, Netonix y
OLTCloud.

El código de referencia completo (poller + dashboard + docs por plataforma)
está en el repo que contiene este skill: `src/`, `docs/`, `config.example.yaml`.

## Cuándo usar esto

- El usuario quiere "ver todo en un solo panel" en vez de entrar a cada
  router/antena/switch por separado.
- Ya existe un dashboard armado con este patrón y hay que **sumar un equipo o
  plataforma nueva**.
- Hay que **investigar una alerta** (caída, temperatura, fan, potencia
  óptica) y conviene mirar el histórico guardado en vez de solo el estado
  puntual.

## Principio rector: no adivines, confirmá con evidencia

Cada plataforma de esta lista tiene comportamientos que **no están
documentados públicamente** (ver `docs/*.md` para el detalle de cada una:
formato de voltaje de MikroTik según versión, mapeo de fans en SwOS, qué
significa cada estado de ONU en OLTCloud, etc). El error más caro en este
tipo de proyecto es asumir un comportamiento "razonable" sin probarlo contra
el equipo real:

- Antes de fijar un umbral de alerta (temperatura, voltaje, etc), mirá
  histórico real de varios equipos del mismo tipo. Un umbral "a ojo" termina
  o sin disparar nunca, o marcando en rojo equipos sanos.
- Antes de asumir que un campo significa lo que su nombre en inglés/portugués
  sugiere (ej. "Sem Energia", "Inativo"), confirmá contra la data real qué
  proporción de equipos cae en ese estado y si correlaciona con algo
  accionable.
- Si un patrón de fallo parece afectar a muchos equipos a la vez (ej. varios
  clientes offline juntos), no concluyas "falla de red compartida" sin
  verificar el nodo/panel que los agrupa — puede ser un corte de luz de zona,
  que tiene la misma firma.
- Si algo "no responde", no asumas que el servicio está apagado — revisá
  firewall/reglas antes de descartar el equipo como inalcanzable.

## Flujo de trabajo para sumar una plataforma o equipo nuevo

1. **Preguntar, no adivinar credenciales/topología.** Pedile al usuario:
   marca/modelo del equipo, IP, usuario/contraseña, y para qué sirve (rol en
   la red). Si el usuario no sabe qué tipo de equipo es una IP dada, es
   válido investigar entrando directo (navegador, curl) antes de asumir de
   qué plataforma se trata — en la práctica, un dispositivo documentado como
   "switch X" resultó ser de un vendor completamente distinto al esperado.
2. **Autenticarse y explorar antes de escribir código.** Con curl/python
   suelto, confirmá el método de auth real (login form, JSON, digest, token)
   y qué endpoints existen — ver `docs/*.md` como punto de partida, pero
   confirmá contra el equipo real porque puede variar por firmware/modelo.
3. **Recién ahí, agregar la entrada a `config.yaml`** (nunca hardcodear
   credenciales en el código) y extender `poller_daemon.py` si es una
   plataforma nueva que el poller no soporta todavía, siguiendo el mismo
   patrón que las integraciones existentes (sesión/token cacheado, función
   `poll_<plataforma>()` que registra métricas vía `record()`).
4. **Verificar en vivo** que el poller efectivamente levanta el equipo nuevo
   (`/api/state` debe traer la entidad) antes de tocar el frontend.
5. **Agregar la tarjeta al dashboard** (`src/static/index.html`) reusando el
   patrón de color semáforo (verde/amarillo/rojo) ya establecido, con
   umbrales basados en histórico real del punto anterior, no en un número
   que "suena bien".
6. **Nunca commitear `config.yaml`** (contiene credenciales) — solo
   `config.example.yaml` con placeholders va al repo.

## Seguridad — no negociable

- Cuenta de solo lectura para cada equipo que la soporte (MikroTik: grupo
  `read`), nunca la cuenta admin de operaciones.
- El dashboard (`app.py`) no tiene autenticación propia — si se expone fuera
  de la red interna, tiene que ir detrás de un proxy con auth o una VPN/túnel
  (Tailscale, WireGuard), nunca expuesto directo a Internet.
- `config.yaml`, cualquier `.db` de datos, y logs van en `.gitignore` — jamás
  se publican en un repo, ni siquiera privado (es buena práctica separar
  secretos del código igual).

## Investigar una alerta existente

Si el usuario reporta una alerta puntual (ej. "se cayó tal antena", "tal
switch está en rojo"):

1. Mirar `/api/history?entity=<X>&metric=<Y>&hours=N` para ver si es un
   evento aislado (blip que se recuperó solo) o algo sostenido.
2. Si el equipo expone su propio log (Netonix `/api/v1/syslog`, por ejemplo),
   revisarlo directo — puede confirmar o descartar causas (ej. un switch que
   nunca perdió alimentación durante un "corte de luz" reportado en otro
   sistema, indica que el corte fue en un equipo aguas abajo, no en ese
   switch).
3. Si son varios equipos cayendo juntos, chequear el nodo/panel/uplink común
   antes de asumir causa compartida (ver principio rector arriba).
