"""Bluetooth interno (Intel 8087:0aaa): encenderlo y apagarlo solo si estorba a la wifi.

Estuvo bloqueado desde jul-2026 creyendo que bt_coex_active=0 evitaba crashes, pero iwlmvm ignora ese
parametro: la coexistencia la hace siempre el firmware (mvm/mac80211.c, kernel 7.0). Encenderlo no
toca la wifi. Protecciones: reversa de systemd a los 10 min si la activacion no se confirma, y el
demonio lo apaga si en las primeras horas hay mas crashes de los tolerados (bt_estado.debe_apagarse).
"""

from __future__ import annotations

import logging
from pathlib import Path

from .bt_estado import archivo, guardar
from .config import Config
from .intentos import con_respaldo
from .red import pausa, red_ok
from .sistema import Sistema

log = logging.getLogger(__name__)
LISTA_NEGRA = "/etc/modprobe.d/blacklist-bluetooth.conf"
REVERSA = "controlador-radio-bt-reversa"
PROGRAMA = "/usr/local/bin/controlador-radio"


def controlador_listo(s: Sistema) -> bool:
    r = s.correr(["bluetoothctl", "show"], tope=10)
    return r.ok and "Powered: yes" in r.salida


def encender_radio(s: Sistema) -> bool:
    s.correr(["rfkill", "unblock", "bluetooth"])
    s.correr(["systemctl", "enable", "--now", "bluetooth.service"], tope=30)

    def poder(orden: list[str]) -> bool:
        return s.correr(orden, tope=15).ok and pausa(s, 1) and controlador_listo(s)

    def recargar() -> bool:
        s.correr(["modprobe", "-r", "btusb"])
        return s.correr(["modprobe", "btusb"]).ok and pausa(s, 4) and poder(["bluetoothctl", "power", "on"])

    pasos = [
        ("bluetoothctl power on", lambda: poder(["bluetoothctl", "power", "on"])),
        ("btmgmt power on", lambda: poder(["btmgmt", "power", "on"])),
        ("recargar btusb", recargar),
    ]
    return con_respaldo("encender bluetooth", pasos).ok


def activar(s: Sistema, cfg: Config) -> bool:
    reversa = ["systemd-run", "--quiet", "--collect", f"--unit={REVERSA}", "--on-active=600"]
    s.correr([*reversa, PROGRAMA, "bt", "desactivar"])  # si algo cuelga a mitad, se deshace solo
    negra = Path(LISTA_NEGRA)
    if negra.exists() and not archivo(
        "guardar lista negra", lambda: negra.rename(f"{LISTA_NEGRA}.desactivado")
    ):
        desactivar(s, cfg)
        return False
    s.correr(["modprobe", "btusb"])
    if not (pausa(s, 3) and encender_radio(s) and pausa(s, 20) and red_ok(s, cfg)):
        log.error("el Bluetooth no encendio o la wifi se resintio: revierto")
        desactivar(s, cfg)
        return False
    guardar(cfg, True)
    s.correr(["systemctl", "stop", f"{REVERSA}.timer"])  # confirmado: se cancela la reversa
    return True


def desactivar(s: Sistema, cfg: Config) -> bool:
    s.correr(["systemctl", "stop", f"{REVERSA}.timer"])
    guardada = Path(f"{LISTA_NEGRA}.desactivado")
    if guardada.exists():
        archivo("reponer lista negra", lambda: guardada.rename(LISTA_NEGRA))
    s.correr(["systemctl", "disable", "--now", "bluetooth.service"], tope=30)
    s.correr(["rfkill", "block", "bluetooth"])
    s.correr(["modprobe", "-r", "btusb", "btintel", "btrtl", "btbcm"])
    return guardar(cfg, False)
