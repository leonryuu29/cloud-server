"""邮件门铃：系统 cron 每小时跑一次（德国 7:00–23:59），不用 AI。
只「看一眼」有没有 48 小时内的新邮件（不推进位置）；有才叫醒大肥鱼的「重要邮件」任务，
由大肥鱼调用 new_emails 判断重要不重要，重要的才发给主人。没新邮件 → 什么都不做，不花 token。
刹车：同一批新邮件只叫醒一次（记下叫醒时邮箱里最大的编号）。"""
import datetime as dt
import json
import pathlib
import sqlite3
import sys
from zoneinfo import ZoneInfo

sys.path.insert(0, "/root/dafeiyu-mcp")
import server                      # noqa: E402  复用 _mail_scan
from watchdog import run_job_now, trim   # noqa: E402  复用本机令牌

STATE = pathlib.Path("/root/dafeiyu-mcp/mail_check_state.json")
LOG = pathlib.Path("/root/dafeiyu-mcp/mail_check.log")
JOB_NAME = "重要邮件"


def log(msg: str):
    line = f"{dt.datetime.now(ZoneInfo('Europe/Berlin')):%Y-%m-%d %H:%M} {msg}"
    print(line)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    trim(LOG)


# 只放「肯定不重要」的发件域名（社交通知、营销）；拿不准的（Google、银行、学校、快递）一律不放，交给大肥鱼判断
NOISE_DOMAINS = ("linkedin.com", "fantia.jp", "tiktok.com", "facebookmail.com", "facebook.com", "instagram.com",
                 "fromjapan.co.jp", "learn.termius.com", "design.com", "x.com", "twitter.com", "pinterest.com",
                 "notice.alibaba.com", "mail.bilibili.com")


def is_noise(sender: str) -> bool:
    addr = sender.rsplit("<", 1)[-1].strip("> ").lower()
    return any(addr.endswith("@" + d) or addr.endswith("." + d) for d in NOISE_DOMAINS)


def main(force: bool = False):
    if not force and not 7 <= dt.datetime.now(ZoneInfo("Europe/Berlin")).hour <= 23:
        return
    found, skipped = server._mail_scan(advance=False)
    if not found:
        return
    worth = [m for m in found if not is_noise(m["from"])]
    if not worth:
        # 全是广告/社交通知：代码直接标记处理过，不叫醒大肥鱼（不花 token）
        server._mail_scan(advance=True)
        log(f"邮件门铃：{len(found)} 封全是广告/通知，直接跳过（没叫醒大肥鱼）")
        return
    st = json.loads(STATE.read_text()) if STATE.exists() else {}
    sig = f"{len(found)}|{found[-1]['subject']}|{found[-1]['date']}"
    if st.get("last_sig") == sig and not force:
        return                                    # 这批已经叫醒过了（大肥鱼没处理就留给日志排查，不反复花钱）
    con = sqlite3.connect("file:/root/astrbot/data/data_v4.db?mode=ro", uri=True)
    row = con.execute("select job_id from cron_jobs where name=?", (JOB_NAME,)).fetchone()
    con.close()
    if not row:
        log("邮件门铃：找不到「重要邮件」任务")
        return
    run_job_now(row[0])
    STATE.write_text(json.dumps({"last_sig": sig, "at": dt.datetime.now().isoformat()}, ensure_ascii=False))
    log(f"邮件门铃：{len(found)} 封新邮件，已叫醒大肥鱼判断")


def beat(error: str | None):
    """心跳：每次运行都记一下（时间 + 有没有出错），验收靠它发现“门铃静悄悄地坏了”。"""
    hb = pathlib.Path("/root/dafeiyu-mcp/mail_check_heartbeat.json")
    hb.write_text(json.dumps({"at": dt.datetime.now(dt.timezone.utc).isoformat(), "error": error}, ensure_ascii=False))


if __name__ == "__main__":
    err = None
    try:
        main(force="--force" in sys.argv)
    except Exception as e:
        err = f"{type(e).__name__}: {str(e)[:150]}"
        log(f"邮件门铃出错：{err}")
    beat(err)
