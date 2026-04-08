# Traefik / mDNS Compose

このリポジトリは、`mDNS` ベースのローカル LAN 向け `Traefik` と `mDNS alias` 管理 UI 用 Docker Compose 構成です。

## ファイル構成

- [`compose.yaml`](/Users/shohei/Dev/portainer/compose.yaml): `Traefik` の基本構成
- [`compose.mdns-admin.yaml`](/Users/shohei/Dev/portainer/compose.mdns-admin.yaml): `mDNS alias` 管理 UI の構成
- [`mdns-admin/`](/Users/shohei/Dev/portainer/mdns-admin): `mDNS alias` 管理 UI 本体
- [`.env.example`](/Users/shohei/Dev/portainer/.env.example): 環境変数のサンプル

## 前提

- Docker Engine と Docker Compose Plugin が使えること
- `80` を開けられること
- Raspberry Pi 側で `*.local` の名前解決ができること
- host 側で `avahi-daemon` が動いていること

この構成は `http` 前提です。`Let's Encrypt` や公開向け `https` は使いません。

## 初期設定

`.env` を作成します。

```bash
cp .env.example .env
```

必要に応じて `.env` を編集します。

```env
TRAEFIK_DASHBOARD_HOST=traefik.local
MDNS_ADMIN_USERNAME=admin
MDNS_ADMIN_PASSWORD=
MDNS_TARGET_IP=192.168.1.10
```

- `TRAEFIK_DASHBOARD_HOST`: Traefik dashboard 用の `.local` 名
- `MDNS_TARGET_IP`: Raspberry Pi の LAN 内 IP
- `MDNS_ADMIN_PASSWORD`: 空にすると初回起動時にランダム生成して volume に保存

`avahi-daemon` が未導入なら入れておきます。

```bash
sudo apt update
sudo apt install -y avahi-daemon
```

## 起動方法

### 1. Traefik 単体で使う

```bash
docker compose up -d
```

### 2. Traefik と mDNS alias 管理 UI を使う

```bash
docker compose -f compose.yaml -f compose.mdns-admin.yaml up -d --build
```

## アクセス URL

- Traefik dashboard: `http://traefik.local`
- mDNS alias 管理 UI: `http://raspberrypi.local/mdns/`

`mDNS alias` 管理 UI は `raspberrypi.local` 配下に置いているので、alias 自体がまだ無くても開けます。

## mDNS alias 管理 UI

[`compose.mdns-admin.yaml`](/Users/shohei/Dev/portainer/compose.mdns-admin.yaml) は、ブラウザから `*.local` alias を追加・削除するための UI です。

- ルートは `http://raspberrypi.local/mdns/`
- HTTP Basic 認証を使います
- 追加した alias は Docker-managed な publisher コンテナとして維持されます
- 既存の `systemd` ベース alias は一覧に出ません
- `MDNS_ADMIN_PASSWORD` が空なら初回起動時に自動生成されます

使い方は次の通りです。

1. `.env` の `MDNS_TARGET_IP` を Raspberry Pi の LAN 内 IP に合わせる
2. `MDNS_ADMIN_PASSWORD` を固定値にするか、空のまま自動生成にする
3. `compose.mdns-admin.yaml` を追加して起動する
4. `http://raspberrypi.local/mdns/` を開いて alias を追加する

この UI で新しい alias を作れば、以後は Raspberry Pi に SSH せずに `gitea.local` などを増やせます。

自動生成したパスワードは初回起動ログに出ます。確認する場合は次を使います。

```bash
docker compose -f compose.yaml -f compose.mdns-admin.yaml logs mdns-admin
```

新しいランダムパスワードにしたい場合は、`mdns_admin_data` volume を削除してから再起動してください。

## 停止方法

### Traefik 単体を停止

```bash
docker compose down
```

### Traefik と mDNS alias 管理 UI を停止

```bash
docker compose -f compose.yaml -f compose.mdns-admin.yaml down
```

## 補足

- 以前の `systemd` ベース alias と同じ名前を `mdns-admin` でも作ると重複広告になるので避けてください
- 今後ほかのアプリを追加するときは、各 app 用の Compose を別ファイルで足して `Host(\`gitea.local\`)` のような Traefik label を付ける運用が素直です
