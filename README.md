<!-- lang: es-CO -->
# Supervisor de wifi Intel Wireless-AC 9560 (iwlwifi) y su Bluetooth en Linux

Idioma: español de Colombia (es-CO). Hay un resumen en inglés justo abajo.

Este repositorio documenta un caso real y la solución que lo dejó estable. Es un Dell Latitude 3400 con wifi Intel Wireless-AC 9560 que trabaja 24/7 como servidor por wifi. La wifi se caía, a veces sin que el sistema lo notara, y el Bluetooth (que comparte el radio con la wifi) era el principal sospechoso. La solución no toca el kernel: es un supervisor en Python, sin dependencias, que mide por capas, diagnostica la causa y aplica solo el remedio que sirve, con protecciones para que nunca congele el equipo.

## Summary in English

**Hardware:** Intel Wireless-AC 9560 CNVi `[8086:9df0]` (rev 30) at `0000:00:14.3`, Bluetooth `8087:0aaa` (Jefferson Peak, USB), firmware `46.7e3e4b69.0` (`9000-pu-b0-jf-b0-46.ucode`, the last one Intel published), driver `iwlwifi`/`iwlmvm`, kernel `7.0.0-38-generic`, Ubuntu 26.04.1 LTS, NetworkManager, Secure Boot on.

**Symptoms:** the link goes "zombie" (associated, with an IP, but no traffic), other hosts see `ARP INCOMPLETE`, and the kernel sometimes logs:

```
iwlwifi 0000:00:14.3: Microcode SW error detected.  Restarting 0x2000000.
iwlwifi 0000:00:14.3: 0x20100705 | ADVANCED_SYSASSERT
```

**What we learned:**

- Most outages were **not** the card: the access point dropped every client at once (`DISASSOC_DUE_TO_INACTIVITY` on other hosts). Resetting the card for those makes things worse: a naive watchdog did 50 PCI resets in one day.
- The module options people usually suggest (`bt_coex_active=0`, `power_save=0`, `uapsd_disable`, `11n_disable=8`) **have no effect on iwlmvm in kernel 7.0**, according to its source code. Coexistence is always handled by the firmware. Only `iwlmvm power_scheme=1` and NetworkManager `wifi.powersave=2` act.
- With **Secure Boot** the kernel is in lockdown (`integrity`): writing to debugfs (`fw_restart`, `send_echo_cmd`, `trans/reset`) fails with `Operation not permitted`, even as root. A safe firmware liveness probe is reading `iwlmvm/nic_temp`.
- Ubuntu blacklists `iTCO_wdt`, and `systemd-modules-load` honors that blacklist, so `RuntimeWatchdogSec` silently does nothing until the module is loaded with an explicit `modprobe`.
- Every probe must go out through the Wi-Fi interface (`ping -I wlp0s20f3`). If you skip `-I` while another route exists, such as a USB-tethered phone, the watchdog thinks the network is fine.

**Solution:** a Python 3.12+ systemd service (standard library only) that diagnoses by layer (`sano`, `sin_interfaz`, `firmware`, `zombi`, `desasociado`, `ap_ausente`, `proveedor`) and escalates from soft to hard remedies, with at most 4 hardware actions per hour. It keeps Bluetooth on with automatic rollback, logs every event with its scenario and evidence, and can fall back to the phone's internet over Bluetooth PAN.

## El escenario

| Componente | Valor |
|---|---|
| Equipo | Dell Latitude 3400, BIOS 1.38.0 |
| Wifi | Intel Wireless-AC 9560 CNVi `[8086:9df0]` rev 30, PCI `0000:00:14.3`, interfaz `wlp0s20f3` |
| Bluetooth | Intel `8087:0aaa` Jefferson Peak, por USB, en el mismo radio que la wifi |
| Firmware | `46.7e3e4b69.0` (`9000-pu-b0-jf-b0-46.ucode`), el último publicado; el driver no acepta una API mayor a la 46 |
| Sistema | Ubuntu 26.04.1 LTS, kernel `7.0.0-38-generic`, NetworkManager, BlueZ, Secure Boot activo |
| Uso | Servidor 24/7 por wifi (nodo de k3s y servidor NFS) en banda de 5 GHz |

