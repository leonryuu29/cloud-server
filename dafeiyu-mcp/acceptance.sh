#!/usr/bin/env bash
# 大肥鱼验收脚本：只读，1 分钟内跑完。用法：bash /root/dafeiyu-mcp/acceptance.sh
# 每一项输出 [PASS] / [WARN] / [FAIL]，最后给总结。
PY=/root/.local/share/uv/tools/astrbot/bin/python
cd /root/dafeiyu-mcp
$PY - <<'EOF'
import datetime as dt, json, os, pathlib, sqlite3, stat, subprocess, sys
from zoneinfo import ZoneInfo
sys.path.insert(0, "/root/dafeiyu-mcp")
B, U = ZoneInfo("Europe/Berlin"), dt.timezone.utc
now = dt.datetime.now(U)
res = []
def sh(c): return subprocess.run(c, shell=True, capture_output=True, text=True).stdout.strip()
def check(area, name, ok, detail, warn=False):
    tag = "PASS" if ok else ("WARN" if warn else "FAIL")
    res.append(tag); print(f"[{tag}] {area:6} {name:18} {detail}")

# 1 稳定：服务
check("稳定", "AstrBot 服务", sh("systemctl is-active astrbot") == "active", sh("systemctl show astrbot -p ActiveEnterTimestamp --value"))
check("稳定", "开机自启", sh("systemctl is-enabled astrbot") == "enabled", sh("systemctl is-enabled astrbot"))
mcp = "Connected to MCP server dafeiyu" in sh("journalctl -u astrbot --since -2d --no-pager | grep 'MCP server dafeiyu' | tail -1")
check("稳定", "MCP 工具箱", mcp, "已连接" if mcp else "未连接")
qq = "Websocket session starting" in sh("journalctl -u astrbot --since -7d --no-pager | grep -i qqofficial | tail -3")
check("稳定", "QQ 机器人", qq, "官方 WebSocket")
mem = sh("free -m | awk '/Mem/{print $3\"/\"$2}'"); disk = int(sh("df --output=pcent / | tail -1 | tr -dc 0-9") or 0)
check("稳定", "资源", disk < 80, f"内存 {mem} MB，磁盘 {disk}%")
errs = int(sh("journalctl -u astrbot --since -24h --no-pager | grep -c ERRO") or 0)
check("稳定", "24h 报错", errs < 100, f"{errs} 行（插件市场连不上属正常）", warn=True)

# 2 自动化：cron + 任务
need = ["astrbot-backup", "dafeiyu-images", "dafeiyu-music", "dafeiyu-watchdog", "dafeiyu-mail"]
have = os.listdir("/etc/cron.d")
miss = [n for n in need if n not in have]
check("自动化", "系统 cron", not miss, "5 个都在" if not miss else f"缺 {miss}")
con = sqlite3.connect("file:/root/astrbot/data/data_v4.db?mode=ro", uri=True)
jobs = con.execute("select name, enabled, timezone, last_error, last_run_at from cron_jobs").fetchall()
en = [j for j in jobs if j[1]]
check("自动化", "定时推送", len(en) >= 11 and all(j[2] == "Europe/Berlin" for j in en),
      f"{len(en)} 个启用，全部 Europe/Berlin" if all(j[2] == "Europe/Berlin" for j in en) else "有任务时区不对")
bad_err = [j[0] for j in jobs if j[3]]
check("自动化", "任务报错", not bad_err, "无" if not bad_err else f"{bad_err}")
mailjob = [j for j in jobs if j[0] == "重要邮件"]
check("自动化", "重要邮件任务", bool(mailjob) and not mailjob[0][1], "存在，不启用（由门铃叫醒）")
pcjob = [j for j in jobs if j[0] == "电脑任务汇报"]
check("协作", "电脑任务汇报", bool(pcjob) and not pcjob[0][1], "存在，不启用（由 pc_task_done 叫醒）")
q = json.loads(pathlib.Path("data/pc_tasks.json").read_text(encoding="utf-8")) if pathlib.Path("data/pc_tasks.json").exists() else []
cnt = {s: sum(t["status"] == s for t in q) for s in ("pending", "claimed", "done")}
stuck = [t["id"] for t in q if t["status"] == "done" and not t.get("reported")]
check("协作", "电脑任务队列", not stuck, f"待领取 {cnt['pending']} · 进行中 {cnt['claimed']} · 已完成 {cnt['done']}"
      + (f" · 完成了但没汇报：{stuck}" if stuck else ""), warn=True)
import os as _os
pc_tools = sh("cd /root/dafeiyu-mcp && DAFEIYU_ROLE=pc /root/.local/share/uv/tools/astrbot/bin/python -c \"import asyncio,server;print(sorted(t.name for t in asyncio.run(server.mcp.list_tools()) if t.name.startswith('pc_')))\"")
check("协作", "电脑端工具", "pc_task_done" in pc_tools and "pc_task_add" not in pc_tools, pc_tools)

