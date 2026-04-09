# Niwaki

Niwaki は、単一ホストの Docker Compose スタックをブラウザから管理するための小さなデプロイ UI です。
Git 管理された Compose ファイルを source of truth とし、stack ごとの詳細ページ、deploy、logs、mDNS alias 管理を扱います。

このリポジトリには、`Traefik` と `Niwaki` を同居させています。
`Niwaki` は mDNS alias UI と publisher 機能を内包しているため、別の `mdns-admin` compose は不要です。
主に以下で構成します。

- `compose.yaml`: Traefik
- `compose.niwaki.yaml`: Niwaki を Traefik に載せる overlay
- `compose.local.yaml`: localhost 用のローカル Docker overlay
- `app/`: Niwaki 本体
- `docs/`: UI / bootstrap / mDNS の設計メモ

## 現在の状態

初期実装として、以下を入れています。

- stack registry の読み込み
- stack 一覧 / 詳細 API
- `git fetch` / `git pull --ff-only`
- `docker compose config` / `pull` / `up -d` / `restart` / `down`
- `docker compose logs`
- 実行履歴の SQLite 保存
- `mdns-admin` 互換ラベルを使った alias 一覧 / 作成 / 削除
- `niwaki:local` を使った mDNS alias publisher
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
├── compose.local.yaml
└── compose.niwaki.yaml
```

## クイックセットアップ

Raspberry Pi OS / Debian / Ubuntu 系であれば、`install.sh` をそのまま流してセットアップできます。
このスクリプトは Git、Docker、`avahi-daemon`、`dbus` を入れて、`https://github.com/pyohei/niwaki` を clone し、`.env` を初回生成してから `Traefik + Niwaki` を起動します。

```bash
curl -fsSL https://raw.githubusercontent.com/pyohei/niwaki/main/install.sh | bash
```

デフォルトの clone 先は `~/niwaki` です。変えたい場合は、実行時に `NIWAKI_INSTALL_DIR` を渡してください。

```bash
curl -fsSL https://raw.githubusercontent.com/pyohei/niwaki/main/install.sh | NIWAKI_INSTALL_DIR=/opt/niwaki bash
```

初回起動時は `ADMIN_PASSWORD` をランダム生成して標準出力に表示します。`.env` が既にある場合は上書きしません。

## 起動方法

今の主導線は `Traefik` 経由です。alias が無くても `raspberrypi.local/niwaki/` で入れる前提にして、`niwaki.local` は追加したら使う常用 URL として扱います。

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
STACK_ROOT=/opt/niwaki
MDNS_TARGET_IP=192.168.1.10
```

### 2. stack registry を編集する

stack registry は SQLite のみで保持します。
起動直後は空なので、Overview ページの `Register Stack` から stack を追加してください。
`repo_url` を入れておくと、stack 個別ページから `Clone` を実行できます。

### 3. Traefik 経由で起動する

```bash
docker compose -f compose.yaml -f compose.niwaki.yaml up -d --build
```

デフォルトでは以下で開けます。

- primary URL: `http://raspberrypi.local/niwaki/`
- alias URL: `http://niwaki.local/`

起動後の主なページは以下です。

- `Overview`: stack 一覧、最近の deploy、stack 登録
- `stacks/<id>`: stack ごとの状態、操作、logs、設定編集
- `settings`: システム共通の Git credential
- `aliases`: `mdns-admin` 互換ラベルでの mDNS alias 管理

### 4. 直接起動で確認する場合

```bash
python3 -m app.backend
```

この場合だけ `http://raspberrypi.local:8787/` や `http://<raspberry-pi-ip>:8787/` で確認できます。

### 5. ローカルで Docker 起動する場合

ローカル開発では `Traefik` と mDNS を切って、`http://localhost:8787/` に直接出すのが一番簡単です。
`STACK_ROOT` は host 側の絶対パスで渡してください。`Niwaki` は host Docker socket を使うので、container 内でも同じ絶対パスを見せる必要があります。

登録したい stack の `cwd` は `STACK_ROOT` 配下である必要があります。

この repo 自体を stack として登録したい場合:

```bash
STACK_ROOT="$PWD" docker compose -f compose.niwaki.yaml -f compose.local.yaml up -d --build
```

`stacks/` 配下だけを管理対象にしたい場合:

```bash
mkdir -p "$PWD/stacks"
STACK_ROOT="$PWD/stacks" docker compose -f compose.niwaki.yaml -f compose.local.yaml up -d --build
```

アクセス先:

- `http://localhost:8787/`

停止:

```bash
STACK_ROOT="$PWD" docker compose -f compose.niwaki.yaml -f compose.local.yaml down
```

または:

```bash
STACK_ROOT="$PWD/stacks" docker compose -f compose.niwaki.yaml -f compose.local.yaml down
```

## UI スタイルの更新方法

フロントエンドの CSS は `tailwindcss@3.4.4` と `daisyui@4.12.24` を pinned して生成します。

```bash
npm install
npm run build:css
```

## Git credential について

Git credential は `SETTINGS_DB_PATH` の SQLite に 1 組だけ保存し、`git clone` / `git fetch` / `git pull --ff-only` 実行時にだけ `GIT_ASKPASS` 経由で注入します。
command log や UI 一覧には password / token 自体は出しません。

## Deploy history について

deploy history も `SETTINGS_DB_PATH` の SQLite に保存します。
以前の `AUDIT_LOG_PATH` の JSON Lines は、初回起動時に DB が空なら自動で取り込みます。

## Compose 構成

Traefik 単体:

```bash
docker compose up -d
```

Traefik と Niwaki:

```bash
docker compose -f compose.yaml -f compose.niwaki.yaml up -d --build
```

通常の mDNS 管理は `Niwaki` の `aliases` ページで行います。
Niwaki 側の mDNS 管理は、以前の `mdns-admin` と同じラベル規約を使っています。

## 今後の前提

- Git が正本
- stack registry で明示した Compose だけを操作
- `Portainer` の内部作業ディレクトリには依存しない
- `raspberrypi.local/niwaki/` を alias 不要の primary 導線として持つ
- `niwaki.local` は追加後の常用 URL として扱う
- `raspberrypi.local:8787` は compose の標準導線ではなく、必要時の直接確認用に留める
