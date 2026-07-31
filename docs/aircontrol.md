# Ubiquiti AirControl

Plataforma de gestión de antenas/radioenlaces (airOS: airFiber, airMAX, etc).
Puede haber más de una instancia (ej. una para antenas de clientes, otra para
enlaces de backbone/paneles) — tratalas como instancias independientes, cada
una con su propia sesión.

## Login

```
POST https://<host>:9082/api/v1/login
Content-Type: application/json

{
  "username": "...",
  "password": "...",
  "eulaAccepted": true,
  "verifyCsrfToken": true
}
```

La sesión se mantiene por cookie en el `requests.Session()` — no hay que
extraer ni reenviar ningún token manualmente. Reusá la sesión ~10-15 minutos
antes de loguear de nuevo (ver `AIRCONTROL_SESSION_MAX_AGE` /
`session_max_age_seconds`); si una llamada devuelve 401/403, descartá la
sesión cacheada y logueá de nuevo una sola vez.

## Listar dispositivos

```
GET https://<host>:9082/api/v1/devices?limit=2000
```

La respuesta trae `{"count": N, "results": [...]}` — **no asumas que la raíz
del JSON ya es la lista**, hay que leer `.results`.

Cada dispositivo trae `status.online` (bool) y las métricas de señal bajo
`overview` u `properties` según versión — buscá claves que contengan
`signal`/`noise` + `~current` (sufijo típico de esta API para "valor actual"
vs. histórico) y restá para sacar SNR.

## Endpoint de reglas (auto-reboot, etc.) — no documentado públicamente

```
GET/PATCH/DELETE https://<host>:9082/api/v1/rules
```

AirControl permite crear reglas tipo "reiniciar antena si uptime > X horas".
Son útiles pero **disparan a cualquier hora del día** (no configurable),
lo cual puede tirar antenas en medio de un pico de uso. Si preferís controlar
el timing (ej. reiniciar solo de madrugada), es mejor:

1. Desactivar la regla nativa. Ojo: `PATCH` por API puede devolver
   `403 action_not_allowed` **incluso con rol Administrator** — en ese caso
   la única forma que funcionó fue togglear el checkbox real en la UI web
   (inspeccionar el DOM para encontrar el ID del toggle).
2. Reimplementar el reboot en un cron propio, llamando:
   ```
   POST https://<host>:9082/api/v1/tasks
   {"name": "reboot", "args": {"sessionId": 0, "device_ids": ["<id>", ...]}}
   ```
   con la ventana horaria que prefieras.

## Gotcha metodológico importante

Un cluster de varios clientes cayendo **al mismo tiempo, con heartbeats casi
idénticos**, se ve idéntico tanto a una falla de infraestructura compartida
(un panel/AP común) como a un **corte de luz de zona** (cada domicilio pierde
electricidad más o menos a la vez). **Antes de concluir "falla de red"**,
verificá el estado del panel/AP que agrupa a esos clientes — si el panel
sigue online, es corte de luz del lado del cliente, no un problema tuyo.
