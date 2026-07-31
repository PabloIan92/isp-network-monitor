# OLTCloud (gestión centralizada de OLTs GPON)

Plataforma que centraliza varias OLTs (potencialmente de distintas marcas)
bajo una sola API. Si tu ISP usa otro software de gestión de OLT, esta
sección no aplica directo, pero el patrón (login por token + paginar el
listado de ONUs + clasificar por estado) sí es reutilizable.

## Login

```
POST <base_url>/api/token
{"username": "...", "password": "..."}
-> {"access": "<token>"}
```

Token bearer, se manda como `Authorization: Bearer <token>` en cada
request. Reusalo mientras no expire (igual que las demás sesiones); si una
llamada da 401/403, pedí un token nuevo una sola vez y reintentá.

## Listado de ONUs

```
GET <base_url>/api/v2/ftth/equipment/list?page=N
-> {"results": [...], "next": <bool o url o null>}
```

Paginar hasta que `next` sea falsy. Cada ítem trae (entre otros campos):
`olt` (nombre de la OLT a la que pertenece), `status` (string), `device_rx`
(potencia óptica recibida en dBm).

## Estados de ONU — no asumas el significado, confirmalo contra tu propia data

Los strings de `status` observados en producción (pueden variar según
firmware/idioma del vendor detrás de OLTCloud):

| Estado          | Significado real                                              | ¿Es un problema de red? |
|-----------------|----------------------------------------------------------------|--------------------------|
| `Online`        | Funcionando normal                                              | —                         |
| `Sem Energia`   | El ONU avisó ("dying gasp") que perdió alimentación eléctrica del lado del cliente antes de apagarse | **No** — corte de luz del domicilio/zona, fuera de tu control |
| `LOSS`          | Pérdida de señal óptica con el ONU aún energizado (fibra cortada, conector sucio, patchcord dañado, falla de hardware) | **Sí** — el único estado que amerita revisión de red/fibra |
| `Inativo`       | ONU dado de baja/desprovisionado (ej. cliente canceló servicio)  | No — administrativo      |
| `Desabilitada`  | Deshabilitado a propósito por un administrador                  | No — administrativo      |

**No mezcles estos estados en un solo "offline" genérico** para calcular el
semáforo de salud de una OLT — si lo hacés, un corte de luz de zona (que
puede afectar a cientos de ONUs de golpe y no depende de vos) va a teñir de
rojo permanentemente una OLT que en realidad está sana. Calculá el % de
salud excluyendo del denominador los estados administrativos/no-accionables,
y contando como "problema real" solo `LOSS` (y cualquier estado
verdaderamente no reconocido, como catch-all para detectar casos nuevos).

## Potencia óptica como indicador preventivo

`device_rx` por debajo de un umbral (ej. -28dBm) para un ONU que sigue
`Online` es la señal más temprana de una fibra degradándose — mucho antes de
que el cliente llame por el corte total. Filtrá el valor sentinel que use tu
proveedor para "sin lectura" (en la práctica se vio `-99.99` como placeholder,
no como una lectura real mala) antes de contarlo como potencia crítica.
