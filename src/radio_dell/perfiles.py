"""Perfiles de NetworkManager del respaldo de internet: consultar, subir y bajar, cada orden con tope."""

from __future__ import annotations

from .config import Config
from .sistema import Sistema


class Perfiles:
    def __init__(self, s: Sistema, cfg: Config) -> None:
        self.s, self.cfg = s, cfg

    def nm(self, *orden: str, tope: float = 20) -> str | None:
        r = self.s.correr(["nmcli", *orden], tope=tope)
        return r.salida.strip() if r.ok else None

    def en_celular(self) -> bool:
        return self.nm("-g", "GENERAL.CONNECTION", "device", "show", self.cfg.iface) == self.cfg.celular

    def bt_activo(self) -> bool:
        return self.nm("-g", "GENERAL.STATE", "connection", "show", self.cfg.bt_celular) == "activated"

    def mac_bt(self) -> str:
        """-g escapa los dos puntos de la direccion (CC\\:62...)."""
        return (self.nm("-g", "bluetooth.bdaddr", "connection", "show", self.cfg.bt_celular) or "").replace(
            "\\", ""
        )

    def visible(self, ssid: str) -> bool:
        orden = ("-t", "-f", "SSID", "device", "wifi", "list", "ifname", self.cfg.iface, "--rescan", "yes")
        return ssid in (self.nm(*orden, tope=30) or "").splitlines()

    def subir(self, perfil: str, tope: float = 60) -> bool:
        return self.nm("connection", "up", perfil, tope=tope) is not None

    def bajar(self, perfil: str) -> bool:
        return self.nm("connection", "down", perfil) is not None
