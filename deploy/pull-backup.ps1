# Dafeiyu (AstrBot) backup: make a fresh backup on the server, download it here.
# Run weekly (Sunday 12:00) by the Windows scheduled task; missed runs catch up after boot.
$dir  = 'C:\Users\1\Documents\dafeiyu-backup'
$keep = 12
$log  = Join-Path $dir 'backup.log'
$name = 'astrbot-' + (Get-Date -Format 'yyyyMMdd-HHmm') + '.tar.gz'
$out  = Join-Path $dir $name

& ssh -o BatchMode=yes -o ConnectTimeout=20 ecs '/usr/local/bin/astrbot-backup' *>> $log
& scp -o BatchMode=yes -o ConnectTimeout=20 'ecs:/root/backups/latest.tar.gz' $out *>> $log

if ((Test-Path $out) -and ((Get-Item $out).Length -gt 0)) {
    Add-Content $log "$(Get-Date -Format s) OK $name"
    Get-ChildItem $dir -Filter 'astrbot-*.tar.gz' | Sort-Object LastWriteTime -Descending |
        Select-Object -Skip $keep | Remove-Item -Force
} else {
    Add-Content $log "$(Get-Date -Format s) FAILED"
}
