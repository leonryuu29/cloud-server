"""B 站接口：WBI 签名、按 UID 查最新投稿、按名字搜 UP 主。"""
import hashlib
import time
import urllib.parse

import httpx

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")
MIXIN_TAB = [46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
             33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40, 61,
             26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36,
             20, 34, 44, 52]

_cache = {"mixin": None, "ts": 0, "cookies": None}


def _client() -> httpx.Client:
    c = httpx.Client(headers={"User-Agent": UA, "Referer": "https://www.bilibili.com/"},
                     timeout=15, follow_redirects=True)
    if _cache["cookies"] is None:
        # 拿匿名访客 cookie（buvid3/buvid4），不带的话容易被风控
        try:
            d = c.get("https://api.bilibili.com/x/frontend/finger/spi").json()["data"]
            _cache["cookies"] = {"buvid3": d["b_3"], "buvid4": d["b_4"]}
        except Exception:
            _cache["cookies"] = {}
    c.cookies.update(_cache["cookies"])
    return c


def _mixin_key(c: httpx.Client) -> str:
    if _cache["mixin"] and time.time() - _cache["ts"] < 3600:
        return _cache["mixin"]
    wbi = c.get("https://api.bilibili.com/x/web-interface/nav").json()["data"]["wbi_img"]
    key = lambda url: url.rsplit("/", 1)[-1].split(".")[0]
    orig = key(wbi["img_url"]) + key(wbi["sub_url"])
    _cache["mixin"] = "".join(orig[i] for i in MIXIN_TAB)[:32]
    _cache["ts"] = time.time()
    return _cache["mixin"]


def _signed(c: httpx.Client, params: dict) -> dict:
    p = dict(params, wts=int(time.time()))
    p = {k: "".join(ch for ch in str(v) if ch not in "!'()*") for k, v in sorted(p.items())}
    q = urllib.parse.urlencode(p)
    p["w_rid"] = hashlib.md5((q + _mixin_key(c)).encode()).hexdigest()
    return p


def latest_videos(mid: int, n: int = 3) -> list[dict]:
    """某个 UP 主最新的 n 个投稿。优先用 recArchivesByKeywords（不用签名、不容易被风控）。"""
    c = _client()
    try:
        r = c.get("https://api.bilibili.com/x/series/recArchivesByKeywords",
                  params={"mid": mid, "keywords": "", "ps": n, "pn": 1}).json()
        if r.get("code") == 0:
            return [{"up": a.get("author") or str(mid), "title": a["title"], "bvid": a["bvid"],
                     "url": f"https://www.bilibili.com/video/{a['bvid']}",
                     "created": a["pubdate"],
                     "length": f"{a.get('duration', 0) // 60}:{a.get('duration', 0) % 60:02d}",
                     "desc": ""} for a in r["data"].get("archives", [])]
    finally:
        c.close()
    return _latest_videos_wbi(mid, n)


def _latest_videos_wbi(mid: int, n: int = 3) -> list[dict]:
    """某个 UP 主最新的 n 个投稿。"""
    c = _client()
    try:
        params = _signed(c, {"mid": mid, "ps": n, "pn": 1, "order": "pubdate",
                             "dm_img_list": "[]",
                             "dm_img_str": "V2ViR0wgMS4wIChPcGVuR0wgRVMgMi4wIENocm9taXVtKQ",
                             "dm_cover_img_str": "QU5HTEUgKE5WSURJQSwgTlZJRElBIEdlRm9yY2UgR1RYIDEwNjApKQ"})
        r = c.get("https://api.bilibili.com/x/space/wbi/arc/search", params=params).json()
    finally:
        c.close()
    if r.get("code") != 0:
        raise RuntimeError(f"bilibili code={r.get('code')} msg={r.get('message')}")
    out = []
    for v in r["data"]["list"]["vlist"]:
        out.append({"up": v["author"], "title": v["title"], "bvid": v["bvid"],
                    "url": f"https://www.bilibili.com/video/{v['bvid']}",
                    "created": v["created"], "length": v.get("length", ""),
                    "desc": (v.get("description") or "")[:80]})
    return out


def search_up(keyword: str, n: int = 5) -> list[dict]:
    """按名字搜 UP 主，返回 UID。"""
    c = _client()
    try:
        params = _signed(c, {"search_type": "bili_user", "keyword": keyword, "page": 1})
        r = c.get("https://api.bilibili.com/x/web-interface/wbi/search/type", params=params).json()
    finally:
        c.close()
    if r.get("code") != 0:
        raise RuntimeError(f"bilibili code={r.get('code')} msg={r.get('message')}")
    res = r.get("data", {}).get("result") or []
    return [{"name": u["uname"], "mid": u["mid"], "fans": u.get("fans"),
             "sign": (u.get("usign") or "")[:40]} for u in res[:n]]
