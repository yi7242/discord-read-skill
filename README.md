# Discord Read Skill

AI エージェントに Discord のチャンネル履歴を読ませるスキル。自分で用意した bot のトークンで読む。送信や削除はしない。

## 導入

1. bot を用意する（次の「bot の準備」）。
2. スキルを入れる。非公開リポジトリなので、アクセス権のある GitHub アカウントで先に `gh auth login` しておく。

   ```bash
   npx skills add yi7242/discord-read-skill -g
   ```

3. トークンを保存する。入力は画面に表示されない。トークンはチャットに貼らない。

   ```bash
   python3 ~/.agents/skills/discord-read/scripts/discord_read.py setup
   ```

4. 確認する。`Message Content Intent: 有効` と読みたいサーバー名が出れば完了。

   ```bash
   python3 ~/.agents/skills/discord-read/scripts/discord_read.py check
   ```

Python 3.8 以上、Node.js、Git が必要。Windows では `python3` を `python` に読み替える。

## bot の準備

1. [Discord Developer Portal](https://discord.com/developers/applications) で **New Application** を作る。
2. **Bot** ページで **Reset Token** を押し、トークンをコピーする。
3. 同じページで **Message Content Intent** をオンにする。オフだと本文が空で返る。
4. 次の URL の `APP_ID` を **General Information** の Application ID に置き換えて開き、サーバーに招待する。付く権限は View Channels と Read Message History だけ。

   ```text
   https://discord.com/oauth2/authorize?client_id=APP_ID&scope=bot&permissions=66560
   ```

招待にはそのサーバーの管理権限が必要。非公開チャンネルは、チャンネルの権限設定で bot に閲覧を許可する。

## 使い方

エージェントに頼む。

```text
Discord の #pj-docs の直近 100 件をまとめて
9 月の #pj-litellm で設定の話をしていたところを探して
```

Claude Code では `/discord-read`、Codex では `$discord-read` で明示的に呼べる。

## うまくいかないとき

| 表示 | 対処 |
| --- | --- |
| 「トークンが未設定です」 | `setup` を実行する |
| `HTTP 401` | トークンを発行し直して `setup` をやり直す |
| `HTTP 403` | チャンネルの権限設定で bot に閲覧を許可する |
| 本文が空 | Message Content Intent をオンにする |
| `servers: 0` | bot をサーバーに招待する |

## 補足

- トークンは `~/.config/discord-read/.env` に保存される。環境変数 `DISCORD_BOT_TOKEN`、または `.env` のパスを入れた `DISCORD_READ_ENV` でも指定できる。
- 更新は `npx skills update discord-read -g`、削除は `npx skills remove discord-read -g`。削除してもトークンのファイルは残る。
- トークンがあれば bot の権限でメッセージを読める。漏れたら Developer Portal の **Reset Token** で無効にする。
