"""Discord のメッセージを bot トークンで読むだけのツール（送信・編集・削除はしない）。

Python 3.8 以上の標準ライブラリだけで動く。bot が参加していて閲覧権限のあるチャンネルを読める。

トークンは次の順で探す。
  1. 環境変数 DISCORD_BOT_TOKEN
  2. 環境変数 DISCORD_READ_ENV で指定した .env ファイル
  3. $XDG_CONFIG_HOME/discord-read/.env（未設定なら ~/.config/discord-read/.env）
初回は `setup` でトークンを入力して保存する（入力は画面に表示されない）。

  python -I discord_read.py setup [--env PATH]
  python -I discord_read.py check
  python -I discord_read.py guilds
  python -I discord_read.py channels [--guild ID]
  python -I discord_read.py threads CHANNEL [--archived]
  python -I discord_read.py read CHANNEL [--limit N] [--since DATE] [--until DATE]
                                        [--before MSGID] [--after MSGID] [--grep TEXT]
  python -I discord_read.py message CHANNEL MSGID
  python -I discord_read.py pins CHANNEL
  python -I discord_read.py download CHANNEL MSGID [--out DIR]

CHANNEL はチャンネルID、または名前（先頭の # は省略可、部分一致が1件だけならそれ）。
DATE は 2026-10-01 や 2026-10-01T09:00 の形式。日時の表示とタイムゾーン未指定の DATE は
この PC のローカル時刻で扱う。
"""
import argparse
import getpass
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

API = "https://discord.com/api/v10"
USER_AGENT = "discord-read-skill (https://github.com/yi7242/discord-read-skill, 1.0)"
LOCAL_TZ = datetime.now().astimezone().tzinfo
DISCORD_EPOCH_MS = 1420070400000
TEXTLIKE = {0, 2, 5, 13, 15, 16}  # text, voice, announcement, stage, forum, media
THREAD_TYPES = {10, 11, 12}
TYPE_NAMES = {0: "text", 2: "voice", 5: "news", 13: "stage", 15: "forum", 16: "media",
              10: "thread", 11: "thread", 12: "private-thread", 4: "category"}
# Application flags: GATEWAY_MESSAGE_CONTENT / GATEWAY_MESSAGE_CONTENT_LIMITED
MESSAGE_CONTENT_FLAGS = (1 << 18) | (1 << 19)

SETUP_HINT = ("トークンが未設定です。ユーザー本人がターミナルで次を実行してください"
              "（トークンをチャットに貼らないこと）:\n  python {script} setup")


def default_env_file():
    if os.environ.get("DISCORD_READ_ENV"):
        return Path(os.environ["DISCORD_READ_ENV"]).expanduser()
    base = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(base) / "discord-read" / ".env"


