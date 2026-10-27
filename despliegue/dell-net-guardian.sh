#!/usr/bin/env bash
# Guardian de red WiFi del Dell: detecta cuelgue del firmware iwlwifi (SYSASSERT
# NOTA (28-jul-2026): absorbio funcionalidad del ex wifi-watchdog.sh v2 (marzo).
# El viejo watchdog quedo deshabilitado y renombrado a .disabled. El nivel 0 de
# este guardian (nmcli disconnect+connect) cubre el flujo del viejo incluyendo
# DHCP renewal implicito. Nivel 1 (recarga iwlwifi) es mas agresivo que el
# restart NetworkManager que hacia el viejo.
# zombie: asociado con IP pero sin trafico) y recupera en caliente con escalada.
set -uo pipefail

ENV_FILE=/etc/dell-net-guardian.env
# shellcheck source=/etc/dell-net-guardian.env
[ -r "$ENV_FILE" ] && . "$ENV_FILE"
IFACE=${IFACE:-wlp0s20f3}
NMCON=${NMCON:-wifi-casa}
PCI=${PCI:-0000:00:14.3}
GATEWAY=${GATEWAY:-192.168.1.254}
INET=${INET:-1.1.1.1}
THRESHOLD=${THRESHOLD:-2}          # ciclos fallidos antes de actuar (histeresis)
LOG=/var/log/dell-net-guardian.log
STATE_DIR=/var/lib/dell-net-guardian
mkdir -p "$STATE_DIR"
FAILS_F="$STATE_DIR/fails"; LEVEL_F="$STATE_DIR/level"
FAILS=$(cat "$FAILS_F" 2>/dev/null || echo 0)
LEVEL=$(cat "$LEVEL_F" 2>/dev/null || echo 0)

log(){ echo "$(date -Iseconds) $*" >>"$LOG"; }
# Politica de avisos (lo que se arregla solo no suena): ver /usr/local/lib/guardian-aviso.sh.
# Sin el modulo solo sale el critical, para no volver a sonar en cada paso de la escalada.
GUARDIAN_NOMBRE=Dell
. /usr/local/lib/guardian-aviso.sh 2>/dev/null || {
  tg_resumen(){ :; }
  tg(){ [ "$1" = critical ] && [ -n "${TELEGRAM_BOT_TOKEN:-}" ] || return 0; shift
    curl -s -m 10 -o /dev/null "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
      --data-urlencode "chat_id=${TELEGRAM_CHAT_ID}" --data-urlencode "text=$*" 2>/dev/null || true; }
}
# Siempre por la wifi: con el celular por cable USB como segunda salida, un ping sin -I saldria por el
# cable con la wifi caida y el guardian creeria que hay red (2026-10-25).
online(){ ping -c1 -W2 -I "$IFACE" "$GATEWAY" >/dev/null 2>&1 || ping -c1 -W2 -I "$IFACE" "$INET" >/dev/null 2>&1 \
  || ping -c1 -W2 -I "$IFACE" "${INET2:-8.8.8.8}" >/dev/null 2>&1; }
sysassert_recent(){ journalctl -k --since "-120s" 2>/dev/null \
  | grep -qiE "Microcode SW error|SYSASSERT|Device error - SW reset"; }
last_kern(){ journalctl -k --since "-180s" 2>/dev/null | grep -i iwlwifi | tail -1; }

if online; then
  tg_resumen
  if [ "${FAILS:-0}" -gt 0 ] || [ "${LEVEL:-0}" -gt 0 ]; then
    log "RECUPERADO (tras fails=$FAILS level=$LEVEL)"
    tg recovered "Dell WiFi RECUPERADO. Escalon usado: nivel $LEVEL. $(last_kern)"
  fi
  echo 0 >"$FAILS_F"; echo 0 >"$LEVEL_F"
  exit 0
fi

FAILS=$((FAILS+1)); echo "$FAILS" >"$FAILS_F"
log "SIN CONECTIVIDAD (fails=$FAILS level=$LEVEL) $(last_kern)"
if [ "$FAILS" -lt "$THRESHOLD" ] && ! sysassert_recent; then
  exit 0   # histeresis: espera confirmacion salvo crash de firmware evidente
fi

# Elegir escalon; si hay SYSASSERT reciente, saltar directo a recarga de modulo
ACT=$LEVEL
sysassert_recent && [ "$LEVEL" -lt 1 ] && ACT=1

case "$ACT" in
  0) log "ACCION nivel0: nmcli reconnect"; tg n0 "Dell WiFi caido -> reconectando (nivel 0)"
     timeout 20 nmcli device disconnect "$IFACE" 2>/dev/null; sleep 1
     timeout 20 nmcli device connect "$IFACE" 2>/dev/null || timeout 30 nmcli con up "$NMCON" 2>/dev/null ;;
  1) log "ACCION nivel1: recarga modulo iwlwifi"; tg n1 "Dell WiFi: recargando driver iwlwifi (nivel 1). $(last_kern)"
     timeout 20 modprobe -r iwlmvm 2>/dev/null; timeout 20 modprobe -r iwlwifi 2>/dev/null; sleep 3
     timeout 20 modprobe iwlwifi 2>/dev/null; sleep 4; timeout 30 nmcli con up "$NMCON" 2>/dev/null ;;
  *) log "ACCION nivel2: PCI remove+rescan $PCI"; tg n2 "Dell WiFi: reset PCI del adaptador (nivel 2). $(last_kern)"
     timeout 20 sh -c "echo 1 >/sys/bus/pci/devices/$PCI/remove" 2>/dev/null; sleep 3
     timeout 20 sh -c "echo 1 >/sys/bus/pci/rescan" 2>/dev/null; sleep 5; timeout 30 nmcli con up "$NMCON" 2>/dev/null ;;
esac

NEXT=$((ACT+1)); [ "$NEXT" -gt 2 ] && NEXT=2; echo "$NEXT" >"$LEVEL_F"
sleep 8
if online; then
  log "RECUPERADO tras accion nivel$ACT"
  tg recovered "Dell WiFi RECUPERADO tras nivel $ACT. $(last_kern)"
  echo 0 >"$FAILS_F"; echo 0 >"$LEVEL_F"
else
  log "AUN CAIDO tras nivel$ACT, escalara a nivel$NEXT en el proximo ciclo"
  [ "$ACT" -ge 2 ] && tg critical "Dell WiFi NO recupera tras reset PCI. Requiere revision fisica. $(last_kern)"
fi

# Auto-reschedule: si acabo de escalar y no recupere, forzar re-verificacion en 10s
# (el timer principal es cada 15s; esto da un ciclo extra rapido durante escalado activo)
LEVEL_END=$(cat "$LEVEL_F" 2>/dev/null || echo 0)
if [ "$LEVEL_END" -gt 0 ] && command -v systemd-run >/dev/null 2>&1; then
  systemd-run --quiet --on-active=10s --unit="dell-net-guardian-boost-$(date +%s)" \
    systemctl start dell-net-guardian.service 2>/dev/null || true
fi
