"""大肥鱼看门狗：cron 每 10 分钟跑一次，发现问题自己修。
1. 推送补发：定时任务跑完 5 分钟内日志里没有「send_message_to_user ... Message sent」→ 调 AstrBot 后台的「立即执行」接口补发一次
   （每次运行最多补发 1 次；补发还失败就放弃，留给服务器日报报出来）
2. AstrBot 没在跑 → systemctl restart
3. MCP 工具箱没连上 → 重启 AstrBot（1 小时内最多一次）
4. 图库存货 < 6 → 后台补货
5. 磁盘 > 90% → 清理 3 天前的临时图片
接口认证：用服务器本机 cmd_config.json 里的 jwt_secret 签一个 5 分钟有效的后台令牌（只在本机用，不保存、不打印）。"""
import datetime as dt
import json
import pathlib
import sqlite3
import subprocess
import urllib.request
from zoneinfo import ZoneInfo

import jwt

HOME = pathlib.Path("/root/dafeiyu-mcp")
STATE = HOME / "watchdog_state.json"
LOG = HOME / "watchdog.log"
DB = "/root/astrbot/data/data_v4.db"
CFG = "/root/astrbot/data/cmd_config.json"
CST, BERLIN, UTC = ZoneInfo("Asia/Shanghai"), ZoneInfo("Europe/Berlin"), dt.timezone.utc
now = dt.datetime.now(UTC)


def sh(cmd: str) -> str:
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60).stdout.strip()


def log(msg: str):
    line = f"{now.astimezone(BERLIN):%Y-%m-%d %H:%M} {msg}"
    print(line)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def load_state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def sent_between(t0: dt.datetime, minutes: int = 5) -> bool:
    a = t0.astimezone(CST)
    b = a + dt.timedelta(minutes=minutes)
    out = sh(f"journalctl -u astrbot --since '{a:%Y-%m-%d %H:%M:%S}' --until '{b:%Y-%m-%d %H:%M:%S}' --no-pager "
             "| grep -c 'send_message_to_user. Result: Message sent'")
    return int(out or 0) > 0


