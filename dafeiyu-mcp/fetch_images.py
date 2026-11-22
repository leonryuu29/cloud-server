"""后台预取二次元图：Safebooru（全年龄图站，北京能直连，速度快）。
按 config.json 里的 image_tags 取图（每个标签按权重分配张数），图库保持 POOL 张没发过的。
cron 每 4 小时跑一次；06:00 的「今日画廊」会把图库里的图拼成一张发给主人。"""
import json
import pathlib
import random
import sys
import time

import httpx

HOME = pathlib.Path("/root/dafeiyu-mcp")
BASE = HOME / "images"
POOL = 20
TOP_N = 200          # 每个角色只从收藏分最高的 200 张里选
API = "https://safebooru.org/index.php"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36"
DEFAULT_TAGS = [
    {"tag": "yuzuki_yukari", "name": "结月缘", "weight": 4},
    {"tag": "ryu_lion", "name": "琉·利昂", "weight": 3},
    {"tag": "natsume_anan", "name": "夏目安安", "weight": 2},
    {"tag": "mahou_shoujo_no_majo_saiban", "name": "魔女裁判", "weight": 1},
]
# 全年龄站也偶尔有泳装之类，这里再挡一层
BLOCK = {"swimsuit", "bikini", "underwear", "panties", "cleavage", "ass", "lingerie",
         "nude", "naked", "pantyshot", "ai-generated", "ai_generated"}


def load(p, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def pending():
    return [p for p in BASE.glob("*.json") if not load(p, {}).get("sent")]


def pick_tag(tags):
    return random.choices(tags, weights=[t.get("weight", 1) for t in tags])[0]


def main():
    BASE.mkdir(parents=True, exist_ok=True)
    tags = load(HOME / "config.json", {}).get("image_tags") or DEFAULT_TAGS
    c = httpx.Client(headers={"User-Agent": UA}, timeout=60, follow_redirects=True)
    seen = {p.stem.split("_")[1] for p in BASE.glob("*.json")}
    need, tries = POOL - len(pending()), 0
    while need > 0 and tries < 20:
        tries += 1
        t = pick_tag(tags)
        query = f"{t['tag']} sort:score:desc -{' -'.join(BLOCK)}"
        try:
            count_xml = c.get(API, params={"page": "dapi", "s": "post", "q": "index",
                                           "limit": 0, "tags": query}).text
            total = int(count_xml.split('count="')[1].split('"')[0])
            if total == 0:
                continue
            pid = random.randint(0, max(0, min(total, TOP_N) // 20 - 1))   # 只在高分前 TOP_N 里抽   # 随机翻页，图不重样
            posts = c.get(API, params={"page": "dapi", "s": "post", "q": "index", "json": 1,
                                       "limit": 20, "pid": pid, "tags": query}).json() or []
        except Exception as e:
            print("query failed", t["tag"], e, file=sys.stderr)
            time.sleep(3)
            continue
        random.shuffle(posts)
        for post in posts:
            pid_s = str(post["id"])
            if pid_s in seen or BLOCK & set(post.get("tags", "").split()):
                continue
            url = post.get("sample_url") or post.get("file_url")
            img = BASE / f"sb_{pid_s}{pathlib.Path(url).suffix or '.jpg'}"
            try:
                img.write_bytes(c.get(url).content)
            except Exception as e:
                print("download failed", url, e, file=sys.stderr)
                continue
            img.with_suffix(".json").write_text(json.dumps({
                "id": pid_s, "character": t["name"], "file": str(img), "sent": False,
                "post": f"https://safebooru.org/index.php?page=post&s=view&id={pid_s}",
                "source": post.get("source", "")}, ensure_ascii=False), encoding="utf-8")
            seen.add(pid_s)
            need -= 1
            print("ok", t["name"], img.name)
            break                       # 每个标签抽一次只拿一张，保证角色多样
        time.sleep(1)
    # 发过的图只留最近 60 张
    sent = sorted((p for p in BASE.glob("*.json") if load(p, {}).get("sent")), key=lambda p: p.stat().st_mtime)
    for p in sent[:-60]:
        pathlib.Path(load(p, {}).get("file", "")).unlink(missing_ok=True)
        p.unlink()


if __name__ == "__main__":
    main()
