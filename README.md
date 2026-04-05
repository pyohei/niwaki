# Traefik / Portainer Compose

このリポジトリは、`Traefik` をベースにした Docker Compose 構成です。

次の 2 パターンで利用できます。

- `Traefik` 単体で起動する
- `Traefik` と `Portainer` を一緒に起動する

## ファイル構成

- [`compose.yaml`](/Users/shohei/Dev/portainer/compose.yaml): `Traefik` の基本構成
- [`compose.portainer.yaml`](/Users/shohei/Dev/portainer/compose.portainer.yaml): `Portainer` を追加するための構成
- [`.env.example`](/Users/shohei/Dev/portainer/.env.example): 環境変数のサンプル

## 前提

- Docker Engine と Docker Compose Plugin が使えること
- `80` と `443` を開けられること
- Let's Encrypt を使う場合は対象ホスト名がこのサーバーを向いていること

## 初期設定

`.env` を作成します。

```bash
cp .env.example .env
```

必要に応じて `.env` を編集します。

```env
TRAEFIK_ACME_EMAIL=admin@example.com
PORTAINER_HOST=portainer.example.com
```

Let's Encrypt の保存先を作成します。

```bash
mkdir -p letsencrypt
touch letsencrypt/acme.json
chmod 600 letsencrypt/acme.json
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

`Portainer` は `PORTAINER_HOST` に設定したホスト名で公開されます。

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

この分け方にしておくと、今後ほかのアプリを追加するときも `compose.<app>.yaml` を増やすだけで運用できます。
