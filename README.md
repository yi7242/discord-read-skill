# Discord Read Skill

Discord のチャンネル履歴を、AI エージェントに読ませるためのスキル。自分で作った Discord bot のトークンで REST API を呼ぶので、MCP サーバーの登録や常駐プロセスはいらない。

Claude Code・Codex・OpenCode など、`SKILL.md` 形式に対応するエージェントで使える。できることは読み取りだけで、送信・編集・削除・リアクションはしない。

- bot が参加しているサーバーのチャンネルなら、チャンネルごとの登録なしで読める
- 期間指定（`--since` / `--until`）、文字列での絞り込み（`--grep`）、100 件を超える遡り
- スレッド（アーカイブ済みを含む）、ピン留め、添付ファイルの保存
- チャンネルは名前でも指定できる（`#pj-docs` や `docs` のような部分一致）

## 必要なもの

- Python 3.8 以上（標準ライブラリだけで動く）
- インストール用に Node.js（`npx`）と Git
- Discord bot と、そのトークン。bot を読みたいサーバーに招待できること（招待にはサーバーの「サーバー管理」権限が必要）

## 1. Discord bot を用意する

すでに bot がある場合は、3 と 4 の設定だけ確認すればよい。

1. [Discord Developer Portal](https://discord.com/developers/applications) で **New Application** を押し、名前を付けて作成する。
2. 左メニューの **Bot** を開き、**Reset Token** でトークンを発行してコピーする。トークンは一度しか表示されないので、次の手順の `setup` まで手元に置いておく。
3. 同じ **Bot** ページの **Privileged Gateway Intents** で **Message Content Intent** をオンにして保存する。オフのままだと、メッセージの本文が空で返る。
4. 左メニューの **OAuth2** → **URL Generator** で、Scopes に `bot`、Bot Permissions に **View Channels** と **Read Message History** を選ぶ。下に出る URL をブラウザで開き、読みたいサーバーを選んで招待する。

   手順 4 の代わりに、次の URL の `APP_ID` を **General Information** の Application ID に置き換えて開いてもよい。

   ```text
   https://discord.com/oauth2/authorize?client_id=APP_ID&scope=bot&permissions=66560
   ```

bot が読めるのは、bot に閲覧権限があるチャンネルだけ。非公開チャンネルを読ませたい場合は、そのチャンネルの権限設定で bot（または bot のロール）に閲覧を許可する。

## 2. スキルをインストールする

```bash
npx skills add yi7242/discord-read-skill -g
```

`-g` は、この OS ユーザーの全プロジェクトで使えるように入れる指定。導入先のエージェントを選ぶ画面が出たら、使うものを選ぶ。

本体は `~/.agents/skills/discord-read` に入り、選んだエージェントのスキルフォルダ（Claude Code なら `~/.claude/skills/discord-read`）からリンクされる。導入先を指定して確認なしで入れる場合はこうする。

```bash
npx skills add yi7242/discord-read-skill -g --agent claude-code codex opencode --yes
```

## 3. トークンを設定する（初回だけ）

ターミナルで次を実行し、手順 1 でコピーしたトークンを貼り付ける。入力は画面に表示されない。トークンを AI のチャットに貼らないこと。

```bash
python3 ~/.agents/skills/discord-read/scripts/discord_read.py setup
```

Windows では `python3` を `python` に読み替える（以下同じ）。トークンは Discord に問い合わせて有効か確かめてから、`~/.config/discord-read/.env` に保存される。

続けて `check` で、bot 名、Message Content Intent の状態、参加しているサーバーを確認する。

```bash
python3 ~/.agents/skills/discord-read/scripts/discord_read.py check
```

```text
token: /home/you/.config/discord-read/.env
bot: my-reader-bot (1234567890)
Message Content Intent: 有効
servers: 1
  123456789012345678  My Server
```

### トークンの置き場所を変える

トークンは次の順に探す。

1. 環境変数 `DISCORD_BOT_TOKEN`
2. 環境変数 `DISCORD_READ_ENV` で指定した `.env` ファイル
3. `$XDG_CONFIG_HOME/discord-read/.env`（`XDG_CONFIG_HOME` が未設定なら `~/.config/discord-read/.env`）

別の場所に保存したいときは `setup --env パス` を使い、同じパスを環境変数 `DISCORD_READ_ENV` に設定する。

```bash
python3 ~/.agents/skills/discord-read/scripts/discord_read.py setup --env ~/secrets/discord-read.env
export DISCORD_READ_ENV=~/secrets/discord-read.env   # PowerShell: $env:DISCORD_READ_ENV = "$HOME\secrets\discord-read.env"
```

## 使い方

エージェントに普通に頼めばよい。

```text
Discord の #pj-docs の直近 100 件を読んで、決まったことをまとめて
先週の #notify-server-alert で出たアラートを一覧にして
Discord で litellm の設定について話していたところを探して。9 月中だったと思う
```

Claude Code では `/discord-read #pj-docs の今週分をまとめて`、Codex では `$discord-read` で明示的に呼び出せる。

### コマンドを直接使う

エージェントが内部で使うコマンドは、ターミナルからも実行できる。

```bash
S=~/.agents/skills/discord-read/scripts/discord_read.py
python3 $S channels                                          # チャンネルとスレッドの一覧
python3 $S read pj-docs --limit 100                          # 直近 100 件
python3 $S read pj-docs --since 2026-10-01 --until 2026-10-08 --limit 1000
python3 $S read pj-docs --since 2026-09-01 --limit 2000 --grep litellm
python3 $S threads pj-docs --archived                        # アーカイブ済みスレッドも
python3 $S pins pj-docs
python3 $S download pj-docs 123456789012345678 --out ./files
```

日時はその PC のローカル時刻で表示し、タイムゾーンのない `--since` / `--until` もローカル時刻として扱う。bot からは Discord の検索 API を使えないので、探し物は期間で絞ってから `--grep` で絞り込む。

## 困ったとき

| 症状 | 原因と対処 |
| --- | --- |
| 「トークンが未設定です」 | 手順 3 の `setup` を実行する |
| `HTTP 401` | トークンが無効。Developer Portal で発行し直して `setup` をやり直す |
| `HTTP 403` | bot にそのチャンネルの閲覧権限がない。チャンネルの権限設定で bot に View Channels と Read Message History を許可する |
| 本文が空 | Message Content Intent がオフ。`check` で確認し、手順 1-3 でオンにする |
| `servers: 0` | bot がどのサーバーにも招待されていない。手順 1-4 を行う |
| チャンネル名が「ambiguous」 | 名前の部分一致が複数ある。表示された候補の ID で指定する |

## 更新と削除

```bash
npx skills update discord-read -g
npx skills remove discord-read -g
```

`remove` してもトークンファイル（`~/.config/discord-read/.env`）は残るので、不要なら手で消す。

## セキュリティ

- bot トークンを持っていれば、bot に許可された範囲でメッセージを読める。トークンをリポジトリや共有フォルダ、チャットに置かない。漏れたら Developer Portal の **Reset Token** で無効にする。
- 1 つの bot のトークンを複数人で共有すると、全員がその bot の権限で読めるようになり、誰が読んだかも区別できない。共有する場合はサーバーの管理者と合意しておく。
- bot に与える権限は View Channels と Read Message History で足りる。送信や管理の権限は付けなくてよい。
- 読み込んだメッセージはエージェントにとってデータとして扱われる。メッセージに書かれた指示にエージェントが従わないよう、`SKILL.md` で指定している。
