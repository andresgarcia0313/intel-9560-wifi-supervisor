"""Sondas: miden cada capa por separado y siempre por la interfaz wifi (nunca por el cable USB).

Cada sonda devuelve un valor simple y no lanza excepciones; si su metodo preferido falla, prueba otro.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .config import Config
from .sistema import Sistema


@dataclass(frozen=True)
class Medida:
    interfaz: bool  # existe la interfaz del kernel
    firmware: bool  # el firmware responde (lectura de temperatura o eco)
    asociado: bool  # hay enlace con un punto de acceso
    ap_visible: bool  # el SSID aparece en el ultimo escaneo
    puerta: bool  # la puerta de enlace responde por la wifi
    internet: bool  # internet responde por la wifi
    senal: int | None = None  # dBm
    tasa_tx: float | None = None  # Mbit/s
    temperatura: int | None = None  # grados C de la tarjeta, medidos por el firmware


def ping(s: Sistema, cfg: Config, destino: str) -> bool:
    return s.correr(["ping", "-c1", "-W2", "-I", cfg.iface, destino], tope=5).ok


def temperatura(s: Sistema, cfg: Config) -> int | None:
    """Pide la temperatura al firmware (debugfs nic_temp): solo responde si el firmware esta vivo."""
    crudo = s.leer(f"{cfg.debugfs}/nic_temp")
    try:
        return int(crudo.strip()) if crudo is not None else None
    except ValueError:
        return None


def debugfs_escribible(s: Sistema) -> bool:
    """Con Secure Boot el kernel entra en lockdown y prohibe escribir en debugfs, incluso a root."""
    modo = s.leer("/sys/kernel/security/lockdown")
    return modo is None or "[none]" in modo


def firmware_vivo(s: Sistema, cfg: Config) -> bool:
    """Lectura de temperatura (permitida con lockdown); respaldo: eco por debugfs; sin debugfs, iw."""
    if s.leer(f"{cfg.debugfs}/fw_ver") is None:
        return s.correr(["iw", "dev", cfg.iface, "info"], tope=5).ok
    return temperatura(s, cfg) is not None or s.escribir(f"{cfg.debugfs}/send_echo_cmd", "1")


def enlace(s: Sistema, cfg: Config) -> tuple[bool, int | None, float | None]:
    r = s.correr(["iw", "dev", cfg.iface, "link"], tope=5)
    if not r.ok or "Connected to" not in r.salida:
        return False, None, None
    senal = re.search(r"signal:\s*(-?\d+)", r.salida)
    tasa = re.search(r"tx bitrate:\s*([\d.]+)", r.salida)
    return True, int(senal.group(1)) if senal else None, float(tasa.group(1)) if tasa else None


def ap_visible(s: Sistema, cfg: Config) -> bool:
    """Busca el SSID de la conexion en los resultados de escaneo que ya tiene NetworkManager."""
    ssid = s.correr(["nmcli", "-g", "802-11-wireless.ssid", "connection", "show", cfg.conexion])
    nombre = ssid.salida.strip() if ssid.ok else cfg.conexion
    lista = s.correr(["nmcli", "-t", "-f", "SSID", "device", "wifi", "list", "ifname", cfg.iface])
    if lista.ok and nombre in lista.salida.splitlines():
        return True
    escaneo = s.correr(["iw", "dev", cfg.iface, "scan", "dump"], tope=10)
    return escaneo.ok and f"SSID: {nombre}" in escaneo.salida


def medir(s: Sistema, cfg: Config) -> Medida:
    if s.leer(f"/sys/class/net/{cfg.iface}/operstate") is None:
        return Medida(False, False, False, False, False, False)
    asociado, senal, tasa = enlace(s, cfg)
    temp = temperatura(s, cfg)
    puerta = ping(s, cfg, cfg.puerta) if asociado else False
    internet = asociado and any(ping(s, cfg, d) for d in cfg.internet)  # cada destino respalda al anterior
    return Medida(
        interfaz=True,
        firmware=temp is not None or firmware_vivo(s, cfg),
        temperatura=temp,
        asociado=asociado,
        ap_visible=True if asociado else ap_visible(s, cfg),
        puerta=puerta,
        internet=internet,
        senal=senal,
        tasa_tx=tasa,
    )
