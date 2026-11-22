"""大肥鱼的 MCP 工具箱（dafeiyu-mcp）。
给 AstrBot 用（stdio），以后也可以给 Claude / Codex 用。
工具都是只读或者只碰自己目录的，不提供执行任意命令的能力。"""
import datetime as dt
import email
import email.header
import email.utils
import imaplib
import json
import pathlib
import re
import shutil
import sqlite3
import subprocess
from zoneinfo import ZoneInfo

from mcp.server.fastmcp import FastMCP

import bili

HOME = pathlib.Path("/root/dafeiyu-mcp")
CONFIG = HOME / "config.json"          # UP 主列表、邮箱配置（含授权码，权限 600）
STATE = HOME / "state.json"            # 记录看到哪儿了（邮件 UID、推过的视频）
ASTRBOT_DB = "/root/astrbot/data/data_v4.db"
ASTRBOT_TEMP = pathlib.Path("/root/astrbot/data/temp")   # AstrBot 允许发送这里的本地文件
BERLIN = ZoneInfo("Europe/Berlin")

mcp = FastMCP("dafeiyu")


def _load(p: pathlib.Path, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def _save_state(state: dict):
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")


# ---------------- 服务器状态 ----------------
@mcp.tool()
def server_status() -> str:
    """查看云服务器的状态：运行时间、内存、磁盘、AstrBot 服务是否正常、最近的错误数。"""
    def sh(cmd):
        return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=20).stdout.strip()
    mem = sh("free -h | awk 'NR==2{print $3\"/\"$2\" 已用\"} NR==3{print \"swap \"$3\"/\"$2}'")
    disk = sh("df -h / | awk 'NR==2{print $3\"/\"$2\" (\"$5\")\"}'")
    return "\n".join([
        f"运行时间: {sh('uptime -p')}",
        f"负载: {sh('cut -d\" \" -f1-3 /proc/loadavg')}",
        f"内存: {mem}",
        f"磁盘: {disk}",
        f"AstrBot 服务: {sh('systemctl is-active astrbot')}",
        f"最近 24 小时 AstrBot 报错行数: {sh('journalctl -u astrbot --since -24h --no-pager | grep -c ERRO')}",
        f"最近一次备份: {sh('ls -t /root/backups/astrbot-*.tar.gz 2>/dev/null | head -1 | xargs -r basename')}",
    ])


# ---------------- B 站 ----------------
@mcp.tool()
def bili_search_up(name: str) -> str:
    """按名字搜索 B 站 UP 主，返回 UID（mid）和粉丝数。添加关注前先用它找到 UID。"""
    res = bili.search_up(name, 5)
    if not res:
        return "没搜到这个 UP 主"
    return "\n".join(f"{u['name']}  UID={u['mid']}  粉丝={u['fans']}  {u['sign']}" for u in res)


@mcp.tool()
def bili_follow(mid: int, name: str = "") -> str:
    """把 UP 主加入大肥鱼的关注列表（只记在本地，不登录 B 站账号）。"""
    cfg = _load(CONFIG, {})
    ups = cfg.setdefault("bili_ups", [])
    if any(u["mid"] == mid for u in ups):
        return f"{name or mid} 已经在关注列表里了"
    ups.append({"mid": mid, "name": name})
    CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")
    CONFIG.chmod(0o600)
    return f"已关注 {name or mid}，现在一共关注 {len(ups)} 个 UP 主"


@mcp.tool()
def bili_unfollow(mid: int) -> str:
    """把 UP 主从关注列表移除。"""
    cfg = _load(CONFIG, {})
    before = len(cfg.get("bili_ups", []))
    cfg["bili_ups"] = [u for u in cfg.get("bili_ups", []) if u["mid"] != mid]
    CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")
    return "已取消关注" if len(cfg["bili_ups"]) < before else "关注列表里没有这个 UID"


@mcp.tool()
def bili_updates(only_new: bool = True, hours: int = 48) -> str:
    """查看关注的 UP 主最近有没有更新视频。only_new=True 时只返回上次查看之后的新视频（推送用）。"""
    cfg, state = _load(CONFIG, {}), _load(STATE, {})
    ups = cfg.get("bili_ups", [])
    if not ups:
        return "还没有关注任何 UP 主。可以先用 bili_search_up 搜索，再用 bili_follow 关注。"
    seen = set(state.get("bili_seen", []))
    since = dt.datetime.now().timestamp() - hours * 3600
    lines, errors = [], []
    for u in ups:
        try:
            for v in bili.latest_videos(u["mid"], 3):
                if v["created"] < since or (only_new and v["bvid"] in seen):
                    continue
                t = dt.datetime.fromtimestamp(v["created"], BERLIN).strftime("%m-%d %H:%M")
                lines.append(f"【{u.get('name') or v['up']}】{v['title']}（{v['length']}，{t}）{v['url']}")
                seen.add(v["bvid"])
        except Exception as e:
            errors.append(f"{u.get('name') or u['mid']}: {e}")
    if only_new:
        state["bili_seen"] = list(seen)[-500:]
        _save_state(state)
    out = "\n".join(lines) if lines else f"最近 {hours} 小时关注的 UP 主没有新视频。"
    if errors:
        out += "\n（部分 UP 主查询失败：" + "；".join(errors) + "）"
    return out


# ---------------- 二次元图 / 画廊 / 卡片 ----------------
import cards


def _pending_images():
    metas = [p for p in (HOME / "images").glob("*.json") if not _load(p, {}).get("sent")]
    return sorted(metas, key=lambda p: p.stat().st_mtime)


def _take(n: int) -> list[dict]:
    out = []
    for p in _pending_images()[:n]:
        meta = _load(p, {})
        meta["sent"] = True
        p.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
        out.append(meta)
    return out


