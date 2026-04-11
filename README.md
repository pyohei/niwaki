# Niwaki

Niwaki は、単一ホストの Docker Compose スタックをブラウザから管理するための小さなデプロイ UI です。
Git 管理された Compose ファイルを source of truth とし、stack ごとの詳細ページ、deploy、logs、mDNS alias 管理を扱います。

このリポジトリは `Niwaki` 本体だけを持ちます。
reverse proxy はこの repo の責務に含めず、必要なら別の構成でカバーします。
`Niwaki` は mDNS alias UI と publisher 機能を内包しているため、別の `mdns-admin` compose は不要です。

主な構成:

- `compose.yaml`: Niwaki を standalone で起動する compose
- `app/`: Niwaki 本体
- `docs/`: UI / 運用 / mDNS の設計メモ

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
└── compose.yaml
```

## クイックセットアップ

Raspberry Pi OS / Debian / Ubuntu 系であれば、`install.sh` をそのまま流してセットアップできます。
このスクリプトは Git、Docker、`avahi-daemon`、`dbus` を入れて、`https://github.com/pyohei/niwaki` を clone し、`.env` を初回生成してから `Niwaki` を起動します。

```bash
curl -fsSL https://raw.githubusercontent.com/pyohei/niwaki/main/install.sh | bash
```

デフォルトの clone 先は `~/niwaki` です。変えたい場合は、実行時に `NIWAKI_INSTALL_DIR` を渡してください。

```bash
curl -fsSL https://raw.githubusercontent.com/pyohei/niwaki/main/install.sh | NIWAKI_INSTALL_DIR=/opt/niwaki bash
```

初回起動時は `ADMIN_PASSWORD` をランダム生成して標準出力に表示します。`.env` が既にある場合は上書きしません。

## 起動方法

標準の導線は `Niwaki` の直公開です。デフォルトでは `http://raspberrypi.local:8787/` に出します。
別の reverse proxy を前段に置く場合は、この repo ではなく外側で受けて、`APP_BASE_URL` と `APP_BASE_PATH` を実際の公開 URL に合わせて調整します。

### 1. 設定ファイルを用意する

```bash
cp .env.example .env
```

`.env` の例:

```env
APP_HOST=0.0.0.0
APP_PORT=8787
APP_BASE_URL=http://raspberrypi.local:8787/
APP_BASE_PATH=
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
`ID` は `Name` から自動生成します。
`CWD` は `STACK_ROOT` 配下に自動で決まり、標準では `stacks/<id>` になります。
`Override File` も自動で決まり、標準では `overrides/<id>.yaml` を使います。
保存時に override file が無ければ、Niwaki が雛形を自動作成します。
実行時は `docker compose -f <compose_file> -f <override_file>` で重ねるので、`ports:` の衝突回避や環境別の追加設定はこの override file に寄せます。

### 3. compose で起動する

```bash
docker compose up -d --build
```

デフォルトでは以下で開けます。

- primary URL: `http://raspberrypi.local:8787/`
- direct URL: `http://<raspberry-pi-ip>:8787/`

起動後の主なページは以下です。

- `Overview`: stack 一覧、最近の deploy、stack 登録
- `stacks/<id>`: stack ごとの状態、操作、logs、設定編集
- `settings`: システム共通の Git credential
- `aliases`: `mdns-admin` 互換ラベルでの mDNS alias 管理

### 4. reverse proxy 配下で使う場合

この repo 自体は reverse proxy を持ちません。
別の reverse proxy から公開する場合は、少なくとも以下を合わせてください。

- `APP_BASE_URL`
- `APP_BASE_PATH`

例:

```env
APP_BASE_URL=https://niwaki.example.local/tools/niwaki/
APP_BASE_PATH=/tools/niwaki
```

### 5. 直接起動で確認する場合

```bash
python3 -m app.backend
```

この場合だけ `http://raspberrypi.local:8787/` や `http://<raspberry-pi-ip>:8787/` で確認できます。

### 6. ローカルで Docker 起動する場合

ローカル開発では `http://localhost:8787/` に直接出すのが一番簡単です。
`STACK_ROOT` は host 側の絶対パスで渡してください。`Niwaki` は host Docker socket を使うので、container 内でも同じ絶対パスを見せる必要があります。

登録したい stack の `cwd` は `STACK_ROOT` 配下である必要があります。

この repo 自体を stack として登録したい場合:

```bash
APP_BASE_URL="http://localhost:8787/" STACK_ROOT="$PWD" docker compose up -d --build
```

`stacks/` 配下だけを管理対象にしたい場合:

```bash
mkdir -p "$PWD/stacks"
APP_BASE_URL="http://localhost:8787/" STACK_ROOT="$PWD/stacks" docker compose up -d --build
```

アクセス先:

- `http://localhost:8787/`

停止:

```bash
STACK_ROOT="$PWD" docker compose down
```

または:

```bash
STACK_ROOT="$PWD/stacks" docker compose down
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

通常の mDNS 管理は `Niwaki` の `aliases` ページで行います。
Niwaki 側の mDNS 管理は、以前の `mdns-admin` と同じラベル規約を使っています。

## 今後の前提

- Git が正本
- stack registry で明示した Compose だけを操作
- `Portainer` の内部作業ディレクトリには依存しない
- 標準導線は `raspberrypi.local:8787`
- reverse proxy は repo 外の責務
- 必要なら `APP_BASE_URL` / `APP_BASE_PATH` で外部 URL に合わせる
