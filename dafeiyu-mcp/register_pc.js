// Register dafeiyu MCP (over ssh, role=pc) in Codex and Claude Desktop. Backs up both configs first.
const fs = require("fs"), path = require("path"), os = require("os"), { execSync } = require("child_process");
const home = os.homedir();
const ssh = execSync("where ssh").toString().split(/\r?\n/)[0].trim();
const remote = "DAFEIYU_ROLE=pc /root/.local/share/uv/tools/astrbot/bin/python /root/dafeiyu-mcp/server.py";
const args = ["-o", "BatchMode=yes", "-o", "ServerAliveInterval=30", "ecs", remote];
const stamp = new Date().toISOString().replace(/[:.]/g, "-");
console.log("ssh:", ssh);

// Codex: ~/.codex/config.toml
const codex = path.join(home, ".codex", "config.toml");
let t = fs.readFileSync(codex, "utf8");
fs.copyFileSync(codex, codex + ".bak-" + stamp);
if (t.includes("[mcp_servers.dafeiyu]")) {
  console.log("codex: already registered");
} else {
  const q = s => JSON.stringify(s);
  t += `\n[mcp_servers.dafeiyu]\ncommand = ${q(ssh)}\nargs = [${args.map(q).join(", ")}]\nstartup_timeout_sec = 30\ntool_timeout_sec = 120\n`;
  fs.writeFileSync(codex, t, "utf8");
  console.log("codex: registered");
}

// Claude Desktop: %APPDATA%/Claude/claude_desktop_config.json
const cd = path.join(process.env.APPDATA, "Claude", "claude_desktop_config.json");
fs.copyFileSync(cd, cd + ".bak-" + stamp);
const cfg = JSON.parse(fs.readFileSync(cd, "utf8"));
cfg.mcpServers = cfg.mcpServers || {};
cfg.mcpServers.dafeiyu = { command: ssh, args };
fs.writeFileSync(cd, JSON.stringify(cfg, null, 2), "utf8");
console.log("claude desktop: registered; servers =", Object.keys(cfg.mcpServers).join(", "));
