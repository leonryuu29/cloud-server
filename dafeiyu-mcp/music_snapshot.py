"""每天存一份听歌快照，给以后的 pandas 口味周报攒数据。
data/week_record.csv   每天一份「最近一周听歌排行」（日期, 排名, 歌名, 歌手, 专辑, 播放次数）
data/daily_recommend.csv 每天的每日推荐（日期, 序号, 歌名, 歌手, 专辑, 推荐理由）
cron：每天德国 23:00 左右（北京 6 点每日推荐刷新之后）跑一次。"""
import csv
import datetime as dt
import pathlib
import sys
from zoneinfo import ZoneInfo

sys.path.insert(0, "/root/dafeiyu-mcp")
import ncm

DATA = pathlib.Path("/root/dafeiyu-mcp/data")
today = dt.datetime.now(ZoneInfo("Europe/Berlin")).date().isoformat()


def append(path: pathlib.Path, header: list[str], rows: list[list]):
    new = not path.exists()
    if not new and today in path.read_text(encoding="utf-8"):   # 同一天只存一次
        return 0
    with path.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(header)
        w.writerows(rows)
    return len(rows)


DATA.mkdir(exist_ok=True)
week = ncm.play_record(week=True)
n1 = append(DATA / "week_record.csv", ["date", "rank", "song_id", "name", "artists", "album", "plays"],
            [[today, i, s["id"], s["name"], s["artists"], s["album"], s["plays"]] for i, s in enumerate(week, 1)])
rec = ncm.daily_recommend()
n2 = append(DATA / "daily_recommend.csv", ["date", "idx", "song_id", "name", "artists", "album", "reason"],
            [[today, i, s["id"], s["name"], s["artists"], s["album"], s["reason"]] for i, s in enumerate(rec, 1)])
print(today, "week rows", n1, "recommend rows", n2)
