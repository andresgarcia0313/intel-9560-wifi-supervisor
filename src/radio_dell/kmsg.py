"""Escucha en vivo del kernel: detecta crashes del firmware al instante, sin esperar la revision periodica.

Lee /dev/kmsg en un hilo; si no puede, sigue con `journalctl -kf`. Los crashes que provoca el propio
controlador (fw_restart fuerza un assert) se ignoran durante la ventana de silencio.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import threading
import time
from collections.abc import Callable, Iterator

log = logging.getLogger(__name__)
CRASH = re.compile(
    r"iwlwifi.*(Microcode SW error|ADVANCED_SYSASSERT|NMI_INTERRUPT|Hardware error detected"
    r"|Queue \d+ is stuck|Failed to wake NIC|HW_ERROR)",
    re.I,
)
# Errores del Bluetooth interno (Intel por USB): fallas de comando, reinicios de hardware, firmware
BT = re.compile(
    r"Bluetooth: hci\d+: .*(Hardware error|tx timeout|Failed|failed|Reset|unexpected|error)"
    r"|btusb.*(error|fail)|btintel.*(error|fail)",
)


def _por_kmsg() -> Iterator[str]:
    fd = os.open("/dev/kmsg", os.O_RDONLY)
    try:
        os.lseek(fd, 0, os.SEEK_END)  # solo lo nuevo
        while True:
            try:
                yield os.read(fd, 8192).decode(errors="replace")
            except BrokenPipeError:  # el anillo se sobrescribio: se sigue leyendo
                continue
    finally:
        os.close(fd)


def _por_journal() -> Iterator[str]:
    p = subprocess.Popen(["journalctl", "-kf", "-n0", "-o", "cat"], stdout=subprocess.PIPE, text=True)
    assert p.stdout is not None
    yield from p.stdout


class Escucha:
    def __init__(
        self, al_evento: Callable[[str, str], None], reloj: Callable[[], float] = time.monotonic
    ) -> None:
        """al_evento(equipo, linea) con equipo "wifi" (crash del firmware) o "bt" (error del Bluetooth)."""
        self.al_evento, self.reloj = al_evento, reloj
        self.silencio_hasta = 0.0
        self.hilo = threading.Thread(target=self._correr, name="kmsg", daemon=True)

    def silenciar(self, segundos: float) -> None:
        self.silencio_hasta = max(self.silencio_hasta, self.reloj() + segundos)

    def procesar(self, linea: str) -> bool:
        """True si la linea es un error real y se notifico. El silencio solo aplica a la wifi: tapa los
        mensajes que provocan los propios remedios."""
        texto = linea.strip()[-300:]
        if BT.search(linea):
            self.al_evento("bt", texto)
            return True
        if not CRASH.search(linea) or self.reloj() < self.silencio_hasta:
            return False
        self.al_evento("wifi", texto)
        return True

    def _correr(self) -> None:
        for fuente in (_por_kmsg, _por_journal):  # la segunda respalda a la primera
            try:
                for bloque in fuente():
                    for linea in bloque.splitlines():
                        self.procesar(linea)
            except Exception:
                log.exception("escucha del kernel por %s fallo; paso a la siguiente fuente", fuente.__name__)
        log.error("sin escucha del kernel: quedan solo las revisiones periodicas")

    def iniciar(self) -> None:
        self.hilo.start()
