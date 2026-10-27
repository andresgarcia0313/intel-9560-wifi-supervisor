<!-- lang: es-CO -->
# 0002 - Respaldo de internet por el celular sin sacar al Dell de la red local

Idioma: español de Colombia (es-CO). Fecha: 2026-10-26. Estado: aceptada.

## Contexto

Se pidió que, sin internet, el Dell use la wifi que comparte el celular (`wifi-celular`) y, si no está, el
internet por el Bluetooth del celular. No hay cable USB del celular conectado. El 26-oct el router
falló dos veces (16:14 y 17:52): otro equipo de la casa y el Dell perdieron la wifi a la vez y la red local volvió en
minutos. El NFS que sirve el Dell y el tráfico de k3s van por la red local cuando existe.

## Decisión

El controlador decide según lo que mide, en el módulo `respaldo.py`:

| Situación | Acción |
|---|---|
| Red local responde, sin internet | Solo el Bluetooth del celular; la wifi sigue en la casa |
| Router ausente | Bluetooth de inmediato; a los `espera_celular` (180 s) la wifi del celular, si se ve |
| En la wifi del celular | Cada `volver_casa` (120 s) busca la casa y vuelve en cuanto la ve |
| Wifi con internet `soltar_bt` (300 s) seguidos | Suelta el Bluetooth |

La ruta la elige NetworkManager: la verificación de conectividad penaliza la wifi sin internet y gana la
del Bluetooth (métrica 1000). En la wifi del celular, una falla cuenta como `proveedor`: no se toca el
hardware por una puerta de enlace que en esa red no existe.

## Alternativas descartadas

- **Pasar la wifi al celular apenas falta internet (orden literal).** Sacaría al Dell de la red local
  mientras el resto del clúster sigue en ella: el NFS y k3s se cortarían por ganar solo internet para el Dell.
- **Bluetooth siempre conectado, como en el portátil principal.** Más simple, pero el Bluetooth comparte el radio con
  la wifi de la 9560; se sube solo cuando hace falta.
- **Que NetworkManager pase solo a `wifi-celular` (autoconexión).** Lo haría en cada reinicio corto del router y
  no volvería a la casa mientras siga asociado; el perfil queda con `autoconnect=false`.

## Consecuencias

- Con el router ausente y el Dell en el celular, los servicios del clúster pueden gastar datos móviles.
- El emparejamiento del celular y el perfil `bt-celular` se crean a mano una vez (README).