@mcp.tool()
def daily_gallery(count: int = 10) -> str:
    """今日画廊：把图库里 count 张二次元角色图（结月缘、琉·利昂、夏目安安等，全年龄）拼成一张大图。
    返回拼图的本地路径；请用发送消息的工具把这张图片文件发给主人，再配一两句话。"""
    metas = _take(max(1, min(count, 15)))
    if not metas:
        return "图库暂时空了（后台每 4 小时补货），今天先不发图。"
    ASTRBOT_TEMP.mkdir(parents=True, exist_ok=True)
    today = dt.datetime.now(BERLIN).strftime("%m月%d日")
    out = cards.gallery([pathlib.Path(m["file"]) for m in metas],
                        ASTRBOT_TEMP / f"dafeiyu_gallery_{dt.datetime.now():%Y%m%d%H%M%S%f}.jpg",
                        f"{today} · 大肥鱼的今日画廊（{len(metas)} 张）")
    chars = {}
    for m in metas:
        chars[m["character"]] = chars.get(m["character"], 0) + 1
    return (f"拼图文件: {out}\n角色: " + "、".join(f"{k}×{v}" for k, v in chars.items()) +
            "\n原图: " + " ".join(f"{i + 1}.{m['post']}" for i, m in enumerate(metas)))


@mcp.tool()
def gallery_images(count: int = 15) -> str:
    """今日美图时间：从图库取 count 张二次元角色图（结月缘、琉·利昂、夏目安安、魔女裁判，全年龄高分图），
    返回每张图片的本地路径和角色名。请先发一句开场白，然后用发送消息的工具把这些图片**一张一张分别**发给主人，
    可以隔几张配一句简短的话（比如点评某个角色），不要把图片拼在一起。"""
    metas = _take(max(1, min(count, 20)))
    if not metas:
        return "图库暂时空了（后台每 4 小时补货），今天先不发图。"
    ASTRBOT_TEMP.mkdir(parents=True, exist_ok=True)
    lines = []
    for i, m in enumerate(metas, 1):
        src = pathlib.Path(m["file"])
        dst = ASTRBOT_TEMP / f"dafeiyu_{src.name}"
        shutil.copy(src, dst)
        lines.append(f"{i}. 图片文件: {dst}（{m['character']}）")
    return f"今天的 {len(metas)} 张图：\n" + "\n".join(lines)


@mcp.tool()
def anime_image() -> str:
    """单独取一张二次元角色图（主人临时想要一张的时候用）。返回图片路径，请把图片文件发给主人。"""
    metas = _take(1)
    if not metas:
        return "图库暂时空了（后台每 4 小时补货）。"
    src = pathlib.Path(metas[0]["file"])
    ASTRBOT_TEMP.mkdir(parents=True, exist_ok=True)
    dst = ASTRBOT_TEMP / f"dafeiyu_{src.name}"
    shutil.copy(src, dst)
    return f"图片文件: {dst}\n角色: {metas[0]['character']}\n原图: {metas[0]['post']}"


@mcp.tool()
def render_card(title: str, body: str) -> str:
    """把文字排版成一张好看的图片卡片（用于昨日小结、服务器日报等，让主人看图就懂）。
    body 写法：以「## 」开头的行是小标题；普通行是正文；
    写成「内存: 786/1700」或「磁盘: 18%」这种格式的行会画成进度条。不要用 emoji（字体不支持）。
    返回图片路径，请用发送消息的工具把图片文件发给主人。"""
    ASTRBOT_TEMP.mkdir(parents=True, exist_ok=True)
    clean = lambda s: "".join(ch for ch in s if ord(ch) < 0x10000)
    out = cards.card(clean(title), clean(body),
                     ASTRBOT_TEMP / f"dafeiyu_card_{dt.datetime.now():%Y%m%d%H%M%S%f}.png")
    return f"卡片图片: {out}"


@mcp.tool()
def server_metrics() -> str:
    """服务器关键指标（数字版，适合直接放进 render_card 画成进度条）。"""
    def sh(cmd):
        return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=20).stdout.strip()
    mem = sh("free -m | awk 'NR==2{print $3\"/\"$2} NR==3{print $3\"/\"$2}'").split("\n")
    disk = sh("df -BG / | awk 'NR==2{gsub(\"G\",\"\"); print $3\"/\"$2}'")
    load = sh("cut -d' ' -f1 /proc/loadavg")
    return "\n".join([
        f"内存(MB): {mem[0]}", f"Swap(MB): {mem[1] if len(mem) > 1 else '0/0'}",
        f"磁盘(GB): {disk}", f"CPU负载: {float(load or 0) * 50:.0f}%",
        f"运行时间: {sh('uptime -p')}", f"AstrBot: {sh('systemctl is-active astrbot')}",
        f"24h报错行数: {sh('journalctl -u astrbot --since -24h --no-pager | grep -c ERRO')}",
        f"图库存货: {len(_pending_images())} 张",
        f"最近备份: {sh('ls -t /root/backups/astrbot-*.tar.gz 2>/dev/null | head -1 | xargs -r basename')}",
    ])


