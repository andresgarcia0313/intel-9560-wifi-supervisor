from falso import SistemaFalso
from radio_dell.config import Config
from radio_dell.diagnostico import Estado, diagnosticar
from radio_dell.sondas import medir

CFG = Config()


def causa(s: SistemaFalso, crash: bool = False) -> Estado:
    return diagnosticar(medir(s, CFG), crash)


def test_sano_mide_senal_y_tasa() -> None:
    s = SistemaFalso()
    m = medir(s, CFG)
    assert diagnosticar(m) is Estado.SANO
    assert (m.senal, m.tasa_tx, m.temperatura) == (-56, 866.7, 57)


def test_pings_salen_siempre_por_la_wifi_no_por_el_cable_usb() -> None:
    s = SistemaFalso()
    medir(s, CFG)
    pings = [o for o in s.ordenes if o[0] == "ping"]
    assert pings and all(o[o.index("-I") + 1] == "wlp0s20f3" for o in pings)


def test_zombi_asociado_sin_trafico() -> None:
    s = SistemaFalso()
    s.puerta = s.internet = False
    assert causa(s) is Estado.ZOMBI


def test_proveedor_no_es_culpa_de_la_wifi() -> None:
    s = SistemaFalso()
    s.internet = False
    assert causa(s) is Estado.PROVEEDOR


def test_ap_ausente_frente_a_desasociado() -> None:
    s = SistemaFalso()
    s.asociado = False
    assert causa(s) is Estado.DESASOCIADO
    s.ssid_visible = False
    assert causa(s) is Estado.AP_AUSENTE


def test_firmware_mudo_y_sin_interfaz() -> None:
    s = SistemaFalso()
    s.firmware = s.puerta = s.internet = False
    assert causa(s) is Estado.FIRMWARE
    del s.archivos["/sys/class/net/wlp0s20f3/operstate"]
    assert causa(s) is Estado.SIN_INTERFAZ


def test_crash_que_el_firmware_resolvio_solo_no_pide_accion() -> None:
    s = SistemaFalso()
    assert causa(s, crash=True) is Estado.SANO
    s.internet = s.puerta = False
    assert causa(s, crash=True) is Estado.FIRMWARE


def test_sonda_de_firmware_fallida_con_red_sana_no_es_falla() -> None:
    s = SistemaFalso()
    s.firmware = False  # sin temperatura ni eco, pero el trafico pasa
    assert causa(s) is Estado.SANO
