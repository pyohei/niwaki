# 初期設定メモ

## 推奨する導線

### 1. 直接アクセス
- `http://raspberrypi.local:8787/`
- `http://<raspberry-pi-ip>:8787/`

これはこの repo の標準導線として持つ。

### 2. reverse proxy 配下の URL
- `https://your-proxy.example/niwaki/`

これは外部の reverse proxy で別途提供する導線で、この repo の責務には含めない。

### 3. mDNS alias
- `niwaki.local`

これは convenience 機能であり、単独では port を表せないので reverse proxy か別の公開手段と組み合わせる。

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