# ---------------- 聊天记录（每日总结用） ----------------
def _texts(content) -> str:
    if isinstance(content, str):
        return content
    return " ".join(c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text")


@mcp.tool()
def chat_history(date: str = "yesterday") -> str:
    """读取主人在 QQ 上和大肥鱼某一天的聊天记录（德国日期），用来写每日总结。
    date 可以是 yesterday、today 或 2026-11-21 这样的日期。"""
    today = dt.datetime.now(BERLIN).date()
    day = {"yesterday": today - dt.timedelta(days=1), "today": today}.get(date) \
        or dt.date.fromisoformat(date)
    con = sqlite3.connect(f"file:{ASTRBOT_DB}?mode=ro", uri=True)
    rows = con.execute("select content from conversations where platform_id != 'webchat'").fetchall()
    con.close()
    lines, current, cnt = [], None, 0
    for (raw,) in rows:
        for m in json.loads(raw or "[]"):
            text = _texts(m.get("content", ""))
            stamp = re.search(r"Current datetime: (\d{4}-\d{2}-\d{2} \d{2}:\d{2}) \((\w+)\)", text)
            if m.get("role") == "user" and stamp:
                tz = ZoneInfo("Asia/Shanghai") if stamp.group(2) == "CST" else BERLIN
                current = dt.datetime.strptime(stamp.group(1), "%Y-%m-%d %H:%M").replace(tzinfo=tz).astimezone(BERLIN)
            if not current or (current - dt.timedelta(hours=5)).date() != day or m.get("role") not in ("user", "assistant"):
                continue
            clean = re.sub(r"<system_reminder>.*?</system_reminder>", "", text, flags=re.S).strip()
            if clean:
                who = "主人" if m["role"] == "user" else "大肥鱼"
                lines.append(f"[{current:%H:%M}] {who}: {clean[:300]}")
                cnt += m["role"] == "user"
    if not lines:
        return f"{day} 主人没有和大肥鱼聊天。"
    return f"{day}（德国时间）共 {cnt} 条主人的消息：\n" + "\n".join(lines[-150:])


# ---------------- 每日日报（图） ----------------
import report


def _day_messages(day: dt.date) -> list[tuple[dt.datetime, str, str]]:
    """某天（德国日期）的 (时间, user/assistant, 文本) 列表。"""
    con = sqlite3.connect(f"file:{ASTRBOT_DB}?mode=ro", uri=True)
    rows = con.execute("select content from conversations where platform_id != 'webchat'").fetchall()
    con.close()
    out, current = [], None
    for (raw,) in rows:
        for m in json.loads(raw or "[]"):
            text = _texts(m.get("content", ""))
            stamp = re.search(r"Current datetime: (\d{4}-\d{2}-\d{2} \d{2}:\d{2}) \((\w+)\)", text)
            if m.get("role") == "user" and stamp:
                tz = ZoneInfo("Asia/Shanghai") if stamp.group(2) == "CST" else BERLIN
                current = dt.datetime.strptime(stamp.group(1), "%Y-%m-%d %H:%M").replace(tzinfo=tz).astimezone(BERLIN)
            logical = (current - dt.timedelta(hours=5)).date() if current else None   # 凌晨 5 点前算前一天
            if current and logical == day and m.get("role") in ("user", "assistant"):
                out.append((current, m["role"], re.sub(r"<system_reminder>.*?</system_reminder>", "", text, flags=re.S).strip()))
    return out


def _parse_day(date: str) -> dt.date:
    today = dt.datetime.now(BERLIN).date()
    return {"yesterday": today - dt.timedelta(days=1), "today": today}.get(date) or dt.date.fromisoformat(date)


@mcp.tool()
def daily_report(date: str = "yesterday", headline: str = "", done: str = "", learned: str = "",
                 chatted: str = "", mood: str = "", comment: str = "") -> str:
    """生成一张生动的「大肥鱼日报」长图。统计数据（消息数、最早/最晚、24 小时分布、高峰时段）和服务器状态由工具自动算，
    你只需要先用 chat_history 看完那天的聊天，再填这些文字（每个字段 1～4 行，多行用换行分开，不要用 emoji）：
    headline 一句话标题（比如「熬夜改 bot 的一天」）；done 今天做了什么；learned 学到了什么；
    chatted 聊了哪些有意思的话题；mood 主人的心情/状态；comment 大肥鱼的点评或叮嘱。
    返回图片路径，请用发送消息的工具把图片文件发给主人。"""
    day = _parse_day(date)
    msgs = _day_messages(day)
    user_msgs = [m for m in msgs if m[1] == "user"]
    hours = [0] * 24
    for t, _, _ in user_msgs:
        hours[t.hour] += 1
    # 夜猫子判定：凌晨 0-5 点算前一天的「最晚」
    late = [t for t, _, _ in user_msgs if t.hour < 5]
    last = max(late or [t for t, _, _ in user_msgs], default=None)
    first = min((t for t, _, _ in user_msgs if t.hour >= 5), default=None) or min((t for t, _, _ in user_msgs), default=None)
    stats = {"消息": len(user_msgs), "最早": first.strftime("%H:%M") if first else "--",
             "最晚": last.strftime("%H:%M") if last else "--",
             "字数": sum(len(x[2]) for x in user_msgs)}

    def sh(cmd):
        return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=20).stdout.strip()
    mem = [int(x) for x in sh("free -m | awk 'NR==2{print $3\" \"$2}'").split()]
    disk = [int(x) for x in sh("df -BG / | awk 'NR==2{gsub(\"G\",\"\"); print $3\" \"$2}'").split()]
    load = float(sh("cut -d' ' -f1 /proc/loadavg") or 0) / 2
    server = {"status": f"AstrBot {sh('systemctl is-active astrbot')}",
              "bars": [("内存", mem[0] / mem[1]), ("磁盘", disk[0] / disk[1]), ("CPU", min(load, 1.0))]}
    clean = lambda s: "".join(ch for ch in (s or "") if ord(ch) < 0x10000)
    sections = [(k, t, clean(v)) for k, t, v in [
        ("done", "今天做了什么", done), ("learned", "学到了什么", learned),
        ("chatted", "聊了些什么", chatted), ("mood", "主人的状态", mood),
        ("comment", "大肥鱼想说", comment)] if v and v.strip()]
    weekday = "一二三四五六日"[day.weekday()]
    ASTRBOT_TEMP.mkdir(parents=True, exist_ok=True)
    out = report.render(ASTRBOT_TEMP / f"dafeiyu_report_{dt.datetime.now():%Y%m%d%H%M%S%f}.png",
                        date_label=f"{day.month}月{day.day}日 周{weekday}",
                        headline=clean(headline) or ("今天主人没来找本鱼玩" if not user_msgs else "平平淡淡的一天"),
                        stats=stats, hours=hours, sections=sections, server=server)
    return f"日报图片: {out}"


