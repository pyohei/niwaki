# UI方針

## 方向性
UI は ECS や Portainer に近い、運用向けの管理画面を目指す。

単なるフォーム集ではなく、以下が一目で分かる構成にする。
- 何が動いているか
- 何が壊れているか
- 何を今すぐ操作できるか
- 直近で何が実行されたか

## 主要画面

### 1. Stack 一覧
- stack 名
- 現在の状態
- 稼働コンテナ数
- Git branch / commit
- 最終 deploy 時刻
- 最終 deploy の成功/失敗

### 2. Stack 詳細
- stack の基本情報
- compose file のパス
- 利用中コンテナ一覧
- 利用 network / volume
- 直近ログ
- deploy 操作
- pull / up / restart / down ボタン
- primary URL
- alias URL

### 3. 実行履歴
- 実行した操作種別
- 実行対象 stack
- 実行時刻
- 実行した command
- exit code
- output の抜粋

### 4. mDNS Alias 管理
- alias 一覧
- target IP
- state / status
- 追加
- 削除

### 5. アクセス導線の案内
- primary URL の表示
- alias URL の表示
- mDNS alias 未設定時の案内
- `raspberrypi.local` と alias の違いの説明

## UX の方針
- 状態は badge や color で即時に判別できるようにする
- destructive action には confirm を付ける
- command output は詳細画面で折りたたみ表示できるようにする
- ログは「十分便利」だが「重すぎない」範囲に留める
- ブラウザから任意シェルは実行させない
- 初回セットアップで迷わないよう、`raspberrypi.local/niwaki/` を常に見せる
