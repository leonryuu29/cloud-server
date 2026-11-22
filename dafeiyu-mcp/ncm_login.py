"""网易云扫码登录：生成二维码图片 -> 等主人用网易云 App 扫码确认 -> 把登录态保存到服务器（权限 600）。
用法：python ncm_login.py   （会一直等，最多 5 分钟；状态写到 ncm_login.status）"""
import pathlib
import time

import pyncm
import qrcode
from pyncm.apis import login

HOME = pathlib.Path("/root/dafeiyu-mcp")
SESSION = HOME / "netease_session.txt"
STATUS = HOME / "ncm_login.status"
QR = HOME / "netease_qr.png"


def status(s):
    STATUS.write_text(s, encoding="utf-8")
    print(s, flush=True)


uuid = login.LoginQrcodeUnikey()["unikey"]
url = f"https://music.163.com/login?codekey={uuid}"
img = qrcode.make(url)
img = img.resize((600, 600))
img.save(QR)
status("WAITING_SCAN")
deadline = time.time() + 300
last = None
while time.time() < deadline:
    r = login.LoginQrcodeCheck(uuid)
    code = r.get("code")
    if code != last:
        status({800: "EXPIRED", 801: "WAITING_SCAN", 802: "SCANNED_WAIT_CONFIRM", 803: "SUCCESS"}.get(code, f"CODE_{code}"))
        last = code
    if code == 803:
        login.WriteLoginInfo(login.GetCurrentLoginStatus())
        SESSION.write_text(pyncm.DumpSessionAsString(pyncm.GetCurrentSession()), encoding="utf-8")
        SESSION.chmod(0o600)
        prof = login.GetCurrentLoginStatus().get("profile") or {}
        status(f"SUCCESS uid={prof.get('userId')} nickname={prof.get('nickname')}")
        break
    if code == 800:
        break
    time.sleep(2)
else:
    status("TIMEOUT")
QR.unlink(missing_ok=True)
