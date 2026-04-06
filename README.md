# Traefik / Portainer Compose

このリポジトリは、`mDNS` ベースのローカル LAN 向け `Traefik` / `Portainer` 用 Docker Compose 構成です。

次の 2 パターンで利用できます。

- `Traefik` 単体で起動する
- `Traefik` と `Portainer` を一緒に起動する
- 必要なら `mDNS alias` 管理 UI を追加する

## ファイル構成

- [`compose.yaml`](/Users/shohei/Dev/portainer/compose.yaml): `Traefik` の基本構成
- [`compose.portainer.yaml`](/Users/shohei/Dev/portainer/compose.portainer.yaml): `Portainer` を追加するための構成
- [`compose.mdns-admin.yaml`](/Users/shohei/Dev/portainer/compose.mdns-admin.yaml): `mDNS alias` 管理 UI の構成
- [`mdns-admin/`](/Users/shohei/Dev/portainer/mdns-admin): `mDNS alias` 管理 UI 本体
- [`.env.example`](/Users/shohei/Dev/portainer/.env.example): 環境変数のサンプル

## 前提

- Docker Engine と Docker Compose Plugin が使えること
- `80` を開けられること
- Raspberry Pi 側で `*.local` の名前解決ができること
- `Traefik` は [`compose.yaml`](/Users/shohei/Dev/portainer/compose.yaml) の `traefik:v3.6` を使うこと

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
MDNS_ADMIN_USERNAME=admin
MDNS_ADMIN_PASSWORD=
MDNS_TARGET_IP=192.168.1.10
```

`MDNS_ADMIN_PASSWORD` を空にすると、`mdns-admin` は初回起動時にランダムなパスワードを生成し、volume 内に保存して再起動後も使い回します。

## 起動方法

### 1. Traefik 単体で使う

```bash
docker compose up -d
```

### 2. Traefik と Portainer を一緒に使う

```bash
docker compose -f compose.yaml -f compose.portainer.yaml up -d
```

### 3. Traefik と mDNS alias 管理 UI を使う

```bash
docker compose -f compose.yaml -f compose.mdns-admin.yaml up -d --build
```

### 4. Traefik と Portainer と mDNS alias 管理 UI を使う

```bash
docker compose -f compose.yaml -f compose.portainer.yaml -f compose.mdns-admin.yaml up -d --build
```

## アクセス URL

- Traefik dashboard: `http://traefik.local`
- Portainer: `http://portainer.local`
- mDNS alias 管理 UI: `http://raspberrypi.local/mdns/`

Raspberry Pi のホスト名が別で、`portainer.local` や `traefik.local` を使いたい場合は、Pi 側で Avahi alias を追加してください。

`mDNS alias` 管理 UI は `raspberrypi.local` 配下に置いているので、alias 自体がまだ無くても開けます。

## mDNS alias 管理 UI

[`compose.mdns-admin.yaml`](/Users/shohei/Dev/portainer/compose.mdns-admin.yaml) は、ブラウザから `*.local` alias を追加・削除するための UI です。

- ルートは `http://raspberrypi.local/mdns/`
- HTTP Basic 認証を使います
- 追加した alias は Docker-managed な publisher コンテナとして維持されます
- 既存の `systemd` ベース alias はそのまま残り、この UI では一覧に出ません
- host 側で `avahi-daemon` が動いている必要があります
- `MDNS_ADMIN_PASSWORD` が空なら初回起動時に自動生成されます

使い方は次の通りです。

1. `.env` の `MDNS_TARGET_IP` を Raspberry Pi の LAN 内 IP に合わせる
2. `MDNS_ADMIN_PASSWORD` を固定値にするか、空のまま自動生成にする
3. 必要なら `sudo apt install -y avahi-daemon` を入れて有効化する
4. `compose.mdns-admin.yaml` を追加して起動する
5. `http://raspberrypi.local/mdns/` を開いて alias を追加する

この UI で新しい alias を作れば、以後は Raspberry Pi に SSH せずに `gitea.local` などを増やせます。

自動生成したパスワードは初回起動ログに出ます。確認する場合は次を使います。

```bash
docker compose -f compose.yaml -f compose.mdns-admin.yaml logs mdns-admin
```

新しいランダムパスワードにしたい場合は、`mdns_admin_data` volume を削除してから再起動してください。

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

その後、`avahi-alias@.service` の instance を 2 つ有効化します。

- `traefik.local` 用
- `portainer.local` 用

```bash
sudo systemctl daemon-reload
for alias in traefik.local portainer.local; do
  sudo systemctl enable --now "avahi-alias@${alias}.service"
done
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

### Traefik と mDNS alias 管理 UI を停止

```bash
docker compose -f compose.yaml -f compose.mdns-admin.yaml down
```

## 構成の考え方

- `compose.yaml` は常にベースとして使う
- `compose.portainer.yaml` は `Portainer` が必要なときだけ追加する
- `compose.mdns-admin.yaml` は alias をブラウザから管理したいときに追加する
- `Portainer` は `Traefik` の `proxy` ネットワークに参加し、labels でルーティングする
- `Traefik` dashboard は `traefik.local` で公開する
- `Portainer` は `portainer.local` で公開する
- `mDNS alias` 管理 UI は `raspberrypi.local/mdns/` で公開する

この分け方にしておくと、今後ほかのアプリを追加するときも `compose.<app>.yaml` を増やすだけで運用できます。
