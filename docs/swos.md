# MikroTik SwOS (switches, no RouterOS)

Algunos switches MikroTik (línea CRS con SwOS en vez de RouterOS, ej.
CRS326-24S+2Q+) exponen un endpoint HTTP con un **formato propietario, no
JSON**, y autenticación **HTTP Digest** (no Basic).

## Auth

```python
import requests
from requests.auth import HTTPDigestAuth

r = requests.get(f"http://{host}/sys.b", auth=HTTPDigestAuth(user, password), timeout=10)
```

Si usás Basic en vez de Digest, vas a recibir 401 aunque las credenciales
sean correctas.

## Formato de respuesta (pseudo-objeto, no JSON)

El body de `/sys.b` es algo así:

```
{temp:'2c',upt:0x1234,fan1:0x0f1e,fan2:0x0000,...}
```

- Claves sin comillas.
- Strings entre comillas simples, a veces hex-encoded.
- Enteros con prefijo `0x` (hexadecimal).

`json.loads` no lo va a parsear. Escribí un parser mínimo a mano (ver
`parse_swos_blob()` en `src/poller_daemon.py`): separar por `,` a nivel
superior, partir cada `clave:valor` por el primer `:`, y decidir el tipo
según el prefijo del valor (`'...'` → string, `0x...` → int hex, resto →
dejar como string crudo).

Campos típicos: `temp` (temperatura), `upt` (uptime en décimas de segundo —
dividir por 10 para segundos), `fan1`..`fan4` (RPM), `p1v`/`p2v` (voltaje de
PSU en milivoltios — dividir por 1000), `p1s`/`p2s` (estado de PSU, `1` = ok).

## Gotcha: no todos los "fan slots" crudos son fans reales

En al menos un modelo, la API expone 4 campos `fan1`..`fan4`, pero la UI
propia del equipo (revisando el minified JS que la sirve — buscar el string
`"FAN"` en el bundle) solo muestra 3 fans reales, con un **mapeo no
secuencial**: por ejemplo `FAN1` de la UI corresponde al `fan1` crudo, pero
`FAN2` de la UI corresponde al `fan4` crudo, y el `fan2` crudo es un slot
fantasma sin fan físico en esa placa.

**No asumas un mapeo 1:1 secuencial.** Si el conteo de fans que mostrás no
coincide con lo que el técnico ve físicamente en el equipo, es señal de que
hay un slot fantasma — confirmá el mapeo real leyendo el JS de la UI del
equipo o preguntando al técnico que lo tiene físicamente en frente, y
configurá explícitamente qué índices son reales (`fan_slots` en
`config.yaml`) en vez de iterar `1..4` a ciegas.
