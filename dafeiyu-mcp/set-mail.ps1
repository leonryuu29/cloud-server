# Set up the mailbox (WEB.DE / GMX / QQ) for dafeiyu. The password is typed here, sent over SSH, never shown or saved on this PC.
$user = Read-Host "Mail address (e.g. name@web.de)"
$sec  = Read-Host "Mail password (input hidden)" -AsSecureString
$pwd  = [Runtime.InteropServices.Marshal]::PtrToStringBSTR([Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec))
"$user`n$pwd" | ssh -o BatchMode=yes ecs "/root/.local/share/uv/tools/astrbot/bin/python /root/dafeiyu-mcp/set_mail.py"
$pwd = $null
Read-Host "Press Enter to close"