## El error

**Cómo se ve.** El equipo sigue encendido y muestra la wifi conectada con su IP, pero no cursa tráfico. Desde los demás equipos el ARP queda `INCOMPLETE`, la VPN lo marca fuera de línea y el clúster lo pone en `NotReady`. Una vez quedó así casi dos días, hasta que alguien lo reconectó a mano.

**Lo que dice el kernel** cuando falla el firmware (líneas reales; con el Bluetooth apagado hubo 11 líneas así en 6 días distintos del 4 al 23 de octubre de 2026):

```
iwlwifi 0000:00:14.3: Microcode SW error detected.  Restarting 0x2000000.
iwlwifi 0000:00:14.3: 0x20100705 | ADVANCED_SYSASSERT
```

El driver informa que reinició el firmware, pero el enlace puede quedar zombi igual.

**Lo que confundía el diagnóstico.** No todas las caídas son de la tarjeta:

- **El router.** El 26 de octubre otro equipo de la casa perdió la wifi a la vez que el Dell. Fueron cuatro veces en 6 minutos, con `wlo1: disassociated from ... (Reason: 4=DISASSOC_DUE_TO_INACTIVITY)`.
- **El proveedor de internet.** A veces la red local responde y lo que falta es internet.
- **Un guardián ingenuo.** Uno que trate toda falta de red igual empeora la situación: el 12 de octubre de 2026 el guardián anterior reinició la tarjeta por PCI 50 veces sin resultado, porque la falla no era de ella.

## Lo que se descubrió

1. **Diagnosticar por capas antes de actuar.** Interfaz del kernel, vida del firmware, asociación, punto de acceso visible, puerta de enlace e internet. Cada causa tiene su remedio, y la del router o la del proveedor no tocan el hardware.
2. **El Bluetooth no se apaga con parámetros.** Según el código de iwlmvm en el kernel 7.0 (`mvm/mac80211.c` e `iwl-modparams.h`), `bt_coex_active`, `power_save`, `uapsd_disable` y `11n_disable=8` no tienen efecto en esta tarjeta. La coexistencia la decide siempre el firmware. En julio de 2026 se apagó el Bluetooth por completo (lista negra de sus módulos y `rfkill`) y los errores del firmware bajaron de 121 en 62 horas a unos 2 en 48 horas. Aun así siguieron apareciendo en octubre. Desde el 25 de octubre el Bluetooth está encendido otra vez, con reversa automática: si en 24 horas hay más de un crash del firmware, el supervisor lo apaga solo. Hasta el 26 de octubre no hubo ninguno, pero son pocos días para concluir.
3. **Secure Boot bloquea debugfs.** Con el kernel en lockdown `integrity`, ni root puede escribir en `fw_restart`, `send_echo_cmd` ni `trans/reset`. Como prueba de vida del firmware sirve leer `iwlmvm/nic_temp`: le pide la temperatura al firmware y responde en unos 16 ms.
4. **El watchdog de hardware estaba apagado sin avisar.** Ubuntu tiene `iTCO_wdt` en su lista negra y `systemd-modules-load` la respeta, así que `RuntimeWatchdogSec=60s` no hacía nada. Lo carga un servicio propio con `modprobe` explícito.
5. **Toda prueba sale por la wifi.** Con el celular conectado por cable USB, un `ping` sin `-I` salía por el cable y daba la red por buena con la wifi caída.
6. **El enlace Bluetooth también se llama `enx<mac>`.** udev le pone a la interfaz BNEP un nombre como el de un adaptador USB. Para saber si hay anclaje por cable hay que mirar el driver (`rndis_host`, `cdc_ether`, `cdc_ncm`, `ipheth`), no el nombre.
7. **Después de una falla del proveedor, la tarjeta no es la culpable.** Si el router acaba de fallar, perder la puerta o la asociación es asunto suyo: durante 10 minutos solo se reasocia, sin recargar el módulo.

## La solución

Un servicio de systemd en Python 3.12+, solo con la biblioteca estándar, que corre en espacio de usuario: si el supervisor falla, systemd lo reinicia y el kernel no se entera. Lo que toca el hardware (`/sys`, debugfs, `modprobe`) va en procesos hijos con tiempo límite. Las razones de no compilar un driver propio ni tocar el firmware (que va firmado) están en `docs/adr/0001-supervisor-en-espacio-de-usuario.md`.