# ---------------- 网易云音乐 ----------------
import collections
import time as _time

import music_card
import style_map
import ncm

PROFILE = HOME / "music_profile.json"


def _lang(s: dict) -> str:
    t = s["name"] + s["artists"] + s.get("album", "")
    if re.search(r"[぀-ヿ]", t):
        return "日语"
    if re.search(r"[가-힯]", t):
        return "韩语"
    if re.search(r"[一-鿿]", t):
        return "中文"
    return "英文/纯音乐"


def _profile(force: bool = False) -> dict:
    """口味画像：一周算一次缓存起来（我喜欢 + 所有时间排行 + 最近一周排行）。"""
    cached = _load(PROFILE, {})
    if cached and not force and _time.time() - cached.get("ts", 0) < 7 * 86400:
        return cached
    liked = ncm.liked_songs()
    allr, week = ncm.play_record(False), ncm.play_record(True)
    artists = collections.Counter()
    for s in liked:
        for a in s["artists"].split(" / "):
            artists[a] += 1
    langs = collections.Counter(_lang(s) for s in liked)
    years = collections.Counter((dt.datetime.fromtimestamp(s["year"] / 1000).year // 5 * 5) for s in liked if s["year"])
    prof = {"ts": _time.time(), "liked_count": len(liked),
            "liked_ids": [s["id"] for s in liked],
            "top_artists": artists.most_common(40),
            "lang": {k: round(v * 100 / max(1, len(liked)), 1) for k, v in langs.most_common()},
            "years": {f"{y}-{y + 4}": n for y, n in sorted(years.items())},
            "all_time_top": [f"{s['name']} - {s['artists']}" for s in allr[:30]],
            "week_top": [f"{s['name']} - {s['artists']}（{s['plays']}次）" for s in week[:30]]}
    PROFILE.write_text(json.dumps(prof, ensure_ascii=False), encoding="utf-8")
    return prof


@mcp.tool()
def music_taste() -> str:
    """主人的网易云口味画像：我喜欢的歌（数量、最常出现的歌手、语种、年代）、所有时间和最近一周最常听的歌。
    数据一周更新一次。"""
    p = _profile()
    return (f"我喜欢共 {p['liked_count']} 首\n语种占比: {p['lang']}\n年代分布: {p['years']}\n"
            f"最常收藏的歌手: {', '.join(f'{a}({n})' for a, n in p['top_artists'][:25])}\n"
            f"所有时间最常听: {'; '.join(p['all_time_top'][:20])}\n"
            f"最近一周最常听: {'; '.join(p['week_top'][:20])}")


@mcp.tool()
def music_daily() -> str:
    """今天的网易云每日推荐（约 30 首），每首带上：网易云给的推荐理由、语种、是不是主人收藏过的歌手、是否已经在「我喜欢」里。
    用来和 music_taste 的口味画像对比，判断今天推荐合不合主人口味。"""
    songs = ncm.daily_recommend()
    p = _profile()
    fav = dict(p["top_artists"])
    all_artists = {a for a, _ in p["top_artists"]}
    liked = set(p["liked_ids"])
    lines = []
    for i, s in enumerate(songs, 1):
        known = [a for a in s["artists"].split(" / ") if a in all_artists]
        tag = []
        if s["id"] in liked:
            tag.append("已在我喜欢")
        if known:
            tag.append("收藏过的歌手:" + ",".join(f"{a}×{fav[a]}" for a in known))
        lines.append(f"{i}. {s['name']} - {s['artists']}｜{s['album']}｜{_lang(s)}"
                     f"{'｜' + s['reason'] if s['reason'] else ''}{'｜' + '；'.join(tag) if tag else ''}")
    known_cnt = sum("收藏过的歌手" in l for l in lines)
    return f"今日推荐 {len(songs)} 首（其中 {known_cnt} 首是主人收藏过的歌手）:\n" + "\n".join(lines)


@mcp.tool()
def music_report_card(headline: str, match_percent: int, styles: str, picks: str,
                      skip: str = "", comment: str = "") -> str:
    """生成「今日推荐品鉴」图片卡片。先调用 music_taste 和 music_daily，分析完再调用本工具：
    headline 一句话标题（比如「今天网易云在给你塞夜曲」）；match_percent 今天推荐和主人口味的吻合度 0-100；
    styles 今日推荐的风格分布，每行「风格: 百分比」，4～7 行，加起来约 100（比如「日系摇滚: 30」）；
    picks 今日必听 5 首，每行「歌名 - 歌手 | 一句推荐理由」；skip 可以跳过的歌和原因（1～3 行，可空）；
    comment 大肥鱼的点评（对今天推荐和主人最近口味的观察，2～3 句）。不要用 emoji。
    语种分布、收藏过的歌手数量等统计由工具自动算。返回图片路径，请把图片文件发给主人。"""
    clean = lambda s: "".join(ch for ch in (s or "") if ord(ch) < 0x10000)
    songs = ncm.daily_recommend()
    p = _profile()
    arts = {a for a, _ in p["top_artists"]}
    known = sum(any(a in arts for a in s["artists"].split(" / ")) for s in songs)
    langs = collections.Counter(_lang(s) for s in songs)
    style_rows = []
    for ln in clean(styles).splitlines():
        m = re.match(r"\s*[-·]?\s*(.+?)[:：]\s*([\d.]+)", ln)
        if m:
            style_rows.append((m.group(1).strip(), float(m.group(2))))
    pick_rows = []
    for ln in clean(picks).splitlines():
        if ln.strip():
            name, _, why = ln.partition("|")
            pick_rows.append((name.strip(" -·0123456789."), why.strip()))
    now = dt.datetime.now(BERLIN)
    sections = [(t, b) for t, b in [("可以跳过", clean(skip)), ("大肥鱼说", clean(comment))] if b.strip()]
    ASTRBOT_TEMP.mkdir(parents=True, exist_ok=True)
    out = music_card.render(
        ASTRBOT_TEMP / f"dafeiyu_music_{now:%Y%m%d%H%M%S%f}.png",
        title=f"{now.month}月{now.day}日 每日推荐", subtitle=clean(headline),
        stats=[("推荐", str(len(songs))), ("吻合度", f"{int(match_percent)}%"),
               ("熟悉歌手", str(known)), ("日语占比", f"{langs.get('日语', 0) * 100 // max(1, len(songs))}%")],
        charts=[("今日风格分布 %", style_rows[:7]),
                ("语种分布 %", [(k, round(v * 100 / len(songs))) for k, v in langs.most_common()])],
        picks=pick_rows[:5], sections=sections,
        footer=f"—— 口味画像基于我喜欢的 {p['liked_count']} 首 · 大肥鱼")
    return f"品鉴卡片: {out}"


@mcp.tool()
def music_style_card(groups: str, subtitle: str = "") -> str:
    """生成「今日推荐风格地图」卡片：把今天每日推荐的每一首按风格分组列出来（第二张卡，配合 music_report_card）。
    先调用 music_daily 看到带序号的歌单，再按风格分组，groups 每行一组，格式：
    「风格名 | 适合什么时候听（一句话） | 序号,序号,...」，比如「Galgame 歌 | 深夜怀旧时听 | 2,10,13,24」。
    分 4～8 组，每一首都要分到某一组（序号用 music_daily 里的编号）。subtitle 一句话概括。不要用 emoji。
    歌名、歌手、是否收藏过的歌手由工具自动填。返回图片路径，请把图片文件发给主人。"""
    clean = lambda s: "".join(ch for ch in (s or "") if ord(ch) < 0x10000)
    songs = ncm.daily_recommend()
    p = _profile()
    arts = {a for a, _ in p["top_artists"]}
    used, out_groups = set(), []
    for ln in clean(groups).splitlines():
        parts = [x.strip() for x in ln.split("|")]
        if len(parts) < 2:
            continue
        name, when, idxs = parts[0], (parts[1] if len(parts) == 3 else ""), parts[-1]
        rows = []
        for n in re.findall(r"\d+", idxs):
            i = int(n)
            if 1 <= i <= len(songs) and i not in used:
                s = songs[i - 1]
                used.add(i)
                rows.append((i, s["name"], s["artists"], any(a in arts for a in s["artists"].split(" / "))))
        if rows:
            out_groups.append((name.strip("「」 "), when, rows))
    rest = [(i, s["name"], s["artists"], any(a in arts for a in s["artists"].split(" / ")))
            for i, s in enumerate(songs, 1) if i not in used]
    if rest:
        out_groups.append(("其他", "", rest))
    now = dt.datetime.now(BERLIN)
    ASTRBOT_TEMP.mkdir(parents=True, exist_ok=True)
    out = style_map.render(ASTRBOT_TEMP / f"dafeiyu_style_{now:%Y%m%d%H%M%S%f}.png",
                           title=f"{now.month}月{now.day}日 风格地图",
                           subtitle=clean(subtitle) or f"今天的 {len(songs)} 首，按风格分好啦",
                           groups=out_groups, footer="★ = 你收藏过这位歌手的歌 · 大肥鱼")
    return f"风格地图图片: {out}"


@mcp.tool()
def server_report(comment: str = "") -> str:
    """生成「服务器日报」图片卡：内存/磁盘/CPU/Swap 仪表、AstrBot 和后台任务状态、过去 24 小时每个定时任务有没有按时跑、
    图库/备份/听歌数据/报错数。数据全部由工具自动统计；comment 可选，写一两句大肥鱼对服务器状况的点评（不要用 emoji）。
    返回图片路径，请用 send_message_to_user 把图片发给主人。"""
    import server_card

    def sh(cmd):
        return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30).stdout.strip()
    mem = [int(x) for x in sh("free -m | awk 'NR==2{print $3\" \"$2} NR==3{print $3\" \"$2}'").split()]
    disk = [int(x) for x in sh("df -BG / | awk 'NR==2{gsub(\"G\",\"\"); print $3\" \"$2}'").split()]
    load = float(sh("cut -d' ' -f1 /proc/loadavg") or 0)
    gauges = [("内存", mem[0] / mem[1], f"{mem[0]}/{mem[1]} MB"), ("磁盘", disk[0] / disk[1], f"{disk[0]}/{disk[1]} GB"),
              ("CPU", min(load / 2, 1.0), f"负载 {load:.2f}"), ("Swap", (mem[2] / mem[3]) if len(mem) > 3 and mem[3] else 0,
                                                                  f"{mem[2] if len(mem) > 2 else 0}/{mem[3] if len(mem) > 3 else 0} MB")]
    errs = int(sh("journalctl -u astrbot --since -24h --no-pager | grep -c ERRO") or 0)
    mcp_ok = "Connected to MCP server dafeiyu" in sh("journalctl -u astrbot --since -7d --no-pager | grep 'MCP server dafeiyu' | tail -1")
    services = [
        ("AstrBot", sh("systemctl is-active astrbot") == "active", "已运行 " + sh("uptime -p").replace("up ", "").replace(" days", " 天").replace(" day", " 天").replace(" hours", " 小时").replace(" hour", " 小时").replace(" minutes", " 分").replace(" minute", " 分").replace(",", "")),
        ("大肥鱼工具箱 MCP", mcp_ok, "已连接" if mcp_ok else "未连接"),
        ("定时器 cron", sh("systemctl is-active cron") == "active", "图库/快照/备份"),
        ("QQ 机器人", "Websocket session starting" in sh("journalctl -u astrbot --since -7d --no-pager | grep -i qqofficial | tail -3"), "官方 WebSocket"),
    ]
    _hb = _load(HOME / "watchdog_state.json", {}).get("heartbeat")
    _hb_age = (dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(_hb)).total_seconds() / 60 if _hb else None
    services.append(("看门狗", _hb_age is not None and _hb_age < 25,
                     f"{int(_hb_age)} 分钟前巡检" if _hb_age is not None else "没有运行记录"))
    # 过去 24 小时的定时任务：看任务运行后 5 分钟内日志里有没有「send_message_to_user ... Message sent」
    con = sqlite3.connect(f"file:{ASTRBOT_DB}?mode=ro", uri=True)
    now_utc = dt.datetime.now(dt.timezone.utc)
    _wd = _load(HOME / "watchdog_state.json", {})
    _since = (dt.datetime.now(BERLIN) - dt.timedelta(hours=24)).strftime("%Y-%m-%d %H:%M")
    _wdlog = HOME / "watchdog.log"
    fixes = sum(1 for l in (_wdlog.read_text(encoding="utf-8").splitlines() if _wdlog.exists() else []) if l[:16] >= _since)
    rows = []
    for name, cron, last in con.execute("select name, cron_expression, last_run_at from cron_jobs where enabled=1"):
        mi, hr = cron.split()[:2]
        short = "晚饭" if "晚上好" in name else name
        order = int(hr) * 60 + int(mi) if hr.isdigit() and mi.isdigit() else 9999
        if last and last != "None":
            t = dt.datetime.fromisoformat(str(last)).replace(tzinfo=dt.timezone.utc)
            if now_utc - t < dt.timedelta(hours=24, minutes=10):
                a = t.astimezone(ZoneInfo("Asia/Shanghai"))
                log = sh(f"journalctl -u astrbot --since '{a:%Y-%m-%d %H:%M:%S}' --until '{(a + dt.timedelta(minutes=5)):%Y-%m-%d %H:%M:%S}' --no-pager | grep -c 'send_message_to_user. Result: Message sent'")
                sent = int(log or 0) > 0
                fixed = any(v.get("name") == name and v.get("ok") for v in _wd.get("retried", {}).values())
                rows.append((order, short, t.astimezone(BERLIN).strftime("%H:%M") + (" 已补发" if sent and fixed else " 已送达" if sent else " 没发出"), sent))
                continue
        rows.append((order, short, f"{int(hr):02d}:{int(mi):02d} 还没到时间" if order < 9999 else "未运行", None))
    jobs = [(n, w, ok) for _, n, w, ok in sorted(rows)]
    con.close()
    pool = len(_pending_images())
    rows = sh("cat /root/dafeiyu-mcp/data/week_record.csv 2>/dev/null | wc -l")
    backup = sh("ls -t /root/backups/astrbot-*.tar.gz 2>/dev/null | head -1 | xargs -r basename").replace("astrbot-", "").replace(".tar.gz", "")
    facts = [("图库存货", f"{pool} 张"), ("24h 报错", f"{errs} 行"), ("听歌快照", f"{max(0, int(rows or 1) - 1)} 行"),
             ("最近备份", backup or "无"), ("网易云登录", "有效" if (HOME / "netease_session.txt").exists() else "未登录"),
             ("自动修复", f"24h {fixes} 次")]
    bad = [g[0] for g in gauges if g[1] >= .9] + [s[0] for s in services if not s[1]] + [j[0] + '没发出' for j in jobs if j[2] is False]
    verdict = "一切正常，主人放心" if not bad else "需要注意：" + "、".join(bad)
    now = dt.datetime.now(BERLIN)
    clean = lambda s: "".join(ch for ch in (s or "") if ord(ch) < 0x10000)
    ASTRBOT_TEMP.mkdir(parents=True, exist_ok=True)
    out = server_card.render(ASTRBOT_TEMP / f"dafeiyu_server_{now:%Y%m%d%H%M%S%f}.png",
                             date_label=f"{now.month}月{now.day}日", verdict=verdict, gauges=gauges,
                             services=services, jobs=jobs, facts=facts, comment=clean(comment))
    return f"服务器日报图片: {out}"


# ---------------- 邮件（WEB.DE，里面代收着 Gmail） ----------------
def _dec(s) -> str:
    out = ""
    for part, enc in email.header.decode_header(s or ""):
        out += part.decode(enc or "utf-8", "replace") if isinstance(part, bytes) else part
    return out


def _body(msg) -> str:
    for part in msg.walk():
        if part.get_content_type() == "text/plain":
            payload = part.get_payload(decode=True) or b""
            return payload.decode(part.get_content_charset() or "utf-8", "replace")
    for part in msg.walk():
        if part.get_content_type() == "text/html":
            html = (part.get_payload(decode=True) or b"").decode(part.get_content_charset() or "utf-8", "replace")
            return re.sub(r"<[^>]+>", " ", html)
    return ""


def _mail_scan(advance: bool, max_count: int = 15, recent_hours: int = 48) -> tuple[list, int]:
    """返回 (新邮件列表, 被挡掉的旧邮件数)。advance=True 才推进「已读到哪」的位置。只读邮箱，不标已读。"""
    cfg = _load(CONFIG, {}).get("mail")
    if not cfg:
        raise RuntimeError("邮箱还没配置（电脑上运行 set-mail.ps1）")
    state = _load(STATE, {})
    pos = state.setdefault("mail_pos", {})
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=recent_hours)
    found, skipped = [], 0
    import fcntl
    lock = open("/tmp/dafeiyu-mail.lock", "w")
    fcntl.flock(lock, fcntl.LOCK_EX)          # 同一时间只允许一个读邮箱（读完自动释放）
    state = _load(STATE, {})                   # 拿到锁后重新读一次位置
    pos = state.setdefault("mail_pos", {})
    with imaplib.IMAP4_SSL(cfg["host"], 993, timeout=30) as M:
        M.login(cfg["user"], cfg["password"])
        for folder in cfg.get("folders", ["INBOX"]):
            typ, _ = M.select(f'"{folder}"', readonly=True)
            if typ != "OK":
                continue
            validity = M.response("UIDVALIDITY")[1][0].decode()
            _, data = M.uid("search", None, "ALL")
            all_uids = [int(u) for u in data[0].split()]
            if not all_uids:
                continue
            key = f"{cfg['user']}/{folder}"
            rec = pos.get(key)
            if not rec or rec.get("validity") != validity:      # 第一次 / 邮箱重建：只记位置
                if advance:
                    pos[key] = {"validity": validity, "uid": max(all_uids)}
                continue
            uids = [u for u in all_uids if u > rec["uid"]]
            if uids:
                _, hd = M.uid("fetch", ",".join(map(str, uids[-500:])), "(UID BODY.PEEK[HEADER.FIELDS (DATE)])")
                recent = []
                for part in hd:
                    if not isinstance(part, tuple):
                        continue
                    uid = int(re.search(rb"UID (\d+)", part[0]).group(1))
                    date_s = email.message_from_bytes(part[1])["Date"]
                    try:
                        when = email.utils.parsedate_to_datetime(date_s)
                        when = when if when.tzinfo else when.replace(tzinfo=dt.timezone.utc)
                    except Exception:
                        when = None
                    if when is None or when >= cutoff:
                        recent.append(uid)
                    else:
                        skipped += 1
                todo = sorted(recent)[:max_count]       # 从早到晚，一次最多 max_count 封
                for uid in todo:
                    _, md = M.uid("fetch", str(uid), "(BODY.PEEK[])")
                    msg = email.message_from_bytes(md[0][1])
                    found.append({"folder": folder, "from": _dec(msg["From"]), "subject": _dec(msg["Subject"]),
                                  "date": msg["Date"], "snippet": re.sub(r"\s+", " ", _body(msg))[:300]})
                if advance:
                    # 全处理完 → 推进到最新；还有剩的 → 只推进到处理过的最后一封，剩下的下次处理
                    rec["uid"] = max(uids) if len(recent) <= max_count else todo[-1]
    if advance:
        _save_state(state)
    return found, skipped


