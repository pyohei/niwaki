# Niwaki

Niwaki は、単一ホストの Docker Compose スタックをブラウザから管理するための小さなデプロイ UI です。
Git 管理された Compose ファイルを source of truth とし、stack 一覧、deploy、logs、mDNS alias 管理を一つの画面から扱えるようにします。

このリポジトリには、既存の `Traefik` / `mdns-admin` 構成も同居しています。
当面は以下を並行して持ちます。

- `compose.yaml`: Traefik
- `compose.mdns-admin.yaml`: 既存の mDNS alias 管理 UI
- `compose.niwaki.yaml`: Niwaki を Traefik に載せる overlay
- `mdns-admin/`: 既存の mDNS alias 管理 UI 実装
- `app/`: Niwaki 本体
- `docs/`: UI / bootstrap / mDNS の設計メモ

## 現在の状態

初期実装として、以下を入れています。

- stack registry の読み込み
- stack 一覧 / 詳細 API
- `git fetch` / `git pull --ff-only`
- `docker compose config` / `pull` / `up -d` / `restart` / `down`
- `docker compose logs`
- 実行履歴の JSON Lines 保存
- `mdns-admin` 互換ラベルを使った alias 一覧 / 作成 / 削除
- SQLite ベースの stack registry 編集
- システム共通の Git credential 保存
- stack ごとの `repo_url` 保存と `git clone`
- Portainer / ECS 風の簡易 Web UI
- `daisyUI v4.12.24` を使った静的 UI スタイル

## ディレクトリ構成

```text
.
├── AGENTS.md
├── CLAUDE.md
├── README.md
├── app/
│   ├── backend/
│   └── frontend/
├── docs/
├── compose.yaml
├── compose.mdns-admin.yaml
└── mdns-admin/
```

## 起動方法

今の主導線は `Traefik` 経由です。alias が無くても `raspberrypi.local/niwaki/` で入れる前提にして、`deploy.local` は追加したら使える常用 URL として扱います。

### 1. 設定ファイルを用意する

```bash
cp .env.example .env
```

`.env` の例:

```env
APP_HOST=0.0.0.0
APP_PORT=8787
APP_BASE_URL=http://raspberrypi.local/niwaki/
APP_BASE_PATH=/niwaki
ADMIN_USERNAME=admin
ADMIN_PASSWORD=change-me
SETTINGS_DB_PATH=./data/niwaki.db
STACK_ROOT=/opt/rpi-infra
MDNS_TARGET_IP=192.168.1.10
```

### 2. stack registry を編集する

stack registry は SQLite のみで保持します。
起動直後は空なので、`Stack Registry` パネルから stack を追加してください。
`repo_url` を入れておくと、`Stack Detail` から `Clone` を実行できます。

### 3. Traefik 経由で起動する

```bash
docker compose -f compose.yaml -f compose.mdns-admin.yaml -f compose.niwaki.yaml up -d --build
```

デフォルトでは以下で開けます。

- primary URL: `http://raspberrypi.local/niwaki/`
- alias URL: `http://deploy.local/`

起動後は UI 上で以下を管理できます。

- `Stack Registry`: stack の追加 / 更新 / 削除
- `Clone`: stack ごとの `repo_url` を使った `git clone`
- `Git Credential`: システム共通の HTTPS credential 保存
- `mDNS Aliases`: `mdns-admin` 互換ラベルでの alias 管理

### 4. 直接起動で確認する場合

```bash
python3 -m app.backend
```

この場合だけ `http://raspberrypi.local:8787/` や `http://<raspberry-pi-ip>:8787/` で確認できます。

## UI スタイルの更新方法

フロントエンドの CSS は `tailwindcss@3.4.4` と `daisyui@4.12.24` を pinned して生成します。

```bash
npm install
npm run build:css
```

## Git credential について

Git credential は `SETTINGS_DB_PATH` の SQLite に 1 組だけ保存し、`git clone` / `git fetch` / `git pull --ff-only` 実行時にだけ `GIT_ASKPASS` 経由で注入します。
command log や UI 一覧には password / token 自体は出しません。

## 既存の Traefik / mDNS 構成

Traefik 単体:

```bash
docker compose up -d
```

Traefik と既存 mDNS 管理 UI:

```bash
docker compose -f compose.yaml -f compose.mdns-admin.yaml up -d --build
```

Traefik と Niwaki:

```bash
docker compose -f compose.yaml -f compose.niwaki.yaml up -d --build
```

既存 mDNS 管理 UI は、`http://raspberrypi.local/mdns/` で引き続き使えます。
Niwaki 側の mDNS 管理は、この UI のラベル規約と互換性を持たせています。

## 今後の前提

- Git が正本
- stack registry で明示した Compose だけを操作
- `Portainer` の内部作業ディレクトリには依存しない
- `raspberrypi.local/niwaki/` を alias 不要の primary 導線として持つ
- `deploy.local` は追加後の常用 URL として扱う
- `raspberrypi.local:8787` は compose の標準導線ではなく、必要時の直接確認用に留める
