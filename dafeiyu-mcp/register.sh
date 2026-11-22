#!/usr/bin/env bash
set -euo pipefail
cd /root/dafeiyu-mcp
chmod 700 /root/dafeiyu-mcp
[ -f config.json ] || echo '{"bili_ups": []}' > config.json
chmod 600 config.json
cp /root/astrbot/data/mcp_server.json /root/astrbot/data/mcp_server.json.bak
python3 - <<'EOF'
import json
p = "/root/astrbot/data/mcp_server.json"
d = json.load(open(p, encoding="utf-8-sig"))
d.setdefault("mcpServers", {})["dafeiyu"] = {
    "command": "/root/.local/share/uv/tools/astrbot/bin/python",
    "args": ["/root/dafeiyu-mcp/server.py"],
    "active": True,
}
json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=4)
print(open(p).read())
EOF
# 图库每 4 小时补货一次
echo '17 */4 * * * root /root/.local/share/uv/tools/astrbot/bin/python /root/dafeiyu-mcp/fetch_images.py >> /root/dafeiyu-mcp/fetch.log 2>&1' > /etc/cron.d/dafeiyu-images
chmod 644 /etc/cron.d/dafeiyu-images
systemctl restart astrbot
sleep 20
systemctl is-active astrbot
journalctl -u astrbot --since '-1 min' --no-pager | grep -iE 'mcp|dafeiyu|ERRO' | cut -c60-300 | tail -12
