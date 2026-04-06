#!/bin/sh
set -eu

mode="${1:-web}"
password_file="${MDNS_ADMIN_PASSWORD_FILE:-/data/admin-password}"

if [ "$mode" = "publisher" ]; then
  : "${MDNS_ALIAS:?MDNS_ALIAS is required}"
  : "${MDNS_TARGET_IP:?MDNS_TARGET_IP is required}"
  export DBUS_SYSTEM_BUS_ADDRESS="${DBUS_SYSTEM_BUS_ADDRESS:-unix:path=/var/run/dbus/system_bus_socket}"
  exec avahi-publish-address -R "$MDNS_ALIAS" "$MDNS_TARGET_IP"
fi

if [ -z "${MDNS_ADMIN_PASSWORD:-}" ]; then
  mkdir -p "$(dirname "$password_file")"
  if [ -f "$password_file" ]; then
    MDNS_ADMIN_PASSWORD="$(cat "$password_file")"
  else
    umask 077
    MDNS_ADMIN_PASSWORD="$(tr -dc 'A-Za-z0-9' </dev/urandom | head -c 24)"
    printf '%s\n' "$MDNS_ADMIN_PASSWORD" >"$password_file"
    echo "[mdns-admin] Generated admin password and saved it to $password_file"
    echo "[mdns-admin] Admin password: $MDNS_ADMIN_PASSWORD"
  fi
  export MDNS_ADMIN_PASSWORD
fi

exec python /app/server.py
