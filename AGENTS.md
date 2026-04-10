# AGENTS.md — Raspberry Pi 向け Compose デプロイ UI

## 目的
単一の Raspberry Pi / Debian 系ホスト上で動く、小さなセルフホストのデプロイ UI を作る。

このリポジトリは、ホスト上に通常のファイルとして置かれている Docker Compose スタックを、ブラウザから操作するためのものとする。
Portainer の `/data/compose/<id>` のような内部作業ディレクトリには依存せず、Git 管理された Compose ファイルを正本として扱う。
reverse proxy はこの repo の責務に含めない。

目指す方向性は以下。
- 単一ホスト専用
- Docker Compose ベース
- Git を source of truth とする
- ブラウザから deploy/update を実行できる
- 挙動が単純で、追跡しやすい

## 主要求
- Raspberry Pi OS / Debian 系ホストで動くこと
- Docker Engine と Docker Compose v2 は導入済みであること
- スタックは通常のディレクトリとしてホスト上に存在すること
  - `/opt/niwaki/stacks/portainer/compose.yaml`
  - `/opt/niwaki/stacks/homepage/compose.yaml`
  - `/opt/niwaki/stacks/gitea/compose.yaml`
- ホストの bind mount は絶対パスのみを使うこと
- Portainer 管理の内部パスに依存しないこと
- 「見えないコピー」を内部データモデルの主軸にしないこと

## 非目標
- Kubernetes や Docker Swarm の管理
- 複数ホストのオーケストレーション
- ブラウザからの任意シェル実行
- 汎用ファイルマネージャ
- 既知の Compose スタックに属さないコンテナの管理
- reverse proxy の管理
- Git を source of truth から外すこと

## 基本方針
- 1 stack = 1 directory = 1 Compose project
- Compose ファイル名は stack ごとに指定可能にする
- `compose.yaml` は標準値として扱うが、`compose.portainer.yaml` のような命名も許可する
- UI はホスト上の確定的な操作を薄く包むだけにする
- UI の見た目と操作感は ECS / Portainer に近いものを目指す
- すべての実行は明示的な working directory を持つ
- 実行した command、cwd、exit code、直近の output を表示できるようにする
- 危険な自動探索より、明示的な stack 登録を優先する
- Git や Docker から導出できる情報は、不要に DB へ複製しない
- アプリ自身の到達 URL は `APP_BASE_URL` を唯一の正本とする

## 必要な機能
stack ごとに最低限ほしい操作:
- stack の状態表示
- コンテナ一覧の表示
- 直近ログの表示
- `docker compose config` の実行
- `docker compose pull` の実行
- `docker compose up -d` の実行
- `docker compose down` の実行
- `git fetch` / `git pull --ff-only` の実行
- 最終 deploy 結果と時刻の表示

あるとよい機能:
- stack の再起動
- 現在の Git branch / 最新 commit の表示
- コマンド実行中の出力ストリーミング
- 全 stack を見渡せる readonly ダッシュボード

## 安全ルール
- UI から任意コマンドを入力させない
- 実行可能な操作は allowlist で固定する
- SQLite registry に登録された stack だけを操作対象にする
- 実行前に stack path を解決し、妥当性を検証する
- 設定された stack root の外側は拒否する
- `git pull --ff-only` を基本にして、暗黙の merge commit を避ける
- 無関係な container / network / volume を自動で壊さない
- 破壊的操作は UI 上で明示的に扱う

## 推奨リポジトリ構成
例:

```text
deploy-ui/
  AGENTS.md
  README.md
  .env.example
  app/
    backend/
      api/
      core/
      docker/
      git/
      stacks/
      auth/
      audit/
      features/
        deploys/
        logs/
        mdns/
        settings/
    frontend/
  docs/
    operations.md
    ui.md
    mdns.md
```

ホスト側の stack 構成例:

```text
/opt/niwaki/stacks/
  portainer/
    compose.yaml
  homepage/
    compose.yaml
  gitea/
    compose.yaml
```

## Stack Registry
ディスク全体を雑に走査するのではなく、SQLite に保持した明示的な stack registry を使う。

ルール:
- `cwd` は絶対パス
- `compose_file` は stack ごとに明示する
- `compose.yaml` はデフォルト値として扱う
- 1 stack に複数 compose ファイルを持たせる場合でも、UI が扱う対象は registry で明示する
- stack の追加・更新・削除は Web UI から行う

