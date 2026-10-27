"""Vigilancia del Bluetooth dentro del demonio: lo apaga si estorba a la wifi y lo vuelve a encender
si debia estar encendido y no lo esta. Cada falla queda en la bitacora con su evidencia."""

from __future__ import annotations

import logging
import time

from . import bluetooth, bt_estado, cerrojo, servicio
from .config import Config
from .episodios import Episodios
from .registro import Registro
from .sistema import Sistema

log = logging.getLogger(__name__)
CADA_BT = 600  # segundos entre revisiones de que el Bluetooth siga encendido si debe estarlo


class VigiaBt:
    def __init__(self, s: Sistema, cfg: Config, registro: Registro, episodios: Episodios) -> None:
        self.s, self.cfg, self.registro, self.episodios = s, cfg, registro, episodios
        self.ultimo = -1e9

    def vigilar(self) -> None:
        if self.cfg.modo == "observar":
            return
        if bt_estado.debe_apagarse(self.cfg, self.registro.crashes_desde):
            log.error("el Bluetooth coincide con crashes del firmware: lo apago")
            self.episodios.bt("apagado_por_crashes", "crashes del firmware wifi con el BT encendido", True)
            with cerrojo.exclusivo(esperar=True):
                bluetooth.desactivar(self.s, self.cfg)
            servicio.avisar("critical", "apague el Bluetooth: con el encendido el firmware fallo")
            return
        if time.monotonic() - self.ultimo < CADA_BT:
            return
        self.ultimo = time.monotonic()
        if bt_estado.leer(self.cfg).get("activo") and not bluetooth.controlador_listo(self.s):
            log.warning("el Bluetooth debia estar encendido y no lo esta: lo enciendo")
            self.episodios.bt("falla", "debia estar encendido y el controlador no responde", True)
            ok = bluetooth.encender_radio(self.s)
            self.episodios.bt("remedio", "encendido de nuevo" if ok else "no se pudo encender")
            if not ok:
                servicio.avisar("critical", "el Bluetooth no enciende: ver la bitacora de eventos")