@mcp.tool()
def new_emails(max_count: int = 15) -> str:
    """查看邮箱（WEB.DE，里面代收着 Gmail）上次检查之后新来的邮件：发件人、标题、时间、开头一小段。
    只读，不会把邮件标成已读。拿到后请判断哪些重要（成绩、考试、学校/大学通知、银行账单、快递、
    合同/房租/保险、需要主人回复或处理的），只把重要的告诉主人；广告、社交网站通知、促销、订阅推送直接忽略。"""
    try:
        found, skipped = _mail_scan(advance=ROLE != "pc", max_count=max_count)
    except Exception as e:
        return f"读邮箱失败：{e}"
    if not found:
        return "没有新邮件。" + (f"（另有 {skipped} 封是代收搬过来的旧邮件，已忽略）" if skipped else "")
    lines = [f"- 来自 {m['from']}｜{m['subject']}｜{m['date']}\n  {m['snippet']}" for m in found]
    more = "（还有更多新邮件，下次检查时继续）" if len(found) >= max_count else ""
    return f"新邮件 {len(found)} 封{more}：\n" + "\n".join(lines)

# ---------------- 电脑协作：任务队列（大肥鱼 ⇄ 电脑上的 Claude Code / Codex） ----------------
import fcntl as _fcntl
import os
ROLE = os.environ.get("DAFEIYU_ROLE", "astrbot")
PC_TASKS = HOME / "data" / "pc_tasks.json"


