# Garmin 自動取得パイプライン（スマホ完結セットアップ）

ブラウザ版 Garmin Connect の人間確認（Cloudflare）を回避するため、
**トークン認証（パスワード不要・ブラウザ不要）** で毎日自動取得する仕組み。

- 初回だけ: Google Colab でトークンを発行
- 毎日: GitHub Actions が 06:00 JST に `data/garmin_data.json` を自動更新
- 取得内容: ランニングのアクティビティ（サマリー＋ラップ別集計）と、
  日ごとの睡眠・HRV・トレーニングレディネス・安静時心拍など
- **GPSトラック（位置情報の軌跡）は出力しない**（ダッシュボードに必要な集計値のみ）

## 同梱ファイル

| ファイル | 置き場所（GitHubリポジトリ内） |
|---|---|
| `garmin_sync.py` | リポジトリ直下 |
| `requirements.txt` | リポジトリ直下 |
| `.github/workflows/garmin-sync.yml` | `.github/workflows/` の中 |
| `colab_token_setup.txt` | GitHubには置かない（Colabに貼る用） |

## 手順（全部スマホのブラウザでOK）

### 1. Colab でトークンを発行（初回のみ）
1. Google Colab を開き「ノートブックを新規作成」
2. `colab_token_setup.txt` の中身を全部コピーしてコードセルに貼り、▶ を押す
3. Garmin のメール・パスワード（＋2段階認証コード）を入力欄に入力
4. 出力された長い Base64 文字列をすべてコピーして控える（タブは閉じてよい）

### 2. GitHub にリポジトリを作ってファイルを置く
1. GitHub で新規リポジトリを作成（公開/非公開は下の「公開か非公開か」参照）
2. 「Add file → Upload files」で `garmin_sync.py` と `requirements.txt` をアップロード
3. ワークフローは「Create new file」でファイル名に
   `.github/workflows/garmin-sync.yml` と直接入力し、ファイルの中身を貼って保存

### 3. Secret を登録して手動実行でテスト
1. Settings → Secrets and variables → Actions → New repository secret
   - Name: `GARMIN_TOKENS_B64`
   - Secret: 手順1の Base64 文字列
2. Actions タブ →「Garmin Connect Daily Sync」→「Run workflow」
3. 緑のチェックが付けば成功。以後は毎朝 06:00 JST に自動更新される

## 公開か非公開か

- **Public**: `data/garmin_data.json` の Raw URL を Muse が直接読めるので、
  ダッシュボードへの反映まで完全自動化できる。ただし JSON は誰でも見られる
  （GPS軌跡は入っていないが、心拍・睡眠などの健康データは含まれる）
- **Private**: 中身は守られるが、Muse が自動で読めない。
  反映したいときに `garmin_data.json` をダウンロードして渡す運用になる

## メンテナンス

- トークンには寿命がある。Actions が認証エラーで失敗し始めたら、
  手順1（Colab）をもう一度やって Secret を貼り直せば復旧する
- 取得範囲は直近14日分（前回失敗しても翌日以降に拾い直せる）
