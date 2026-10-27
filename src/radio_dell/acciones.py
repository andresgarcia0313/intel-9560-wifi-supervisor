"""Remedios, de menor a mayor fuerza. Cada uno devuelve True solo si al final la wifi volvio a cursar trafico.

Cada remedio tiene un metodo alterno por si el preferido falla (patron de intentos.con_respaldo).
"""

from __future__ import annotations

from .config import Config
from .intentos import con_respaldo
from .red import esperar, interfaz_presente, levantar, pausa, red_ok
from .sistema import Sistema
from .sondas import firmware_vivo


def reasociar(s: Sistema, cfg: Config) -> bool:
    s.correr(["nmcli", "device", "disconnect", cfg.iface], tope=20)
    s.dormir(1)
    return levantar(s, cfg)


def reiniciar_firmware(s: Sistema, cfg: Config) -> bool:
    """Reinicia el firmware dentro del mismo driver (~3 s): por iwlmvm y, si falla, por el transporte."""
    trans = cfg.debugfs.rsplit("/", 1)[0] + "/trans/reset"

    def tras(ruta: str, valor: str) -> bool:
        return (
            s.escribir(ruta, valor)
            and esperar(s, lambda: firmware_vivo(s, cfg), 15)
            and (esperar(s, lambda: red_ok(s, cfg), 12) or levantar(s, cfg))
        )

    pasos = [
        ("iwlmvm fw_restart", lambda: tras(f"{cfg.debugfs}/fw_restart", "nolog\n")),
        ("trans reset sw", lambda: tras(trans, "sw")),
    ]
    return con_respaldo("reiniciar firmware", pasos).ok


def presente(s: Sistema, cfg: Config) -> bool:
    """El dispositivo PCI de la tarjeta sigue en el bus."""
    return s.leer(f"/sys/bus/pci/devices/{cfg.pci}/vendor") is not None


def recargar_modulo(s: Sistema, cfg: Config) -> bool:
    if not presente(s, cfg):  # sin dispositivo no hay que recargar: buscarlo en el bus
        s.escribir("/sys/bus/pci/rescan", "1")
    s.correr(["modprobe", "-r", "iwlmvm", "iwlwifi"], tope=30)
    s.dormir(2)
    if not s.correr(["modprobe", "iwlwifi"], tope=30).ok or not interfaz_presente(s, cfg):
        return False
    return levantar(s, cfg)


def reset_pci(s: Sistema, cfg: Config) -> bool:
    """Quita el dispositivo del bus y lo vuelve a buscar; si el bus no responde, desliga y liga el driver."""
    driver = "/sys/bus/pci/drivers/iwlwifi"

    def por_bus() -> bool:
        # si un intento anterior lo quito y el rescan fallo, el dispositivo ya no esta: solo buscarlo
        if presente(s, cfg) and not s.escribir(f"/sys/bus/pci/devices/{cfg.pci}/remove", "1"):
            return False
        return pausa(s, 3) and s.escribir("/sys/bus/pci/rescan", "1")

    def por_driver() -> bool:
        s.escribir(f"{driver}/unbind", cfg.pci)
        return pausa(s, 2) and s.escribir(f"{driver}/bind", cfg.pci)

    ok = con_respaldo("reset pci", [("remove+rescan", por_bus), ("unbind+bind", por_driver)]).ok
    return ok and interfaz_presente(s, cfg) and levantar(s, cfg)
