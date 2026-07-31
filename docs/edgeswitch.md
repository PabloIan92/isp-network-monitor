# Ubiquiti EdgeSwitch

No confundir con Netonix ni con UISP — es una línea de producto y una API
totalmente distintas, aunque convivan en la misma red WISP. Un switch que el
inventario histórico marcaba como "otra unidad Netonix" puede en realidad ser
un EdgeSwitch; confirmalo entrando directo a la IP con el navegador antes de
asumir qué plataforma es.

## Login

```
POST https://<host>/api/v1.0/user/login
Content-Type: application/json

{"username": "...", "password": "..."}
```

El token de sesión viene en el **header de la respuesta**, no en el body:

```
x-auth-token: <token>
```

Mandalo en cada request siguiente como header `x-auth-token`. Si una llamada
da 401/403, volvé a loguear una vez y reintentá.

## Estadísticas

```
GET https://<host>/api/v1.0/statistics
```

Devuelve una **lista** (no un objeto) — tomá el primer elemento. Trae CPU,
RAM, uptime del dispositivo, y por interfaz: contadores de errores/paquetes
descartados.

## Gotcha: no todos los modelos exponen temperatura

Algunos modelos de EdgeSwitch devuelven `"temperatures": []` — sin ningún
sensor térmico expuesto por API. No diseñes el semáforo de salud asumiendo
que vas a tener temperatura para todos los switches; para estos modelos,
basate en errores de puerto (`errors`/`dropped` por interfaz) como única
señal de problema.
