# 初期設定メモ

## 推奨する最初の導線

### 1. Traefik primary
- `http://raspberrypi.local/niwaki/`

これは alias が無くても使える標準導線として持つ。

### 2. Traefik alias
- `http://deploy.local/`

これは普段使いの導線として使う。

### 3. 直接アクセス
- `http://raspberrypi.local:8787`
- `http://<raspberry-pi-ip>:8787`

これは必要なときだけ使う確認用導線とする。通常の compose 起動では前提にしない。

## 認証の初期案
- 単一管理者アカウントのみ
- username / password もしくは password hash を `.env` で持つ
- 初期実装では HTTP Basic 認証を使う

## Stack registry の初期案
- SQLite registry に明示的に定義する
- stack ごとに `cwd` と `compose_file` を持つ
- ディスク全体の自動探索はしない

## 失敗時の表示
deploy は以下の段階に分けて表示する。

1. `git fetch`
2. `git pull --ff-only`
3. `docker compose config`
4. `docker compose pull`
5. `docker compose up -d`

各段階に対して、以下を持つ。
- state
- command
- exit code
- output

また、以下は分けて保持する。
- 最後に成功した deploy
- 最後に試した deploy
