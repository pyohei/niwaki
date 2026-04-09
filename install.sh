#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${NIWAKI_REPO_URL:-https://github.com/pyohei/niwaki}"
REPO_BRANCH="${NIWAKI_BRANCH:-main}"

log() {
  printf '[niwaki-setup] %s\n' "$*"
}

fail() {
  printf '[niwaki-setup] ERROR: %s\n' "$*" >&2
  exit 1
}

need_command() {
  command -v "$1" >/dev/null 2>&1 || fail "Required command not found: $1"
}

run_as_root() {
  if [ "$(id -u)" -eq 0 ]; then
    "$@"
    return
  fi
  need_command sudo
  sudo "$@"
}

run_as_target_user() {
  if [ "$(id -u)" -eq 0 ] && [ -n "${SUDO_USER:-}" ]; then
    sudo -u "$SUDO_USER" -H "$@"
    return
  fi
  "$@"
}

current_target_user() {
  if [ "$(id -u)" -eq 0 ] && [ -n "${SUDO_USER:-}" ]; then
    printf '%s\n' "$SUDO_USER"
    return
  fi
  id -un
}

current_target_home() {
  local target_user
  target_user="$(current_target_user)"
  if command -v getent >/dev/null 2>&1; then
    getent passwd "$target_user" | cut -d: -f6
    return
  fi
  if [ -n "${HOME:-}" ]; then
    printf '%s\n' "$HOME"
    return
  fi
  fail "Could not determine target home directory."
}

random_secret() {
  openssl rand -base64 32 | tr -d '\n' | tr '/+' 'ab'
}

read_env_value() {
  local env_path key

  env_path="$1"
  key="$2"
  awk -F= -v key="$key" '
    $1 == key {
      value = substr($0, index($0, "=") + 1)
      print value
    }
  ' "$env_path" | tail -n 1
}

detect_primary_host() {
  hostname -s 2>/dev/null || hostname
}

detect_primary_ip() {
  if [ -n "${NIWAKI_TARGET_IP:-}" ]; then
    printf '%s\n' "$NIWAKI_TARGET_IP"
    return
  fi

  if command -v ip >/dev/null 2>&1; then
    ip -4 route get 1.1.1.1 2>/dev/null | awk '
      /src/ {
        for (i = 1; i <= NF; i++) {
          if ($i == "src") {
            print $(i + 1)
            exit
          }
        }
      }
    '
    return
  fi

  hostname -I 2>/dev/null | awk '
    {
      for (i = 1; i <= NF; i++) {
        if ($i !~ /^127\./) {
          print $i
          exit
        }
      }
    }
  '
}

ensure_linux_supported() {
  [ "$(uname -s)" = "Linux" ] || fail "This installer currently supports Linux only."
  need_command apt-get

  case "$(uname -m)" in
    armv6l)
      fail "ARMv6 Raspberry Pi models are not supported by current official Docker packages."
      ;;
  esac
}

install_base_packages() {
  log "Installing base packages..."
  run_as_root apt-get update
  run_as_root apt-get install -y ca-certificates curl git gnupg openssl
}

resolve_docker_repo_family() {
  local arch os_id os_like

  arch="$(dpkg --print-architecture)"
  os_id="$(. /etc/os-release && printf '%s' "${ID:-}")"
  os_like="$(. /etc/os-release && printf '%s' "${ID_LIKE:-}")"

  case "${os_id}:${arch}" in
    raspbian:armhf)
      printf '%s\n' "raspbian"
      ;;
    ubuntu:*)
      printf '%s\n' "ubuntu"
      ;;
    debian:*|raspbian:*)
      printf '%s\n' "debian"
      ;;
    *)
      case " ${os_like} " in
        *" ubuntu "*)
          printf '%s\n' "ubuntu"
          ;;
        *" debian "*)
          printf '%s\n' "debian"
          ;;
        *)
          fail "Unsupported distribution. This installer expects Debian, Ubuntu, or Raspberry Pi OS."
          ;;
      esac
      ;;
  esac
}

install_docker() {
  local repo_family codename arch key_url key_tmp repo_line

  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    log "Docker and Docker Compose plugin are already installed."
    return
  fi

  log "Installing Docker Engine and Docker Compose plugin..."
  repo_family="$(resolve_docker_repo_family)"
  codename="$(. /etc/os-release && printf '%s' "${VERSION_CODENAME:-}")"
  arch="$(dpkg --print-architecture)"
  [ -n "$codename" ] || fail "Could not determine distro codename from /etc/os-release."

  key_url="https://download.docker.com/linux/${repo_family}/gpg"
  key_tmp="$(mktemp)"
  curl -fsSL "$key_url" -o "$key_tmp"

  run_as_root install -m 0755 -d /etc/apt/keyrings
  run_as_root install -m 0644 "$key_tmp" /etc/apt/keyrings/docker.asc
  rm -f "$key_tmp"

  repo_line="deb [arch=${arch} signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/${repo_family} ${codename} stable"
  printf '%s\n' "$repo_line" | run_as_root tee /etc/apt/sources.list.d/docker.list >/dev/null

  run_as_root apt-get update
  run_as_root apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

  if command -v systemctl >/dev/null 2>&1; then
    run_as_root systemctl enable --now docker
  fi
}

ensure_docker_group() {
  local target_user

  target_user="$(current_target_user)"
  if ! getent group docker >/dev/null 2>&1; then
    run_as_root groupadd docker
  fi

  if id -nG "$target_user" | grep -qw docker; then
    DOCKER_GROUP_ADDED=0
    return
  fi

  run_as_root usermod -aG docker "$target_user"
  DOCKER_GROUP_ADDED=1
}

docker_cli() {
  if docker info >/dev/null 2>&1; then
    docker "$@"
    return
  fi
  run_as_root docker "$@"
}