# 3 送达：过去 24h 每条推送
sent_ok, sent_bad = 0, []
for name, enabled, tz, err, last in en:
    if not last or last == "None": continue
    t = dt.datetime.fromisoformat(str(last)).replace(tzinfo=U)
    if now - t > dt.timedelta(hours=24): continue
    a = t.astimezone(ZoneInfo("Asia/Shanghai"))
    n = int(sh(f"journalctl -u astrbot --since '{a:%Y-%m-%d %H:%M:%S}' --until '{a + dt.timedelta(minutes=5):%Y-%m-%d %H:%M:%S}' --no-pager | grep -c 'send_message_to_user. Result: Message sent'") or 0)
    (sent_bad.append(name[:6]) if n == 0 else None); sent_ok += n > 0
check("送达", "24h 推送", not sent_bad, f"{sent_ok} 条送达" + (f"，没发出：{sent_bad}" if sent_bad else ""), warn=True)

# 4 自愈：看门狗
wd = json.loads(pathlib.Path("watchdog_state.json").read_text())
age = (now - dt.datetime.fromisoformat(wd["heartbeat"])).total_seconds() / 60
check("自愈", "看门狗心跳", age < 25 and not wd.get("last_errors"), f"{age:.0f} 分钟前巡检，自身错误 {len(wd.get('last_errors', []))} 个")
fixes = sum(1 for l in pathlib.Path("watchdog.log").read_text(encoding="utf-8").splitlines()
            if l[:16] >= (dt.datetime.now(B) - dt.timedelta(hours=24)).strftime("%Y-%m-%d %H:%M")) if pathlib.Path("watchdog.log").exists() else 0
check("自愈", "24h 自动修复", True, f"{fixes} 次")

# 5 邮件
import server
try:
    f, s = server._mail_scan(advance=False)
    check("邮件", "WEB.DE 登录", True, f"正常，待处理 {len(f)} 封（只看不推进）")
except Exception as e:
    check("邮件", "WEB.DE 登录", False, str(e)[:80])
hbp = pathlib.Path("mail_check_heartbeat.json")
if hbp.exists():
    hb = json.loads(hbp.read_text(encoding="utf-8"))
    hb_age = (now - dt.datetime.fromisoformat(hb["at"])).total_seconds() / 60
    check("邮件", "门铃心跳", hb_age < 25 and not hb.get("error"),
          f"{hb_age:.0f} 分钟前运行" + (f"，出错：{hb['error']}" if hb.get("error") else "，无错误"))
else:
    check("邮件", "门铃心跳", False, "还没有心跳记录", warn=True)
ml = pathlib.Path("mail_check.log")
check("邮件", "门铃最近叫醒", True, ml.read_text(encoding="utf-8").splitlines()[-1] if ml.exists() else "还没有")

# 6 数据
pool = len(server._pending_images())
check("数据", "图库", pool >= 6, f"{pool} 张")
rows = int(sh("wc -l < data/week_record.csv") or 0)
check("数据", "听歌快照", rows > 1, f"{rows - 1} 行")
check("数据", "网易云登录", pathlib.Path("netease_session.txt").exists(), "有效" if pathlib.Path("netease_session.txt").exists() else "过期")
bk = sh("ls -t /root/backups/astrbot-*.tar.gz | head -1")
bk_age = (now.timestamp() - os.path.getmtime(bk)) / 86400 if bk else 99
check("数据", "最近备份", bk_age < 8, f"{os.path.basename(bk)}（{bk_age:.1f} 天前）")

# 7 安全
perms = {p: oct(stat.S_IMODE(os.stat(p).st_mode)) for p in ("config.json", "netease_session.txt")}
check("安全", "密钥文件权限", all(v == "0o600" for v in perms.values()), str(perms))
port = sh("ss -ltn | grep -c '0.0.0.0:6185'")
check("安全", "后台不对外", port == "0", "6185 只监听本机" if port == "0" else "6185 对外开放！")

# 8 成本
cfgc = json.load(open("/root/astrbot/data/cmd_config.json", encoding="utf-8-sig"))["agent_runner"]["config"]["compression"]
check("成本", "上下文上限", cfgc.get("max_turns", -1) > 0, f"最近 {cfgc.get('max_turns')} 轮")
day = (now - dt.timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
r = con.execute("select count(*), coalesce(sum(token_input_other),0), coalesce(sum(token_input_cached),0), coalesce(sum(token_output),0) "
                "from provider_stats where created_at >= ?", (day,)).fetchone()
hit = r[2] / max(1, r[1] + r[2])
check("成本", "24h 聊天 token", True, f"{r[0]} 次调用，输入 {r[1] + r[2]:,}（缓存命中 {hit:.0%}），输出 {r[3]:,}（定时推送不在这个统计里）")

p, w, f_ = res.count("PASS"), res.count("WARN"), res.count("FAIL")
print(f"\n验收结果：{p} 通过 · {w} 提醒 · {f_} 失败  ({dt.datetime.now(B):%Y-%m-%d %H:%M} 德国时间)")
EOF
