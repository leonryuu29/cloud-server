"""从 stdin 读两行：QQ 邮箱地址、授权码。先试登录，成功才写进 config.json（600），并自动找出 Gmail 代收文件夹。授权码不打印。"""
import imaplib, json, os, re, sys

CONFIG = "/root/dafeiyu-mcp/config.json"
lines = sys.stdin.read().splitlines()
user, pwd = lines[0].strip(), lines[1].strip().replace(" ", "")


def utf7(name: str) -> str:
    def dec(m):
        s = m.group(1)
        return "&" if not s else ("+" + s.replace(",", "/") + "-").encode().decode("utf-7")
    return re.sub(r"&([^-]*)-", dec, name)


HOSTS = {"qq.com": "imap.qq.com", "foxmail.com": "imap.qq.com", "web.de": "imap.web.de",
         "gmx.de": "imap.gmx.net", "gmx.net": "imap.gmx.net", "163.com": "imap.163.com"}
host = HOSTS.get(user.rsplit("@", 1)[-1].lower())
if not host:
    print("不认识这个邮箱后缀，请用完整地址，比如 xxx@web.de"); sys.exit(1)

try:
    M = imaplib.IMAP4_SSL(host, 993, timeout=30)
    M.login(user, pwd)
except Exception as e:
    print("登录失败：", str(e)[:120])
    print("检查：邮箱地址是否写全（xxx@web.de）、设置里「POP3- und IMAP-Zugriff erlauben」是否打开、密码是否正确"
          "（WEB.DE 开了两步验证的话要用「Anwendungsspezifisches Passwort」）。")
    sys.exit(1)

folders = []
for raw in M.list()[1]:
    raw = raw.decode()
    name = raw.rsplit(' "/" ', 1)[-1].strip().strip('"')
    folders.append((name, utf7(name)))
M.logout()

picked = ["INBOX"] + [n for n, d in folders if "gmail" in d.lower()]
cfg = json.load(open(CONFIG, encoding="utf-8"))
cfg["mail"] = {"host": host, "user": user, "password": pwd, "folders": picked}
json.dump(cfg, open(CONFIG, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
os.chmod(CONFIG, 0o600)
print("登录成功，已保存（授权码只存在服务器 config.json 里，权限 600）。")
print("邮箱里的文件夹：", "、".join(d for _, d in folders))
print("大肥鱼会检查：", "、".join(utf7(n) for n in picked))
