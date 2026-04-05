# Traefik / Portainer Compose

このリポジトリは、`mDNS` ベースのローカル LAN 向け `Traefik` / `Portainer` 用 Docker Compose 構成です。

次の 2 パターンで利用できます。

- `Traefik` 単体で起動する
- `Traefik` と `Portainer` を一緒に起動する

## ファイル構成

- [`compose.yaml`](/Users/shohei/Dev/portainer/compose.yaml): `Traefik` の基本構成
- [`compose.portainer.yaml`](/Users/shohei/Dev/portainer/compose.portainer.yaml): `Portainer` を追加するための構成
- [`.env.example`](/Users/shohei/Dev/portainer/.env.example): 環境変数のサンプル

## 前提

- Docker Engine と Docker Compose Plugin が使えること
- `80` を開けられること
- Raspberry Pi 側で `*.local` の名前解決ができること

この構成は `http` 前提です。`Let's Encrypt` や公開向け `https` は使いません。

## 初期設定

`.env` を作成します。

```bash
cp .env.example .env
```

必要に応じて `.env` を編集します。

```env
TRAEFIK_DASHBOARD_HOST=traefik.local
PORTAINER_HOST=portainer.local
```

## 起動方法

### 1. Traefik 単体で使う

```bash
docker compose up -d
```

### 2. Traefik と Portainer を一緒に使う

```bash
docker compose -f compose.yaml -f compose.portainer.yaml up -d
```

## アクセス URL

- Traefik dashboard: `http://traefik.local`
- Portainer: `http://portainer.local`

Raspberry Pi のホスト名が別で、`portainer.local` や `traefik.local` を使いたい場合は、Pi 側で Avahi alias を追加してください。

## Raspberry Pi 側の mDNS alias 設定

Raspberry Pi は通常 `raspberrypi.local` のような 1 つの名前だけを `mDNS` で公開します。`traefik.local` と `portainer.local` を追加で使う場合は、別名を広告する設定が必要です。

まず `avahi-utils` を入れます。

```bash
sudo apt update
sudo apt install -y avahi-daemon avahi-utils
```

次に systemd のテンプレート unit を作成します。

```ini
[Unit]
Description=Publish %I as an mDNS alias
After=avahi-daemon.service network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/bin/sh -c 'set -- $$(/usr/bin/hostname -I); exec /usr/bin/avahi-publish-address -R %I "$$1"'
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

ファイル名は `/etc/systemd/system/avahi-alias@.service` とします。

その後、2 つの alias を有効化します。

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now [email protected]
sudo systemctl enable --now [email protected]
```

これで同じ Raspberry Pi に対して次の名前でアクセスできます。

- `http://traefik.local`
- `http://portainer.local`

## 停止方法

### Traefik 単体を停止

```bash
docker compose down
```

### Traefik と Portainer をまとめて停止

```bash
docker compose -f compose.yaml -f compose.portainer.yaml down
```

## 構成の考え方

- `compose.yaml` は常にベースとして使う
- `compose.portainer.yaml` は `Portainer` が必要なときだけ追加する
- `Portainer` は `Traefik` の `proxy` ネットワークに参加し、labels でルーティングする
- `Traefik` dashboard は `traefik.local` で公開する
- `Portainer` は `portainer.local` で公開する

この分け方にしておくと、今後ほかのアプリを追加するときも `compose.<app>.yaml` を増やすだけで運用できます。
