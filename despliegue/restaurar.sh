#!/usr/bin/env bash
# restaurar.sh [/root/respaldo-radio-<fecha>.tgz] - Deja el Dell como estaba antes del controlador:
# lo detiene y desinstala, y repone desde el respaldo (por defecto el mas antiguo, el previo a todo)
# el guardian, el escucha, sus unidades y /etc/modprobe.d (incluida la lista negra del Bluetooth).
# Corre en el Dell como root. No reinicia el equipo: la wifi sigue con el modulo ya cargado.
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo "requiere root" >&2; exit 1; }
respaldo=${1:-$(ls -1 /root/respaldo-radio-*.tgz | sort | head -1)}
[[ -f "$respaldo" ]] || { echo "no hay respaldo: $respaldo" >&2; exit 1; }
echo "restaurando desde $respaldo"

systemctl disable --now controlador-radio.service 2>/dev/null || true
systemctl disable watchdog-itco.service 2>/dev/null || true  # el modulo cargado se queda hasta reiniciar
systemctl stop controlador-radio-bt-reversa.timer 2>/dev/null || true
rm -f /etc/systemd/system/controlador-radio.service /etc/systemd/system/watchdog-itco.service \
      /usr/local/bin/controlador-radio /etc/modules-load.d/watchdog-itco.conf
rm -f /etc/systemd/system/dell-net-guardian.service.d/reserva.conf

dir=$(mktemp -d /root/.restaurar-radio-XXXXXX)
trap 'rm -rf -- "${dir:?}"' EXIT
tar -C "$dir" -xzf "$respaldo"
for f in usr/local/bin/dell-net-guardian.sh usr/local/bin/dell-net-crash-listener.sh \
         etc/systemd/system/dell-net-guardian.service etc/systemd/system/dell-net-guardian.timer \
         etc/systemd/system/dell-net-crash-listener.service; do
  [[ -e "$dir/$f" ]] && cp -a -- "$dir/$f" "/$f"
done
# modprobe.d: se quita lo que agrego el controlador y se repone el resto tal cual
rm -f /etc/modprobe.d/blacklist-bluetooth.conf.desactivado
cp -a -- "$dir/etc/modprobe.d/." /etc/modprobe.d/

systemctl daemon-reload
systemctl enable --now dell-net-guardian.timer dell-net-crash-listener.service
if grep -q '^blacklist btusb' /etc/modprobe.d/blacklist-bluetooth.conf 2>/dev/null; then
  systemctl disable --now bluetooth.service 2>/dev/null || true
  rfkill block bluetooth || true
  modprobe -r btusb btintel 2>/dev/null || true
fi
echo "restaurado; /opt/controlador-radio queda como referencia (borrarlo es opcional)"
systemctl is-active dell-net-guardian.timer dell-net-crash-listener.service
