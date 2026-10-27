"""Bitacora de eventos de la wifi y del Bluetooth: un JSON por linea en <estado_dir>/eventos.jsonl.

Cada evento dice que paso (falla, crash, remedio, recuperacion), a que equipo (wifi o bt), por que
(la causa diagnosticada) y en que escenario (carga, memoria, temperatura, senal, canal, Bluetooth,
cable USB). Si hubo falla, apunta a la carpeta de evidencia con los registros completos.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from pathlib import Path
from typing import Any

from .config import Config
from .sistema import Sistema

log = logging.getLogger(__name__)
TOPE_BYTES = 5 * 1024 * 1024  # al pasarlo, eventos.jsonl rota a eventos.jsonl.1


class Bitacora:
    def __init__(self, directorio: str) -> None:
        self.ruta = Path(directorio) / "eventos.jsonl"
        self.cerrojo = threading.Lock()  # la escucha del kernel corre en otro hilo

    def anotar(self, equipo: str, tipo: str, **datos: Any) -> dict[str, Any]:
        evento = {"hora": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "equipo": equipo, "tipo": tipo, **datos}
        log.info("evento %s/%s: %s", equipo, tipo, datos.get("causa") or datos.get("detalle") or "")
        try:
            with self.cerrojo:
                self.ruta.parent.mkdir(parents=True, exist_ok=True)
                if self.ruta.exists() and self.ruta.stat().st_size > TOPE_BYTES:
                    os.replace(self.ruta, self.ruta.with_suffix(".jsonl.1"))
                with self.ruta.open("a") as f:
                    f.write(json.dumps(evento, ensure_ascii=False, default=str) + "\n")
        except OSError as exc:  # sin bitacora el controlador sigue: queda en el journal
            log.warning("no se pudo anotar el evento (%s): %s", exc, evento)
        return evento

    def ultimos(self, n: int = 20) -> list[dict[str, Any]]:
        try:
            lineas = self.ruta.read_text().splitlines()[-n:]
        except OSError:
            return []
        eventos = []
        for linea in lineas:
            try:
                eventos.append(json.loads(linea))
            except ValueError:
                continue  # una linea a medias (corte de luz) no impide leer las demas
        return eventos


def _leer(ruta: str) -> str:
    try:
        return Path(ruta).read_text().strip()
    except OSError:
        return ""


ANCLAJE = frozenset({"rndis_host", "cdc_ether", "cdc_ncm", "ipheth"})


def anclaje_usb(red: str = "/sys/class/net") -> bool:
    """Cable del celular por su driver: el enlace Bluetooth tambien se llama enx<mac> (udev)."""
    try:
        return any(
            os.path.basename(os.path.realpath(f"{red}/{n}/device/driver")) in ANCLAJE for n in os.listdir(red)
        )
    except OSError:
        return False


def escenario(s: Sistema, cfg: Config) -> dict[str, Any]:
    """Foto rapida de lo que pasaba alrededor de la falla (cada dato es opcional)."""
    datos: dict[str, Any] = {"carga": _leer("/proc/loadavg")}
    memoria = re.search(r"MemAvailable:\s+(\d+)", _leer("/proc/meminfo"))
    datos["memoria_libre_mb"] = int(memoria.group(1)) // 1024 if memoria else None
    io = re.search(r"some avg10=([\d.]+)", _leer("/proc/pressure/io"))
    datos["presion_io_10s"] = float(io.group(1)) if io else None
    datos["encendido_s"] = (
        int(float(_leer("/proc/uptime").split()[0] or 0)) if _leer("/proc/uptime") else None
    )
    enlace = s.correr(["iw", "dev", cfg.iface, "link"], tope=5).salida
    for clave, patron in (("bssid", r"Connected to (\S+)"), ("frecuencia_mhz", r"freq:\s*([\d.]+)")):
        hallado = re.search(patron, enlace)
        datos[clave] = hallado.group(1) if hallado else None
    datos["bluetooth_conectados"] = len(
        s.correr(["bluetoothctl", "devices", "Connected"], tope=5).salida.splitlines()
    )
    datos["cable_usb"] = anclaje_usb()
    return datos
