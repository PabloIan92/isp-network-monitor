# MikroTik RouterOS

Acceso vía SSH, ejecutando un mini-script RouterOS por ciclo de poll. No hay
"API REST" involucrada — es la misma consola que usarías por Winbox/terminal,
pero automatizada.

## Cuenta de acceso

**Nunca uses la cuenta admin para el poller.** Creá una cuenta de solo lectura:

```
/user group add name=monitoreo-ro policy=read,test,winbox
/user add name=monitoreo group=monitoreo-ro password=<password largo>
```

El grupo `read` (o uno custom con solo `read`) alcanza para todo lo que hace
este poller (lecturas de `/system resource`, `/system health`, `/interface
ethernet`). No necesita `write` ni `policy`.

## Conexión persistente, no reconectar cada ciclo

Si el poller abre una conexión SSH nueva cada 1-2 minutos, el log del router
se llena de líneas `user X logged in via ssh` — con varios routers y un
intervalo corto, son cientos de líneas por día sin ninguna señal útil, y
puede alertar a quien monitoree el log.

**Solución:** mantené una conexión `paramiko.SSHClient` viva por router,
reconectando solo si `transport.is_active()` da `False`. Ver
`get_ssh_client()` en `src/poller_daemon.py`.

## El patrón `:put` para leer datos limpios

En vez de parsear la salida "bonita" de un comando (que trae formato de
tabla, colores ANSI, etc.), pedile a RouterOS que imprima pares
`clave=valor` explícitos:

```
:put ("cpu_load=" . [/system resource get cpu-load])
```

Encadená todas las lecturas de un ciclo en un solo `exec_command` separadas
por `;` — **un solo comando suelto falla** con `expected command name`:

```
:put ("cpu_load=" . [/system resource get cpu-load]); :put ("uptime=" . [/system resource get uptime])
```

El stdout resultante son líneas `clave=valor` fáciles de parsear con
`line.split("=", 1)`.

## Diferencias RouterOS v6 vs v7

- **`/system health`**: en v7 es una tabla, hay que buscar la fila:
  `[/system health get [find name=voltage] value]`. En v6 la propiedad se lee
  directo: `[/system health get voltage]`. Confirmá la versión real
  (`/system resource print`) por cada router — no asumas por antigüedad del
  hardware, puede haber sido actualizado.
- **Voltaje en `/system health`**: v6 devuelve **decivoltios** (el valor
  crudo hay que dividirlo por 10). v7 devuelve voltios reales directamente.
  Esto **no está documentado en ningún lado** — se confirma comparando la
  lectura contra un tester real o contra la UI de Winbox, no asumiendo.
- **Netwatch**: en v7 `/tool netwatch add` acepta `name=`/`type=`; en v6 esos
  parámetros no existen, solo `comment=`.

## PSU / voltaje: no todos los modelos son iguales

Hay al menos 3 formas distintas de reportar alimentación según el modelo:

| `psu_style`      | Qué expone                          |
|------------------|--------------------------------------|
| `simple_voltage` | una sola propiedad `voltage`          |
| `psu_voltage`     | `psu1-voltage` / `psu2-voltage` (fuentes redundantes con voltaje) |
| `psu_state`       | `psu1-state` / `psu2-state` (texto `ok`/`fail`, sin voltaje numérico) |

Confirmá cuál tiene cada router probando el comando a mano antes de asumir.

## Errores de interfaz (FCS/CRC) como indicador temprano

`rx-fcs-error` y `rx-code-error` crecientes en un uplink, comparados contra
`rx-packet` (para sacar una tasa, no un contador absoluto que siempre crece),
son la señal más temprana de un módulo SFP o cable degradándose — mucho antes
de que el link caiga del todo. Guardá el contador crudo en cada poll y
calculá la derivada en el frontend/consulta, no acumules vos mismo un
"contador de errores" separado.

## Alertas nativas vía Netwatch (alternativa/complemento)

Si no querés correr un poller externo para ciertas métricas, RouterOS puede
alertar solo: un Netwatch "creativo" apuntado a una IP fija (ej. 8.8.8.8) que
en realidad ignora si esa IP responde y en su lugar ejecuta un script que lee
`/system health` y dispara un webhook (ej. a un bot de Telegram) si cruza un
umbral, usando una variable global para no repetir la alerta (avisa una vez
al cruzar el umbral, y una vez al "normalizarse"). Es un patrón útil para
routers puntuales sin meterlos todos en el poller central.

## Gotchas encontrados en producción

- Un router puede tener el servicio SSH habilitado pero igual no responder:
  revisá las reglas de firewall (`/ip firewall filter print`) antes de asumir
  que el servicio está apagado — un `drop` genérico de "todo lo demás" puede
  estar bloqueando el puerto SSH para tu origen aunque el servicio esté up.
- Si un router no tiene SSH accesible pero sí Winbox (puerto TCP por defecto
  8291), WebFig (por defecto el mismo puerto que Winbox más 99, revisar
  `/ip service print`) es una alternativa navegable para relevar/config,
  aunque no sirve para polling automatizado periódico.
