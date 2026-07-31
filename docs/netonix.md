# Netonix (switches WISP)

La documentación pública de Netonix no menciona un login limpio por API —
pero existe: es un simple POST de formulario HTML al backend PHP viejo del
equipo. No hay CSRF token que juntar a mano.

## Login

```
POST http(s)://<host>/index.php
Content-Type: application/x-www-form-urlencoded

username=...&password=...
```

Si el login fue exitoso, la respuesta trae una cookie `PHPSESSID`. Si no
aparece esa cookie, las credenciales están mal — no confíes en el status
code HTTP solo (suele devolver 200 igual con credenciales incorrectas).

Algunos switches están configurados para redirigir todo a HTTPS (certificado
propio, normalmente self-signed) — probá `scheme: https` con
`verify=False` si `http` no funciona.

## Telemetría en vivo

```
GET /api/v1/bootid            -> {"BootID": "..."}
GET /api/v1/status/30sec?<BootID>
```

El `BootID` va como query string pegado (no como parámetro nombrado) — es
una particularidad de esta API, hay que armar la URL como
`f"{base}/api/v1/status/30sec?{bootid}"`, no `params={"bootid": bootid}`.

La respuesta trae, entre otras cosas: `CPU_Temp`, `Board_Temp`, `Uptime`,
`Fan_Speeds` (array), y — según el modelo de fuente —
`DCDC_Input_Voltage`/`DCDC_Output_Voltage` (modelos DC) o
`Board_48V`/`Board_24V` (modelos AC). **No asumas qué campos existen**: usá
`.get()` con manejo de `None`, un modelo AC no tiene ninguno de los campos
`DCDC_*` y tirará `KeyError` si accedés directo.

## Log del propio switch

```
GET /api/v1/syslog -> {"messages": "<texto multilinea>"}
```

Útil para correlacionar un evento de red (ej. una alerta de corte de luz en
otro sistema) contra lo que vio el switch: si el switch **no** tiene un
evento de reinicio/pérdida de energía en ese rango horario, el switch se
mantuvo alimentado y el problema fue en otro equipo aguas abajo.

## Nombres de puerto (topología)

```
GET /api/v1/config -> incluye "Ports": [{"Number": N, "Name": "...", "PoE": "...", ...}, ...]
```

Los nombres de puerto configurados por el instalador (ej. "Wifi", "ONU",
"Panel X") sirven para identificar rápido qué equipo está conectado a un
puerto que empieza a flapear, sin tener que ir al sitio físico primero.

## El "medidor" de temperatura de la UI no es una alarma real

La UI web de Netonix pinta un gauge de temperatura con un gradiente de color
de 0 a 125°C — a simple vista parece un indicador de severidad, pero es
puramente decorativo (se puede confirmar leyendo los valores hexadecimales de
color del propio DOM: el gradiente es continuo, no tiene un "salto" en
ningún umbral). **No repliques esa escala de colores como si fuera un umbral
real de alarma.** Los valores de `Board_Temp` normales en producción pueden
sentarse cómodamente en 45-49°C sin ninguna anomalía — confirmá el rango
normal de tu propio hardware con el histórico real (ver más abajo) en vez de
adivinar un umbral.

## Umbrales: usá el histórico real, no un número que "suena razonable"

Antes de fijar un umbral de rojo/amarillo para board_temp o cualquier otra
métrica, mirá al menos 24-48hs de histórico de varios equipos del mismo
modelo. Un umbral puesto "a ojo" puede terminar marcando en rojo la mitad de
la flota en operación completamente normal — un umbral demasiado sensible es
tan malo como uno que no dispara nunca (fatiga de alertas).

## Falla de fan: exigí que sea sostenida

Netonix ciclan los fans on/off según temperatura ("New Fan Mode") — un fan en
0 RPM en una sola lectura es comportamiento normal, no una falla. Para
distinguir un ciclado normal de una falla real, exigí varias lecturas
consecutivas (ej. 3, ~6 minutos con un poll cada 2min) con el fan en 0 **y**
la temperatura por encima de un umbral (si el equipo realmente necesitara el
fan y no lo tuviera, la temperatura subiría) antes de marcar la falla.
