<!-- lang: es-CO -->
# 0001 - Supervisor en espacio de usuario, sin driver propio ni firmware descompilado

Idioma: español de Colombia (es-CO). Fecha: 2026-10-25. Estado: aceptada.

## Contexto

La wifi Intel 9560 del Dell pierde la conexión varias veces por semana. Se buscaba un "controlador" que mejorara el código de recuperación existente sin riesgo de congelar el equipo. Revisamos:

- **El driver `iwlwifi`/`iwlmvm`.** Es software libre (GPL) y viene en el kernel 7.0: no hace falta descompilarlo.
- **El firmware.** El `iwlwifi-9000-pu-b0-jf-b0-46.ucode` (46.7e3e4b69.0) es un binario firmado por Intel. Si se modifica, la tarjeta no lo carga, y su licencia prohíbe la ingeniería inversa. Es la última versión que existe, y el driver no acepta una API mayor a la 46 (`cfg/9000.c`).
- **El backport de Intel (`backport-iwlwifi`, rama core105).** Tiene el mismo límite de API y ninguna corrección identificada para la 9560. Además, un módulo fuera del kernel se rompe en cada actualización.
- **Los datos de 30 días.** Hubo cero SYSASSERT y muchas pérdidas de conectividad que un reset PCI no arreglaba.

## Decisión

Construir un supervisor en Python, con solo la biblioteca estándar y como servicio de systemd. Mide por capas, diagnostica la causa y aplica remedios escalonados con respaldo. Usa las vías oficiales del driver: `send_echo_cmd`, `fw_restart`, `trans/reset`, `modprobe` y `sysfs` de PCI.

## Alternativas descartadas

- **Parchear y compilar `iwlwifi` (DKMS).** No hay un error del driver identificado que corregir. Un fallo en código del kernel sí puede congelar el equipo, que es justo lo que se quería evitar.
- **Descompilar el firmware.** Es inútil, porque no se puede cargar uno modificado, y lo prohíbe la licencia.
- **Seguir con el guardián en bash.** No distinguía causas, no tenía tope de reinicios y quedó ciego con el cable USB del celular (su prueba salía por el cable).

## Consecuencias

- Un error del supervisor solo lo afecta a él. systemd lo reinicia, y el guardián anterior queda de reserva.
- Según el código de iwlmvm 7.0 (`mvm/mac80211.c` e `iwl-modparams.h`), los parámetros `bt_coex_active`, `power_save`, `uapsd_disable` y `11n_disable=8` no tienen efecto en iwlmvm 7.0. Solo actúan `power_scheme=1` y `wifi.powersave=2` de NetworkManager. Por eso el Bluetooth se puede encender sin tocar la wifi: la coexistencia la hace siempre el firmware.
- El diagnóstico por causa deja datos para encontrar la raíz de las caídas, que hoy apunta al punto de acceso o al entorno de radio y no al firmware. Esto todavía es hipótesis.
