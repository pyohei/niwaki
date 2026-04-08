# mDNS 機能メモ

## 取り込みたい考え方
`/Users/shohei/Dev/portainer/mdns-admin` から、機能そのものだけでなく設計上の良さを取り込む。

## 参考にする点
- Docker API を叩く責務が専用クラスに分かれている
- 管理対象が label で限定されている
- 入力値の normalize / validate が早い段階で行われる
- HTML テンプレートとサーバー処理が分離されている
- 「このアプリが管理する対象だけを触る」境界が明確

## 新しい deploy UI での取り込み方
- mDNS alias 管理は独立 feature とする
- 管理対象の alias container には既存の `io.mdns-admin.*` ラベルを使い、移行期間の互換性を保つ
- Docker API 呼び出しは deploy 機能と shared でも、mDNS 用の service 層を分ける
- 一覧・作成・削除の UI を stack 管理とは別タブで持つ
- 既存 alias との衝突検知や入力検証を行う
- alias が無くても deploy UI へ到達できる前提で設計する
- alias は bootstrap ではなく convenience 機能として扱う

## 到達性の考え方
- `raspberrypi.local/niwaki/` は alias 不要の primary URL
- `deploy.local` のような alias は、設定後の常用 URL
- `raspberrypi.local:PORT` は必要時だけ使う直接確認用 URL
- mDNS alias が未設定でも管理 UI は使えるべき

## 実装イメージ
- `app/backend/features/mdns/`
  - `service.py`
- `app/frontend/`
  - alias 一覧
  - alias 追加フォーム

## 境界
- この機能は Docker 上でこのアプリが作成した alias container だけを管理する
- 手動で作られた他の container までは面倒を見ない
