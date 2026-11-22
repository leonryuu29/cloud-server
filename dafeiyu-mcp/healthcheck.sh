#!/usr/bin/env bash
# 大肥鱼全面体检：只读，不改任何东西
PY=/root/.local/share/uv/tools/astrbot/bin/python
echo "== 服务"; systemctl is-active astrbot; systemctl is-enabled astrbot; systemctl is-active cron
echo "== 资源"; free -h | head -2; df -h / | tail -1
echo "== cron 文件"; for f in /etc/cron.d/astrbot-backup /etc/cron.d/dafeiyu-images /etc/cron.d/dafeiyu-music; do echo "$f: $(cat $f)"; done
echo "== 图库"; echo "未发: $(grep -L '"sent": true' /root/dafeiyu-mcp/images/*.json 2>/dev/null | wc -l) 张 / 共 $(ls /root/dafeiyu-mcp/images/*.json | wc -l)"
echo "== 备份"; ls -lt /root/backups | head -4
echo "== 数据"; wc -l /root/dafeiyu-mcp/data/*.csv
echo "== 敏感文件权限"; ls -l /root/dafeiyu-mcp/config.json /root/dafeiyu-mcp/netease_session.txt; stat -c '%a %n' /root/dafeiyu-mcp
echo "== temp 目录大小"; du -sh /root/astrbot/data/temp
echo "== 定时任务"
python3 - <<'EOF'
import sqlite3
for r in sqlite3.connect("file:/root/astrbot/data/data_v4.db?mode=ro", uri=True).execute(
        "select name, cron_expression, timezone, enabled, status, next_run_time, last_error from cron_jobs order by next_run_time"):
    print(r)
EOF
echo "== 近 6 小时报错（按类型）"
journalctl -u astrbot --since -6h --no-pager | grep ERRO | sed -E 's/.*\[(ERRO)\] \[[^]]*\] \[([^]]*)\]: (.{0,90}).*/\2: \3/' | sort | uniq -c | sort -rn | head -12
echo "== 工具冒烟测试"
cd /root/dafeiyu-mcp && $PY - <<'EOF' 2>&1 | grep -v 'HTTP Request'
import server as s
for name, fn in [("server_status", lambda: s.server_status()), ("chat_history", lambda: s.chat_history("today")),
                 ("music_taste", lambda: s.music_taste()), ("music_daily", lambda: s.music_daily()),
                 ("bili_updates", lambda: s.bili_updates(only_new=False, hours=24*365)),
                 ("mail_scan(只看不推进)", lambda: f"{len(s._mail_scan(advance=False)[0])} 封待处理")]:
    try:
        out = fn(); print(f"[OK] {name}: {out.splitlines()[0][:80]}")
    except Exception as e:
        print(f"[FAIL] {name}: {e}")
EOF

# 看门狗心跳
/root/.local/share/uv/tools/astrbot/bin/python - <<'PYEOF'
import json, datetime as dt
s = json.load(open("/root/dafeiyu-mcp/watchdog_state.json"))
age = (dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(s["heartbeat"])).total_seconds() / 60
print(("[OK]" if age < 25 and not s.get("last_errors") else "[!!]"), f"watchdog: {age:.0f} 分钟前巡检，自身错误 {len(s.get('last_errors', []))} 个")
PYEOF

# 邮件门铃：邮箱能不能登录、上次叫醒大肥鱼是什么时候
/root/.local/share/uv/tools/astrbot/bin/python - <<'PYEOF'
import sys, json, pathlib; sys.path.insert(0, "/root/dafeiyu-mcp")
import server
try:
    f, s = server._mail_scan(advance=False)
    st = pathlib.Path("/root/dafeiyu-mcp/mail_check_state.json")
    last = json.loads(st.read_text()).get("at", "?")[:16] if st.exists() else "还没叫醒过"
    print(f"[OK] mail: 登录正常，待处理新邮件 {len(f)} 封，上次叫醒 {last}")
except Exception as e:
    print("[FAIL] mail:", str(e)[:100])
PYEOF