def _for(role):
    """只给某个身份注册成工具；另一个身份看不到它。"""
    return mcp.tool() if ROLE == role else (lambda f: f)


def _tasks_edit(fn):
    """加锁读-改-写任务文件。fn(tasks) 返回结果。"""
    PC_TASKS.parent.mkdir(parents=True, exist_ok=True)
    with open("/tmp/dafeiyu-pctasks.lock", "w") as lk:
        _fcntl.flock(lk, _fcntl.LOCK_EX)
        tasks = _load(PC_TASKS, [])
        out = fn(tasks)
        PC_TASKS.write_text(json.dumps(tasks, ensure_ascii=False, indent=1), encoding="utf-8")
        os.chmod(PC_TASKS, 0o600)
        return out


def _now_berlin() -> str:
    return dt.datetime.now(BERLIN).strftime("%Y-%m-%d %H:%M")


def _astrbot_run(job_name: str) -> str:
    """叫 AstrBot 立即执行某个任务（本机现签 5 分钟令牌）。"""
    import jwt, urllib.request
    dash = json.load(open("/root/astrbot/data/cmd_config.json", encoding="utf-8-sig"))["dashboard"]
    tok = jwt.encode({"username": dash.get("username", "astrbot"),
                      "exp": dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=5)}, dash["jwt_secret"], algorithm="HS256")
    con = sqlite3.connect(f"file:{ASTRBOT_DB}?mode=ro", uri=True)
    row = con.execute("select job_id from cron_jobs where name=?", (job_name,)).fetchone()
    con.close()
    if not row:
        return f"找不到任务「{job_name}」"
    req = urllib.request.Request(f"http://127.0.0.1:{dash.get('port', 6185)}/api/v1/cron/jobs/{row[0]}/run",
                                 method="POST", headers={"Authorization": f"Bearer {tok}"})
    return urllib.request.urlopen(req, timeout=20).read().decode()[:100]