def read_env_token(path):
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("DISCORD_BOT_TOKEN="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def load_token():
    tok = os.environ.get("DISCORD_BOT_TOKEN") or read_env_token(default_env_file())
    if not tok:
        sys.exit(SETUP_HINT.format(script=Path(__file__).resolve()))
    return tok.strip()


TOKEN = None


class ApiError(Exception):
    def __init__(self, code, path, body):
        super().__init__(f"HTTP {code} {path}: {body}")
        self.code = code


def api(path, params=None, token=None):
    url = API + path
    if params:
        url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bot {token or TOKEN}", "User-Agent": USER_AGENT})
    for _ in range(5):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(float(json.load(e).get("retry_after", 1)) + 0.1)
                continue
            raise ApiError(e.code, path, e.read().decode("utf-8", "replace")[:300])
    raise ApiError(429, path, "rate limited too many times")


# ---- name resolution -------------------------------------------------------

_guilds = None
_channels = None


def guilds():
    global _guilds
    if _guilds is None:
        _guilds = api("/users/@me/guilds")
    return _guilds


def all_channels():
    global _channels
    if _channels is None:
        _channels = []
        for g in guilds():
            for c in api(f"/guilds/{g['id']}/channels"):
                c["_guild"] = g["name"]
                _channels.append(c)
            try:
                threads = api(f"/guilds/{g['id']}/threads/active").get("threads", [])
            except ApiError:
                threads = []  # 権限がなければスレッドなしで続ける
            for t in threads:
                t["_guild"] = g["name"]
                _channels.append(t)
    return _channels


def resolve(ch):
    if ch.isdigit():
        return ch
    name = ch.lstrip("#").lower()
    cands = [c for c in all_channels() if c["type"] in TEXTLIKE | THREAD_TYPES]
    exact = [c for c in cands if c["name"].lower() == name]
    hits = exact or [c for c in cands if name in c["name"].lower()]
    if len(hits) == 1:
        return hits[0]["id"]
    if not hits:
        sys.exit(f"no channel matches '{ch}'")
    lines = "\n".join(f"  {c['id']}  {c['_guild']} / #{c['name']}" for c in hits)
    sys.exit(f"'{ch}' is ambiguous:\n{lines}")


# ---- formatting ------------------------------------------------------------

def snowflake_from_dt(dt):
    return str((int(dt.timestamp() * 1000) - DISCORD_EPOCH_MS) << 22)


def parse_date(s):
    dt = datetime.fromisoformat(s)
    return dt if dt.tzinfo else dt.replace(tzinfo=LOCAL_TZ)


def fmt_time(iso):
    return datetime.fromisoformat(iso).astimezone(LOCAL_TZ).strftime("%Y-%m-%d %H:%M")


def fmt_msg(m):
    who = m["author"].get("global_name") or m["author"]["username"]
    if m["author"].get("bot"):
        who += " [bot]"
    text = m.get("content", "")
    for u in m.get("mentions", []):
        name = "@" + (u.get("global_name") or u["username"])
        text = text.replace(f"<@{u['id']}>", name).replace(f"<@!{u['id']}>", name)
    for e in m.get("embeds", []):
        parts = [e.get("title"), e.get("description")]
        parts += [f"{f.get('name')}: {f.get('value')}" for f in e.get("fields", [])]
        text += "\n  [embed] " + " / ".join(p for p in parts if p)
    for a in m.get("attachments", []):
        text += f"\n  [file] {a['filename']} ({a.get('size', 0)} bytes) {a['url']}"
    head = f"[{fmt_time(m['timestamp'])}] {who}"
    ref = m.get("referenced_message")
    if ref:
        rwho = ref["author"].get("global_name") or ref["author"]["username"]
        head += f" (reply to {rwho} {ref['id']})"
    if m.get("thread"):
        text += f"\n  [thread] #{m['thread']['name']} id={m['thread']['id']}"
    # 1メッセージ内の改行は字下げして、別メッセージと見分けられるようにする
    text = text.replace("\n", "\n    ")
    return f"{head}: {text}  (id: {m['id']})"


# ---- commands --------------------------------------------------------------

def cmd_guilds(a):
    for g in guilds():
        print(f"{g['id']}  {g['name']}")


def cmd_channels(a):
    byid = {c["id"]: c for c in all_channels()}
    rows = [c for c in all_channels()
            if c["type"] in TEXTLIKE | THREAD_TYPES and (not a.guild or c.get("guild_id") == a.guild)]

    def path(c):
        # カテゴリ / #チャンネル、スレッドは #親チャンネル > スレッド名
        if c["type"] in THREAD_TYPES:
            parent = byid.get(c.get("parent_id"))
            return (path(parent) if parent else "?") + f" > {c['name']}"
        cat = byid.get(c.get("parent_id"))
        return (cat["name"] + " / " if cat else "") + "#" + c["name"]

    rows.sort(key=lambda c: (c["_guild"], path(c)))
    for c in rows:
        kind = TYPE_NAMES.get(c["type"], str(c["type"]))
        print(f"{c['id']}  {c['_guild']} / {path(c)}  ({kind})")


def cmd_threads(a):
    cid = resolve(a.channel)
    rows = [t for t in all_channels() if t["type"] in THREAD_TYPES and t.get("parent_id") == cid]
    if a.archived:
        before = None
        while True:
            r = api(f"/channels/{cid}/threads/archived/public", {"limit": 100, "before": before})
            rows += r.get("threads", [])
            if not r.get("has_more") or not r.get("threads"):
                break
            before = r["threads"][-1]["thread_metadata"]["archive_timestamp"]
    for t in rows:
        meta = t.get("thread_metadata", {})
        state = "archived" if meta.get("archived") else "active"
        print(f"{t['id']}  #{t['name']}  ({state}, {t.get('message_count', '?')} msgs)")


def cmd_read(a):
    cid = resolve(a.channel)
    after = a.after or (snowflake_from_dt(parse_date(a.since)) if a.since else None)
    before = a.before or (snowflake_from_dt(parse_date(a.until)) if a.until else None)
    out = []
    if after and not a.before and not a.until:
        # 指定時点から新しい方向へ読む
        cur = after
        while len(out) < a.limit:
            batch = api(f"/channels/{cid}/messages", {"limit": 100, "after": cur})
            if not batch:
                break
            batch.sort(key=lambda m: int(m["id"]))
            out += batch
            cur = batch[-1]["id"]
        out = out[:a.limit]
    else:
        # 新しい方（または before）から古い方向へ遡る
        cur = before
        while len(out) < a.limit:
            batch = api(f"/channels/{cid}/messages", {"limit": min(100, a.limit - len(out)), "before": cur})
            if not batch:
                break
            out += batch
            cur = batch[-1]["id"]
            if after and int(cur) <= int(after):
                break
        if after:
            out = [m for m in out if int(m["id"]) > int(after)]
        out.sort(key=lambda m: int(m["id"]))
    if a.grep:
        q = a.grep.lower()
        out = [m for m in out if q in fmt_msg(m).lower()]
    for m in out:
        print(fmt_msg(m))
    print(f"-- {len(out)} messages", file=sys.stderr)


def cmd_message(a):
    print(fmt_msg(api(f"/channels/{resolve(a.channel)}/messages/{a.id}")))


def cmd_pins(a):
    for m in api(f"/channels/{resolve(a.channel)}/pins"):
        print(fmt_msg(m))


def cmd_download(a):
    m = api(f"/channels/{resolve(a.channel)}/messages/{a.id}")
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    for att in m.get("attachments", []):
        name = Path(att["filename"]).name
        dest = out / f"{a.id}_{name}"
        with urllib.request.urlopen(urllib.request.Request(
                att["url"], headers={"User-Agent": USER_AGENT})) as r:
            dest.write_bytes(r.read())
        print(dest)


def cmd_setup(a):
    path = Path(a.env).expanduser() if a.env else default_env_file()
    if a.stdin:
        tok = sys.stdin.readline().strip()
    else:
        print("Discord Developer Portal の Bot ページで発行したトークンを貼り付けて Enter（入力は表示されません）")
        tok = getpass.getpass("DISCORD_BOT_TOKEN: ").strip()
    if not tok:
        sys.exit("トークンが空です")
    try:
        me = api("/users/@me", token=tok)
    except ApiError as e:
        sys.exit(f"トークンを確認できませんでした: {e}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"DISCORD_BOT_TOKEN={tok}\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    print(f"保存しました: {path}  (bot: {me['username']})")
    if a.env and path != default_env_file():
        print(f"この場所を使うには環境変数 DISCORD_READ_ENV={path} を設定してください")
    print("続けて `check` で参加サーバーと Message Content Intent を確認できます")


def cmd_check(a):
    env = default_env_file()
    src = "環境変数 DISCORD_BOT_TOKEN" if os.environ.get("DISCORD_BOT_TOKEN") else str(env)
    print(f"token: {src}")
    me = api("/users/@me")
    print(f"bot: {me['username']} ({me['id']})")
    app = api("/applications/@me")
    ok = bool(app.get("flags", 0) & MESSAGE_CONTENT_FLAGS)
    print(f"Message Content Intent: {'有効' if ok else '無効（本文が空で返る。Developer Portal の Bot ページで有効にする）'}")
    gs = guilds()
    print(f"servers: {len(gs)}")
    for g in gs:
        print(f"  {g['id']}  {g['name']}")
    if not gs:
        print("bot がどのサーバーにも参加していません。README の招待手順を参照してください")


HTTP_HINTS = {
    401: "トークンが無効です。`setup` で設定し直してください",
    403: "bot にこのチャンネルを見る権限（View Channel / Read Message History）がありません",
    404: "チャンネルかメッセージが見つかりません。ID を確認してください",
}


def main():
    global TOKEN
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description="read-only Discord reader")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("setup", help="トークンを入力して保存する")
    s.add_argument("--env", help="保存先の .env（既定は ~/.config/discord-read/.env）")
    s.add_argument("--stdin", action="store_true", help="トークンを標準入力から読む")
    s.set_defaults(f=cmd_setup, no_token=True)
    sub.add_parser("check").set_defaults(f=cmd_check)
    sub.add_parser("guilds").set_defaults(f=cmd_guilds)
    s = sub.add_parser("channels")
    s.add_argument("--guild")
    s.set_defaults(f=cmd_channels)
    s = sub.add_parser("threads")
    s.add_argument("channel")
    s.add_argument("--archived", action="store_true")
    s.set_defaults(f=cmd_threads)
    s = sub.add_parser("read")
    s.add_argument("channel")
    s.add_argument("--limit", type=int, default=50)
    s.add_argument("--since")
    s.add_argument("--until")
    s.add_argument("--before")
    s.add_argument("--after")
    s.add_argument("--grep")
    s.set_defaults(f=cmd_read)
    s = sub.add_parser("message")
    s.add_argument("channel")
    s.add_argument("id")
    s.set_defaults(f=cmd_message)
    s = sub.add_parser("pins")
    s.add_argument("channel")
    s.set_defaults(f=cmd_pins)
    s = sub.add_parser("download")
    s.add_argument("channel")
    s.add_argument("id")
    s.add_argument("--out", default=str(Path.home() / "Downloads" / "discord"))
    s.set_defaults(f=cmd_download)
    a = p.parse_args()
    if not getattr(a, "no_token", False):
        TOKEN = load_token()
    try:
        a.f(a)
    except ApiError as e:
        hint = HTTP_HINTS.get(e.code)
        sys.exit(f"{e}\n{hint}" if hint else str(e))


if __name__ == "__main__":
    main()
