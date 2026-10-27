"""Estado del Bluetooth en <estado_dir>/bt.json y la regla que decide apagarlo si estorba a la wifi."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from pathlib import Path

from .config import Config

log = logging.getLogger(__name__)


def archivo(tarea: str, accion: Callable[[], object]) -> bool:
    """Operacion de archivo que nunca lanza: registra el error y devuelve False."""
    try:
        accion()
        return True
    except OSError as exc:
        log.error("%s: %s", tarea, exc)
        return False


def _ruta(cfg: Config) -> Path:
    return Path(cfg.estado_dir) / "bt.json"


def leer(cfg: Config) -> dict[str, float | bool]:
    try:
        return dict(json.loads(_ruta(cfg).read_text()))
    except (OSError, ValueError):
        return {"activo": False, "desde": 0.0}


def guardar(cfg: Config, activo: bool, ahora: float | None = None) -> bool:
    datos = json.dumps({"activo": activo, "desde": time.time() if ahora is None else ahora})

    def escribir() -> None:
        _ruta(cfg).parent.mkdir(parents=True, exist_ok=True)
        _ruta(cfg).write_text(datos)

    return archivo("guardar estado bt", escribir)


def debe_apagarse(cfg: Config, crashes_desde: Callable[[float], int], ahora: float | None = None) -> bool:
    """True si el Bluetooth esta en su periodo de prueba y ya hubo mas crashes de los tolerados."""
    bt = leer(cfg)
    desde = float(bt.get("desde", 0))
    t = time.time() if ahora is None else ahora
    if not bt.get("activo") or t - desde > cfg.bt_vigilancia_h * 3600:
        return False
    return crashes_desde(t - desde) > cfg.bt_max_crashes
