#!/usr/bin/env bash
# respaldar.sh - Copia en /root/respaldo-radio-<fecha>.tgz todo lo que el controlador reemplaza o toca
# (guardian, escucha, unidades, modprobe, conexiones NM, estado de rfkill y parametros vivos).
# Corre en el Dell como root. Imprime la ruta del respaldo. Lo deshace restaurar.sh.
set -euo pipefail
umask 077  # el respaldo incluye secretos (wifi, token): nunca existe legible por otros
ts=$(date +%Y%m%d-%H%M%S)
dir=$(mktemp -d /root/.respaldo-radio-XXXXXX)
trap 'rm -rf -- "${dir:?}"' EXIT
archivos=(
  /usr/local/bin/dell-net-guardian.sh /usr/local/bin/dell-net-crash-listener.sh
  /usr/local/lib/guardian-aviso.sh /etc/dell-net-guardian.env /var/lib/dell-net-guardian
  /etc/systemd/system/dell-net-guardian.service /etc/systemd/system/dell-net-guardian.timer
  /etc/systemd/system/dell-net-crash-listener.service /etc/logrotate.d/dell-net-guardian
  /etc/modprobe.d /etc/NetworkManager/system-connections /etc/NetworkManager/conf.d
  /etc/udev/rules.d /etc/systemd/system/controlador-radio.service /etc/controlador-radio
)
for f in "${archivos[@]}"; do
  [[ -e "$f" ]] && cp -a --parents -- "$f" "$dir/" || echo "no existe (se omite): $f" >&2
done
{
  echo "# Estado vivo al $ts"
  for p in /sys/module/iwlwifi/parameters/* /sys/module/iwlmvm/parameters/*; do
    printf '%s=%s\n' "$p" "$(cat "$p" 2>/dev/null)"
  done
  rfkill -o ID,TYPE,DEVICE,SOFT,HARD
  lsmod | awk '$1 ~ /^(iwl|bt|bluetooth|mac80211|cfg80211)/'
  systemctl is-enabled dell-net-guardian.timer dell-net-crash-listener.service bluetooth.service 2>&1
  nmcli -f connection.id,802-11-wireless.band,802-11-wireless.powersave,ipv4.route-metric con show wifi-casa
} > "$dir/estado-vivo.txt" 2>&1
out=/root/respaldo-radio-$ts.tgz
tar -C "$dir" -czf "$out" .
chmod 600 "$out"
echo "$out"
