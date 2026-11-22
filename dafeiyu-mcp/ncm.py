"""网易云音乐接口（只读）：每日推荐、听歌排行、我喜欢。登录态来自 netease_session.txt。"""
import pathlib

import pyncm
from pyncm.apis import WeapiCryptoRequest
from pyncm.apis.track import GetTrackDetail

SESSION = pathlib.Path("/root/dafeiyu-mcp/netease_session.txt")
_loaded = {"ok": False, "uid": None}


def ensure_login() -> int:
    if not _loaded["ok"]:
        if not SESSION.exists():
            raise RuntimeError("网易云还没登录（需要在服务器上运行 ncm_login.py 扫码）")
        pyncm.SetCurrentSession(pyncm.LoadSessionFromString(SESSION.read_text(encoding="utf-8")))
        _loaded["ok"] = True
        _loaded["uid"] = pyncm.GetCurrentSession().uid
    return _loaded["uid"]


@WeapiCryptoRequest
def _daily():
    return "/weapi/v3/discovery/recommend/songs", {}


@WeapiCryptoRequest
def _record(uid, type_):
    return "/weapi/v1/play/record", {"uid": str(uid), "type": str(type_)}


@WeapiCryptoRequest
def _likelist(uid):
    return "/weapi/song/like/get", {"uid": str(uid)}


def _song(s: dict) -> dict:
    ar = s.get("ar") or s.get("artists") or []
    al = s.get("al") or s.get("album") or {}
    return {"id": s["id"], "name": s["name"], "artists": " / ".join(a.get("name", "") for a in ar),
            "album": al.get("name", ""), "year": (al.get("publishTime") or s.get("publishTime") or 0)}


def daily_recommend() -> list[dict]:
    ensure_login()
    r = _daily()
    if r.get("code") != 200:
        raise RuntimeError(f"每日推荐获取失败 code={r.get('code')} {r.get('message', '')}")
    out = []
    for s in r["data"]["dailySongs"]:
        song = _song(s)
        reason = next((x.get("reason") for x in r["data"].get("recommendReasons", []) if x.get("songId") == s["id"]), "")
        song["reason"] = reason or s.get("reason") or ""
        out.append(song)
    return out


def play_record(week: bool = True) -> list[dict]:
    """听歌排行：week=True 最近一周，False 所有时间（各最多 100 首）。"""
    uid = ensure_login()
    r = _record(uid, 1 if week else 0)
    if r.get("code") != 200:
        raise RuntimeError(f"听歌排行获取失败 code={r.get('code')} {r.get('message', '')}")
    data = r.get("weekData" if week else "allData") or []
    return [dict(_song(x["song"]), score=x.get("score"), plays=x.get("playCount")) for x in data]


def liked_songs() -> list[dict]:
    """「我喜欢的音乐」全部歌曲（分批查详情）。"""
    uid = ensure_login()
    ids = _likelist(uid).get("ids", [])
    out = []
    for i in range(0, len(ids), 500):
        d = GetTrackDetail(ids[i:i + 500])
        out += [_song(s) for s in d.get("songs", [])]
    return out