| Causa diagnosticada | Remedio, del más suave al más fuerte |
|---|---|
| `desasociado` | reasociar, reiniciar firmware, recargar módulo |
| `zombi` | reasociar, reiniciar firmware, recargar módulo, reset PCI |
| `firmware` | reiniciar firmware, recargar módulo, reset PCI |
| `sin_interfaz` | reset PCI, recargar módulo |
| `ap_ausente` | solo reasociar, cada 60 s: el router no está |
| `proveedor` | nada sobre el hardware: la red local responde |

Cada paso respalda al anterior. Los que tocan el hardware gastan un cupo de 4 por hora, guardado en disco antes de actuar. Así no hay tormentas de reinicios, ni siquiera si el servicio se reinicia.

**Protecciones contra congelamiento:**

- watchdog de systemd de 300 s, con latido en cada vuelta y en cada paso;
- `MemoryMax=150M`, `CPUQuota=30%`, `TasksMax=64` y solo 8 capacidades;
- cada vuelta en try/except, con un respaldo mínimo (reasociar);
- cerrojo `flock` compartido con el guardián de reserva;
- en el kernel, `softlockup_panic`, `hardlockup_panic` y `hung_task_panic` con `kernel.panic=10`, más `iTCO_wdt` vigilado por systemd: un equipo trabado se reinicia solo en vez de quedar colgado.

**Registro para encontrar la causa.** Cada falla queda en `/var/lib/controlador-radio/eventos.jsonl`, una línea JSON por evento, con:

- causa y medida de cada capa;
- escenario: carga, memoria, presión de disco, BSSID, frecuencia, dispositivos Bluetooth y cable USB;
- remedio y segundos que tardó.

Además deja una carpeta de evidencia por episodio con los registros de los 15 minutos alrededor de la falla. Si el firmware falló, copia también su volcado (`devcoredump`), que el kernel borra a los 5 minutos.

**Internet de respaldo por el celular** (opcional, `docs/adr/0002-respaldo-de-internet-por-el-celular.md`):

- **la red local responde y no hay internet:** sube solo el Bluetooth del celular (PAN) y deja la wifi en la casa, para no sacar al servidor de la red local;
- **el router desaparece:** sube el Bluetooth de inmediato y, a los 3 minutos, la wifi que comparte el celular; desde ahí vuelve a la casa en cuanto la ve;
- **la wifi vuelve a tener internet 5 minutos seguidos:** suelta el Bluetooth.

**Resultados medidos en el equipo real:**

| Prueba | Tiempo hasta recuperar |
|---|---|
| Desasociado | 33 s |
| Enlace zombi | 29 s |
| Recarga del módulo | 10,3 s |
| Reset PCI | 10,5 s |
| Internet de la wifi cortado (red local intacta) | Bluetooth arriba a los 64 s, internet por el celular a los 95 s |

## Instalar y adaptar

Requisitos: Linux con NetworkManager, Python 3.12 o superior, `iw` y, para el Bluetooth, BlueZ. Todo como root.

1. Ajusta `despliegue/config.toml`. Los valores que cambian de un equipo a otro:

   | Clave | Qué es |
   |---|---|
   | `iface` | Interfaz wifi |
   | `pci` | Dirección PCI de la tarjeta |
   | `conexion` | Perfil de NetworkManager de tu wifi; su nombre debe ser igual al SSID |
   | `puerta` | Puerta de enlace |
   | `internet` | Direcciones para probar internet |
   | `celular` | Perfil de la wifi que comparte el celular |
   | `bt_celular` | Perfil del internet por Bluetooth |

   Lo demás tiene valores probados y límites sanos: un valor fuera de rango se ignora.
2. Estrénalo en modo observar, que diagnostica y registra sin tocar nada:

   ```
   sudo bash despliegue/instalar.sh observar
   ```

   Antes de tocar nada hace un respaldo en `/root/respaldo-radio-<fecha>.tgz` y una prueba de humo.