def run_job_now(job_id: str) -> str:
    dash = json.load(open(CFG, encoding="utf-8-sig"))["dashboard"]
    token = jwt.encode({"username": dash.get("username", "astrbot"), "auth_source": "watchdog",
                        "exp": now + dt.timedelta(minutes=5)}, dash["jwt_secret"], algorithm="HS256")
    port = dash.get("port", 6185)
    req = urllib.request.Request(f"http://127.0.0.1:{port}/api/v1/cron/jobs/{job_id}/run", method="POST",
                                 headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode()[:200]


def check_pushes(state: dict):
    retried = state.setdefault("retried", {})       # job_id -> {"orig": 原运行时间, "at": 补发时间}
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    jobs = con.execute("select job_id, name, last_run_at from cron_jobs where enabled=1").fetchall()
    con.close()
    for job_id, name, last in jobs:
        if not last or last == "None":
            continue
        t = dt.datetime.fromisoformat(str(last)).replace(tzinfo=UTC)
        age = now - t
        if not (dt.timedelta(minutes=6) <= age <= dt.timedelta(minutes=40)):
            continue                                  # 只管刚跑完不久的，不翻旧账
        if sent_between(t):
            if job_id in retried and retried[job_id].get("at") == str(last) and not retried[job_id].get("ok"):
                retried[job_id]["ok"] = True
                log(f"补发成功：{name}")
            continue
        rec = retried.get(job_id)
        if rec and (rec.get("orig") == str(last) or rec.get("at") == str(last)):
            if rec.get("at") == str(last) and not rec.get("gave_up"):
                rec["gave_up"] = True
                log(f"补发后仍没发出，放弃：{name}（留给服务器日报报告）")
            continue
        try:
            resp = run_job_now(job_id)
            retried[job_id] = {"orig": str(last), "at": None, "name": name, "when": now.isoformat()}
            log(f"没发出，已自动补发：{name}（原定 {t.astimezone(BERLIN):%H:%M}）→ {resp}")
        except Exception as e:
            log(f"补发失败：{name}：{e}")


def record_retry_runs(state: dict):
    """补发触发后，任务的 last_run_at 会变成补发那次的时间，记下来以便下一轮核对。"""
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    for job_id, rec in state.get("retried", {}).items():
        if rec.get("at") is None:
            row = con.execute("select last_run_at from cron_jobs where job_id=?", (job_id,)).fetchone()
            if row and str(row[0]) != rec["orig"]:
                rec["at"] = str(row[0])
    con.close()


def self_heal(state: dict):
    if sh("systemctl is-active astrbot") != "active":
        sh("systemctl restart astrbot")
        log("AstrBot 没在运行，已重启")
        return
    boot = sh("journalctl -u astrbot --no-pager | grep -n 'AstrBot started' | tail -1 | cut -d: -f1")
    if boot:
        tail = sh(f"journalctl -u astrbot --no-pager | tail -n +{boot} | grep -c 'Connected to MCP server dafeiyu'")
        started_long_ago = int(sh("systemctl show astrbot -p ActiveEnterTimestampMonotonic --value") or 0) / 1e6 \
            < float(sh("cut -d' ' -f1 /proc/uptime") or 0) - 120
        last_fix = state.get("mcp_restart_at")
        if tail == "0" and started_long_ago and (not last_fix or now - dt.datetime.fromisoformat(last_fix) > dt.timedelta(hours=1)):
            state["mcp_restart_at"] = now.isoformat()
            sh("systemctl restart astrbot")
            log("MCP 工具箱没连上，已重启 AstrBot")
    def _unsent(p):
        try:
            return not json.loads(p.read_text(encoding="utf-8")).get("sent")
        except Exception:
            return False
    pending = sum(1 for p in (HOME / "images").glob("*.json") if _unsent(p))
    if pending < 6 and not sh("pgrep -f 'python /root/dafeiyu-mcp/fetch_[i]mages'"):
        subprocess.Popen(["/root/.local/share/uv/tools/astrbot/bin/python", str(HOME / "fetch_images.py")],
                         stdout=open(HOME / "fetch.log", "a"), stderr=subprocess.STDOUT)
        log(f"图库只剩 {pending} 张，已开始补货")
    use = int(sh("df --output=pcent / | tail -1 | tr -dc 0-9") or 0)
    if use > 90:
        sh("find /root/astrbot/data/temp -name 'dafeiyu_*' -mtime +3 -delete")
        log(f"磁盘 {use}%，已清理 3 天前的临时图片")


def trim(path: pathlib.Path, keep: int = 500):
    """日志只留最后 keep 行，防止越写越大。"""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        if len(lines) > keep:
            path.write_text("\n".join(lines[-keep:]) + "\n", encoding="utf-8")
    except FileNotFoundError:
        pass


def main():
    state = load_state()
    errors = []
    # 每一步单独兜底：某一步出错只记下来，不影响其他步骤，也不会让整个看门狗崩掉
    for step in (record_retry_runs, check_pushes, self_heal):
        try:
            step(state)
        except Exception as e:
            errors.append(f"{step.__name__}: {type(e).__name__}: {str(e)[:120]}")
    if errors:
        log("看门狗自身出错（其他步骤照常）：" + " | ".join(errors))
    cutoff = now - dt.timedelta(days=3)
    state["retried"] = {k: v for k, v in state.get("retried", {}).items()
                        if dt.datetime.fromisoformat(v["when"]) > cutoff}
    state["heartbeat"] = now.isoformat()          # 服务器日报看这个判断看门狗是否还活着
    state["last_errors"] = errors
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    trim(LOG)
    trim(HOME / "watchdog.cron.log")


if __name__ == "__main__":
    main()