## UI 要件
UI は Portainer や ECS に近い管理画面として設計する。

最低限ほしい画面:
- stack 一覧
- stack 詳細
- deploy 実行ダイアログ
- ログ表示
- 実行履歴
- mDNS alias 管理

一覧画面で見たい情報:
- stack 名
- 稼働状態
- Git branch / commit
- 最終 deploy 時刻
- 現在のコンテナ数
- health / degraded の表示

詳細画面で見たい情報:
- stack の概要
- 実行中コンテナ一覧
- compose file の場所
- 利用 network / volume
- 直近ログ
- 最後に実行した command と結果
- `pull`, `up -d`, `restart`, `down` などの操作ボタン
- stack ごとの補助 URL

## アクセス導線
このアプリ自身の標準導線は direct access とする。

- 標準導線: `http://raspberrypi.local:8787/`
- 補助導線: `http://<raspberry-pi-ip>:8787/`
- 外部公開 URL: 必要なら別の reverse proxy で作る

考え方:
- Niwaki は単体で到達可能にする
- reverse proxy が無くても管理 UI に入れること
- `APP_BASE_URL` は実際にユーザーが開く URL に合わせて設定する
- `APP_BASE_PATH` は外部 proxy が path prefix を付ける場合だけ使う

## mdns-admin から取り込みたい設計
旧 `mdns-admin` 実装から、以下の性質を引き継ぐ。

- 管理対象をラベルで限定する設計
- Docker API を叩く処理を専用クラスへ分離する設計
- 入力値の normalize / validate を先に行う設計
- HTML/API とバックエンド処理を分ける設計
- 「このアプリが作ったものだけを管理する」境界を明確にする設計

今回の deploy UI では、これを以下に読み替える。

- stack 管理対象は registry で境界を持つ
- Docker 操作は `docker/` モジュールに閉じ込める
- Git 操作は `git/` モジュールに閉じ込める
- feature 単位の API ハンドラを `features/` 配下に分ける
- mDNS alias 管理機能は独立 feature として組み込めるようにする
- 既存の `io.mdns-admin.*` ラベルとも互換性を持つ

## 実装方針
- 小さな backend から `git` と `docker compose` を叩く構成を優先する
- Compose のロジックを再実装するより、server-side の command wrapper を使う
- stack 登録は SQLite registry を正本にする
- ユーザー管理を大きく作り込まず、LAN 内向けの単一管理者認証を優先する
- frontend は薄く保ち、ダッシュボードの肥大化を避ける
- ログと失敗理由を追いやすくする
- 気の利いた抽象化より、地味でも壊れにくいホスト操作を選ぶ
- ただし実装ファイルは 1 箇所に寄せず、責務ごとに分割する
- mDNS 管理は deploy UI のサブ機能として自然に追加できる構成にする

## 想定コマンドモデル
stack が `cwd=/opt/niwaki/stacks/homepage`、`compose_file=compose.homepage.yaml` の場合:

```bash
git -C /opt/niwaki/stacks/homepage fetch --prune
git -C /opt/niwaki/stacks/homepage pull --ff-only
docker compose -f compose.homepage.yaml config
docker compose -f compose.homepage.yaml pull
docker compose -f compose.homepage.yaml up -d
docker compose -f compose.homepage.yaml ps
docker compose -f compose.homepage.yaml logs --tail=200
```

Docker Compose の実行は、必ず stack directory を cwd にして行うこと。

## UI の期待
UI では以下を簡単にしたい。
- 登録済み stack を一覧できる
- 各 stack が healthy か degraded かを把握できる
- ある stack だけを deploy できる
- 失敗時に command output を追える
- いま何の Git revision が入っているかを分かるようにする
- mDNS alias の追加・削除・一覧確認ができる
- 現在の primary URL を確認できる

逆に、以下は優先しない。
- マルチテナント運用
- plugin ecosystem
- marketplace / template 中心の運用
- Compose ファイルから切り離された抽象的なコンテナ管理

## 出力に関する期待
このリポジトリで変更を加える場合:
- 単一ホスト向け Compose deploy tool という軸を崩さない
- ファイル構成と設定は単純に保つ
- host setup と運用手順の文書を含める
- 隠れた state を導入する場合は明記する
- reverse proxy を内包前提に戻さない

## 補足
- stack ファイルの正本は Git
- Docker の実行時情報は動的に取得する
- ゴールは「ブラウザから便利に使えること」であり、「内部実装が魔法になること」ではない
