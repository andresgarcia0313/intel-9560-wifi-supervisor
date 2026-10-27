"""Sistema falso para las pruebas: responde segun reglas y registra cada orden y escritura."""

from __future__ import annotations

from collections.abc import Callable

from radio_dell.config import Config
from radio_dell.sistema import Resultado

LINK_OK = "Connected to 02:00:00:00:00:01 (on wlp0s20f3)\n\tsignal: -56 dBm\n\ttx bitrate: 866.7 MBit/s VHT"


class SistemaFalso:
    def __init__(self) -> None:
        self.ordenes: list[list[str]] = []
        self.escrituras: list[tuple[str, str]] = []
        self.archivos: dict[str, str] = {
            "/sys/class/net/wlp0s20f3/operstate": "up",
            f"{Config().debugfs}/fw_ver": "46",
            f"/sys/bus/pci/devices/{Config().pci}/vendor": "0x8086",
        }
        self.asociado = True
        self.puerta = True
        self.internet = True
        self.firmware = True
        self.ssid_visible = True
        self.otras_redes: list[str] = []  # SSID visibles ademas de la casa
        self.activa = "wifi-casa"  # perfil wifi activo
        self.bt = False  # perfil bt-celular activo
        self.no_suben: set[str] = set()  # perfiles cuyo 'connection up' falla
        self.al_escribir: dict[str, Callable[[], bool]] = {}  # ruta -> efecto (devuelve exito)
        self.al_correr: dict[str, Callable[[list[str]], Resultado]] = {}  # primera palabra -> efecto

    def correr(self, orden: list[str], tope: float = 20) -> Resultado:
        self.ordenes.append(orden)
        if orden[0] in self.al_correr:
            return self.al_correr[orden[0]](orden)
        if orden[0] == "ping":
            ok = self.puerta if orden[-1] == Config().puerta else self.internet
            return Resultado(0 if ok and self.asociado else 1)
        if orden[:3] == ["iw", "dev", "wlp0s20f3"] and orden[3] == "link":
            return Resultado(0, LINK_OK if self.asociado else "Not connected.")
        if orden[:2] == ["nmcli", "-t"]:
            casa = "wifi-casa\n" if self.ssid_visible else "otra\n"
            return Resultado(0, casa + "".join(f"{r}\n" for r in self.otras_redes))
        if orden[:3] == ["nmcli", "connection", "up"] or orden[:3] == ["nmcli", "connection", "down"]:
            return self._perfil(orden[2] == "up", orden[3])
        if orden[:3] == ["nmcli", "-g", "GENERAL.CONNECTION"]:
            return Resultado(0, f"{self.activa}\n")
        if orden[:3] == ["nmcli", "-g", "GENERAL.STATE"]:
            return Resultado(0, "activated\n" if self.bt else "")
        if orden[:3] == ["nmcli", "-g", "bluetooth.bdaddr"]:
            return Resultado(0, "00\\:11\\:22\\:33\\:44\\:55\n")
        if orden[:2] == ["nmcli", "-g"]:
            return Resultado(0, "wifi-casa\n")
        return Resultado(0)

    def _perfil(self, subir: bool, nombre: str) -> Resultado:
        if nombre in self.no_suben:
            return Resultado(4)
        if nombre == "bt-celular":
            self.bt = subir
        elif subir:
            self.activa = nombre
        return Resultado(0)

    def escribir(self, ruta: str, texto: str) -> bool:
        self.escrituras.append((ruta, texto))
        if ruta.endswith("send_echo_cmd"):
            return self.firmware
        efecto = self.al_escribir.get(ruta)
        return efecto() if efecto else True

    def leer(self, ruta: str) -> str | None:
        if ruta.endswith("/nic_temp"):  # el firmware solo responde la temperatura si esta vivo
            return "57\n" if self.firmware else None
        return self.archivos.get(ruta)

    def dormir(self, segundos: float) -> None:
        return None

    def ordeno(self, *palabras: str) -> bool:
        return any(o[: len(palabras)] == list(palabras) for o in self.ordenes)