clone_or_update_repo() {
  local install_dir parent_dir existing_remote

  install_dir="$1"
  parent_dir="$(dirname "$install_dir")"
  run_as_target_user mkdir -p "$parent_dir"

  if [ -d "$install_dir/.git" ]; then
    existing_remote="$(run_as_target_user git -C "$install_dir" remote get-url origin)"
    [ "$existing_remote" = "$REPO_URL" ] || fail "Install dir already points to a different remote: $existing_remote"
    log "Updating existing Niwaki checkout..."
    run_as_target_user git -C "$install_dir" fetch --prune origin
    run_as_target_user git -C "$install_dir" checkout "$REPO_BRANCH"
    run_as_target_user git -C "$install_dir" pull --ff-only origin "$REPO_BRANCH"
    return
  fi

  if [ -e "$install_dir" ]; then
    fail "Install dir already exists and is not a git repository: $install_dir"
  fi

  log "Cloning Niwaki..."
  run_as_target_user git clone --branch "$REPO_BRANCH" "$REPO_URL" "$install_dir"
}

write_env_file_if_missing() {
  local install_dir stack_root env_path env_tmp primary_host primary_fqdn primary_ip
  local admin_password session_secret

  install_dir="$1"
  stack_root="$2"
  env_path="$install_dir/.env"

  primary_host="${NIWAKI_PRIMARY_HOST:-$(detect_primary_host)}"
  primary_fqdn="${primary_host}.local"
  primary_ip="$(detect_primary_ip || true)"
  admin_password="${NIWAKI_ADMIN_PASSWORD:-$(random_secret)}"
  session_secret="${NIWAKI_SESSION_SECRET:-$(random_secret)}"

  run_as_target_user mkdir -p "$install_dir/data" "$stack_root"

  PRIMARY_URL="http://${primary_fqdn}/niwaki/"
  MDNS_URL="http://${primary_fqdn}/mdns/"
  GENERATED_ADMIN_PASSWORD=""
  DETECTED_TARGET_IP="$primary_ip"

  if [ -f "$env_path" ]; then
    log ".env already exists. Leaving it untouched."
    PRIMARY_URL="$(read_env_value "$env_path" APP_BASE_URL || true)"
    DETECTED_TARGET_IP="$(read_env_value "$env_path" MDNS_TARGET_IP || true)"
    if [ -z "$PRIMARY_URL" ]; then
      PRIMARY_URL="http://${primary_fqdn}/niwaki/"
    fi
    if [ -n "$(read_env_value "$env_path" BOOTSTRAP_HOST || true)" ]; then
      MDNS_URL="http://$(read_env_value "$env_path" BOOTSTRAP_HOST || true)/mdns/"
    fi
    return
  fi

  env_tmp="$(mktemp)"
  cat >"$env_tmp" <<EOF
TRAEFIK_DASHBOARD_HOST=traefik.local
MDNS_TARGET_IP=${primary_ip}

APP_HOST=0.0.0.0
APP_PORT=8787
APP_BASE_URL=${PRIMARY_URL}
APP_BASE_PATH=/niwaki

BOOTSTRAP_HOST=${primary_fqdn}
BOOTSTRAP_PORT=80

TRAEFIK_ENABLED=true
TRAEFIK_HOST=niwaki.local
TRAEFIK_FALLBACK_HOST=${primary_fqdn}
TRAEFIK_ENTRYPOINT=web
TRAEFIK_DOCKER_NETWORK=proxy

ADMIN_USERNAME=admin
ADMIN_PASSWORD=${admin_password}
SESSION_SECRET=${session_secret}

SETTINGS_DB_PATH=./data/niwaki.db
STACK_ROOT=${stack_root}
EOF

  run_as_target_user mv "$env_tmp" "$env_path"
  GENERATED_ADMIN_PASSWORD="$admin_password"
}

start_services() {
  local install_dir

  install_dir="$1"
  log "Starting Traefik and Niwaki..."
  cd "$install_dir"
  docker_cli compose -f compose.yaml -f compose.niwaki.yaml up -d --build
}

main() {
  local install_dir stack_root target_user target_home

  ensure_linux_supported
  target_user="$(current_target_user)"
  target_home="$(current_target_home)"
  install_dir="${NIWAKI_INSTALL_DIR:-${target_home}/niwaki}"
  stack_root="${NIWAKI_STACK_ROOT:-${install_dir}/stacks}"

  install_base_packages
  install_docker
  ensure_docker_group
  clone_or_update_repo "$install_dir"
  write_env_file_if_missing "$install_dir" "$stack_root"
  start_services "$install_dir"

  printf '\n'
  log "Setup completed."
  printf 'Install dir: %s\n' "$install_dir"
  printf 'Primary URL: %s\n' "$PRIMARY_URL"
  printf 'mDNS Admin: %s\n' "$MDNS_URL"
  printf 'Admin user: admin\n'
  if [ -n "$GENERATED_ADMIN_PASSWORD" ]; then
    printf 'Generated admin password: %s\n' "$GENERATED_ADMIN_PASSWORD"
  else
    printf 'Admin password: existing value from %s\n' "$install_dir/.env"
  fi
  if [ -n "$DETECTED_TARGET_IP" ]; then
    printf 'MDNS_TARGET_IP: %s\n' "$DETECTED_TARGET_IP"
  else
    printf 'MDNS_TARGET_IP: not detected. Update %s/.env before creating aliases.\n' "$install_dir"
  fi
  if [ "${DOCKER_GROUP_ADDED:-0}" -eq 1 ]; then
    printf 'Docker group: added %s to docker. Log out and back in before using docker without sudo.\n' "$target_user"
  fi
}

main "$@"
