"""Diagnostico: convierte una medida en la causa probable de la falla, para actuar solo donde sirve.

El guardian anterior trataba toda falta de red igual y el 12-oct-2026 reinicio la tarjeta 50 veces
por un problema que no era de la tarjeta. Aqui cada causa tiene su propio remedio.
"""

from __future__ import annotations

from enum import StrEnum

from .sondas import Medida


class Estado(StrEnum):
    SANO = "sano"
    SIN_INTERFAZ = "sin_interfaz"  # el kernel perdio el dispositivo: reset PCI
    FIRMWARE = "firmware"  # el firmware no responde o acaba de fallar: reiniciarlo
    ZOMBI = "zombi"  # asociado pero sin trafico (el cuelgue clasico del 9560)
    DESASOCIADO = "desasociado"  # el punto de acceso esta pero no hay enlace: reasociar
    AP_AUSENTE = "ap_ausente"  # el router no se ve: no tocar el hardware, esperar
    PROVEEDOR = "proveedor"  # la red local responde y el internet no: no es la wifi


SIN_TOCAR_HARDWARE = frozenset({Estado.SANO, Estado.AP_AUSENTE, Estado.PROVEEDOR})


def diagnosticar(m: Medida, crash_reciente: bool = False) -> Estado:
    if not m.interfaz:
        return Estado.SIN_INTERFAZ
    # una sonda de firmware fallida o un crash solo cuentan si ademas no hay trafico: tras un crash el
    # firmware suele reiniciarse solo, y una lectura fallida con la red sana no justifica tocar nada
    if (not m.firmware or crash_reciente) and not (m.internet or m.puerta):
        return Estado.FIRMWARE
    if not m.asociado:
        return Estado.DESASOCIADO if m.ap_visible else Estado.AP_AUSENTE
    if m.internet:
        return Estado.SANO
    if m.puerta:
        return Estado.PROVEEDOR
    return Estado.ZOMBI