@_for("astrbot")
def pc_task_add(title: str, detail: str) -> str:
    """把一件事交给主人电脑上的 Claude Code / Codex 去做（写进任务队列，电脑那边打开时会领走）。
    当主人说「让电脑上的 Claude / Codex 帮我……」「交给电脑做……」时使用。
    title：一句话标题；detail：把主人的要求原样、完整地写清楚（要做什么、交付什么、放在哪）。
    加完告诉主人：已经交给电脑了，做完会回来汇报。"""
    def add(tasks):
        tid = max([t["id"] for t in tasks] + [0]) + 1
        tasks.append({"id": tid, "title": title[:80], "detail": detail[:2000], "status": "pending",
                      "created": _now_berlin(), "by": "大肥鱼", "agent": None, "result": None, "reported": False})
        return tid
    tid = _tasks_edit(add)
    return f"已加入电脑任务队列：#{tid}「{title[:80]}」。电脑上的 Claude Code / Codex 打开后会领取，做完我会收到结果。"


@_for("astrbot")
def pc_task_status() -> str:
    """查看交给电脑的任务现在怎么样了（待领取 / 进行中 / 已完成）。主人问「电脑那边做得怎么样了」时使用。"""
    tasks = _load(PC_TASKS, [])
    if not tasks:
        return "电脑任务队列是空的。"
    names = {"pending": "待领取", "claimed": "进行中", "done": "已完成"}
    return "\n".join(f"#{t['id']} [{names.get(t['status'], t['status'])}] {t['title']}"
                     + (f"（{t['agent']}）" if t.get("agent") else "") for t in tasks[-15:])


