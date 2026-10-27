"""Configuracion: valores por defecto del Dell sobrescribibles en /etc/controlador-radio/config.toml."""

from __future__ import annotations

import logging
import tomllib
from dataclasses import dataclass, fields, replace
from pathlib import Path

log = logging.getLogger(__name__)
RUTA = "/etc/controlador-radio/config.toml"


@dataclass(frozen=True)
class Config:
    modo: str = "actuar"  # "observar": diagnostica y registra sin tocar nada (para estrenar cambios)
    iface: str = "wlp0s20f3"
    conexion: str = "wifi-casa"
    pci: str = "0000:00:14.3"
    puerta: str = "192.168.1.254"
    internet: tuple[str, ...] = ("1.1.1.1", "8.8.8.8", "9.9.9.9")
    intervalo: float = 15.0  # segundos entre revisiones normales
    confirmar: int = 2  # revisiones fallidas seguidas antes de actuar (salvo crash de firmware)
    max_resets_hora: int = 4  # tope de acciones sobre el hardware por hora (evita tormentas)
    espera_ap: float = 60.0  # con el punto de acceso ausente, cada cuanto reintentar asociar
    espera_router: float = 600.0  # tras una falla del proveedor, segundos en que solo se reasocia
    celular: str = "wifi-celular"  # perfil (y SSID) de la wifi que comparte el celular
    bt_celular: str = "bt-celular"  # perfil del internet por el Bluetooth del celular
    espera_celular: float = 180.0  # router ausente: segundos antes de pasar la wifi al celular
    volver_casa: float = 120.0  # en el celular: cada cuanto buscar la casa para volver
    soltar_bt: float = 300.0  # wifi con internet: segundos antes de soltar el Bluetooth
    estado_dir: str = "/var/lib/controlador-radio"
    debugfs: str = "/sys/kernel/debug/iwlwifi/0000:00:14.3/iwlmvm"
    bt_vigilancia_h: float = 24.0  # horas de prueba del Bluetooth antes de darlo por estable
    bt_max_crashes: int = 1  # crashes de firmware tolerados en esa ventana antes de apagarlo


# Limites sanos: fuera de ellos el valor se ignora (p. ej. un intervalo >= WatchdogSec mataria al demonio)
RANGOS: dict[str, tuple[float, float]] = {
    "intervalo": (5, 120),
    "confirmar": (1, 10),
    "max_resets_hora": (0, 20),
    "espera_ap": (10, 3600),
    "espera_router": (60, 3600),
    "espera_celular": (30, 3600),
    "volver_casa": (60, 3600),
    "soltar_bt": (30, 3600),
    "bt_vigilancia_h": (0, 720),
    "bt_max_crashes": (0, 100),
}
MODOS = ("actuar", "observar")


def _valido(clave: str, valor: object) -> bool:
    if clave == "modo":
        return valor in MODOS
    minimo, maximo = RANGOS.get(clave, (float("-inf"), float("inf")))
    return not isinstance(valor, int | float) or minimo <= valor <= maximo


def cargar(ruta: str = RUTA) -> Config:
    """Lee el TOML; si falta o esta mal, sigue con los valores por defecto (nunca detiene el demonio)."""
    base = Config()
    try:
        datos = tomllib.loads(Path(ruta).read_text())
    except FileNotFoundError:
        return base
    except (OSError, tomllib.TOMLDecodeError) as exc:
        log.error("config %s ilegible (%s): uso los valores por defecto", ruta, exc)
        return base
    validos = {f.name: f.type for f in fields(Config)}
    cambios: dict[str, object] = {}
    for clave, crudo in datos.items():
        valor = crudo
        if clave not in validos:
            log.warning("config: clave desconocida '%s' ignorada", clave)
            continue
        actual = getattr(base, clave)
        if isinstance(actual, tuple) and isinstance(valor, list):
            valor = tuple(str(v) for v in valor)
        elif isinstance(actual, float) and isinstance(valor, int):
            valor = float(valor)
        if type(valor) is not type(actual) or not _valido(clave, valor):
            log.warning("config: '%s' = %r fuera de tipo o de rango, ignorado", clave, valor)
            continue
        cambios[clave] = valor
    return replace(base, **cambios)  # type: ignore[arg-type]
