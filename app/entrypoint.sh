#!/bin/sh
set -eu

mode="${1:-web}"

case "$mode" in
  publisher)
    shift
    : "${MDNS_ALIAS:?MDNS_ALIAS is required}"
    : "${MDNS_TARGET_IP:?MDNS_TARGET_IP is required}"
    export DBUS_SYSTEM_BUS_ADDRESS="${DBUS_SYSTEM_BUS_ADDRESS:-unix:path=/var/run/dbus/system_bus_socket}"
    exec avahi-publish-address -R "$MDNS_ALIAS" "$MDNS_TARGET_IP"
    ;;
  web)
    [ "$#" -gt 0 ] && shift
    exec python3 -m app.backend "$@"
    ;;
  *)
    exec "$@"
    ;;
esac