3. Cuando el diagnóstico te convenza, instala en modo de actuar: `sudo bash despliegue/instalar.sh actuar`.
4. Para deshacer: `sudo controlador-radio-restaurar [respaldo]`.

Uso diario:

```
sudo controlador-radio diagnostico          # mide y dice la causa, sin tocar nada
sudo controlador-radio estado               # contadores, última medida y Bluetooth
sudo controlador-radio eventos 20           # los últimos 20 eventos
sudo controlador-radio evidencia            # captura manual de todos los registros
sudo controlador-radio reparar              # una vuelta completa
sudo controlador-radio probar reasociar     # o reiniciar-firmware, recargar-modulo, reset-pci
sudo controlador-radio bt activar|desactivar|estado
journalctl -u controlador-radio -f
```

**Internet por el Bluetooth del celular.** El emparejamiento se hace una vez:

1. Pon el equipo visible con un agente que acepte la confirmación, por ejemplo `bluetoothctl` con `agent KeyboardDisplay`, `default-agent` y `discoverable on`, respondiendo `yes` al código.
2. **Inicia el emparejamiento desde el celular.** Si lo pide el equipo, el celular suele aceptar tarde y BlueZ responde `AuthenticationFailed`.
3. Activa en el celular "Compartir internet por Bluetooth" y crea el perfil:

```
nmcli con add type bluetooth con-name bt-celular ifname "*" bt-type panu \
  bluetooth.bdaddr <MAC-del-celular> connection.autoconnect no \
  ipv4.route-metric 1000 ipv6.route-metric 1000
```

Activa además la verificación de conectividad de NetworkManager (`[connectivity]` con `uri` e `interval=60`). Así la wifi sin internet recibe +20000 en su métrica y gana la ruta del Bluetooth. Si el equipo tiene sesión gráfica, desactiva el audio Bluetooth de WirePlumber (`monitor.bluez = disabled`), para que el celular no le mande sonido ni llamadas.

**Avisos.** Si existe `/usr/local/lib/guardian-aviso.sh`, el supervisor le pasa los avisos, por ejemplo para enviarlos a Telegram con silencio nocturno. Si no existe, solo los deja en el registro. `despliegue/dell-net-guardian.sh` es el guardián anterior, en bash. Queda de reserva y solo actúa si el supervisor no está activo.

## Limitaciones

- No arregla el firmware: Intel no publica uno más nuevo para esta tarjeta, y modificarlo no sirve porque va firmado.
- Si la tarjeta muere del todo, no hay redundancia de hardware. El respaldo por el celular cubre internet, no la red local.
- Con el router ausente y el servidor en la wifi del celular, los servicios pueden gastar datos móviles.
- La relación entre el Bluetooth y los crashes del firmware sigue siendo una hipótesis: el supervisor la vigila, pero no la demuestra.

## Desarrollo

```
VENV=/ruta/al/venv/bin bash scripts/calidad.sh   # ruff format, ruff check, mypy --strict y pytest
```

Las pruebas usan un sistema falso (`tests/falso.py`), así que nunca tocan el hardware. Las decisiones de diseño están en `docs/adr/`.

## Control de cambios

| Versión | Fecha | Cambio |
|---|---|---|
| 1.3.0 | 2026-10-26 | Respaldo de internet por el celular: Bluetooth (PAN) y wifi del celular según la causa, con vuelta a la casa. |
| 1.2.1 | 2026-10-26 | Tras una falla del proveedor solo reasocia durante `espera_router`, sin tocar el hardware; el cable USB se reconoce por su driver. |
| 1.2.0 | 2026-10-25 | Registro de eventos de wifi y Bluetooth con causa, escenario y evidencia completa por episodio. |
| 1.1.0 | 2026-10-25 | Correcciones de una revisión independiente: sin reinicios con la red sana, tope persistente, reset PCI que siempre vuelve a buscar la tarjeta, latido en cada espera y mínimo privilegio. |
| 1.0.0 | 2026-10-25 | Primera versión: diagnóstico por capas, remedios con respaldo, tope de hardware, escucha del kernel, Bluetooth con reversa y protecciones contra congelamiento. |

## Licencia

MIT. Ver `LICENSE`.