@_for("astrbot")
def pc_task_report() -> str:
    """取出电脑那边新完成、还没汇报给主人的任务结果（取出后标记为已汇报）。"""
    def take(tasks):
        out = [t for t in tasks if t["status"] == "done" and not t.get("reported")]
        for t in out:
            t["reported"] = True
        return out
    done = _tasks_edit(take)
    if not done:
        return "没有新完成的电脑任务。"
    return "\n\n".join(f"#{t['id']}「{t['title']}」由 {t.get('agent') or '电脑'} 在 {t.get('finished')} 完成：\n{t['result']}"
                       for t in done)


@_for("pc")
def pc_task_list() -> str:
    """列出大肥鱼（主人在 QQ 上）交给电脑的任务。先看这个，再用 pc_task_claim 领取。"""
    tasks = [t for t in _load(PC_TASKS, []) if t["status"] != "done"]
    if not tasks:
        return "没有待办的电脑任务。"
    return "\n\n".join(f"#{t['id']} [{t['status']}] {t['title']}（{t['created']}）\n{t['detail']}" for t in tasks)


@_for("pc")
def pc_task_claim(task_id: int, agent: str) -> str:
    """领取一个任务，表示你开始做了。agent 填你自己的名字，比如 "Claude Code" 或 "Codex"。"""
    def claim(tasks):
        for t in tasks:
            if t["id"] == task_id:
                if t["status"] != "pending":
                    return f"#{task_id} 现在是 {t['status']}，不能领取。"
                t.update(status="claimed", agent=agent[:30], claimed=_now_berlin())
                return f"已领取 #{task_id}「{t['title']}」。要求：\n{t['detail']}\n做完后调用 pc_task_done 填写结果。"
        return f"没有 #{task_id}。"
    return _tasks_edit(claim)


@_for("pc")
def pc_task_done(task_id: int, result: str) -> str:
    """任务做完后调用：result 写清楚做了什么、结果是什么、文件放在哪（主人会在 QQ 上看到，写简洁）。
    调用后大肥鱼会马上在 QQ 上把结果告诉主人。"""
    def done(tasks):
        for t in tasks:
            if t["id"] == task_id:
                t.update(status="done", result=result[:3000], finished=_now_berlin(), reported=False)
                return True
        return False
    if not _tasks_edit(done):
        return f"没有 #{task_id}。"
    try:
        r = _astrbot_run("电脑任务汇报")
    except Exception as e:
        r = f"叫醒大肥鱼失败：{e}（结果已保存，下次大肥鱼查状态时能看到）"
    return f"#{task_id} 已标记完成，已通知大肥鱼汇报给主人。{r}"


# ---------------- 电脑端精简：只留用得上的工具（省每个新对话的 token） ----------------
PC_KEEP = {"server_status", "server_metrics", "chat_history", "new_emails",
           "pc_task_list", "pc_task_claim", "pc_task_done"}
if ROLE == "pc":
    for _name in [t.name for t in mcp._tool_manager.list_tools()]:
        if _name not in PC_KEEP:
            mcp._tool_manager._tools.pop(_name, None)


if __name__ == "__main__":
    mcp.run()
