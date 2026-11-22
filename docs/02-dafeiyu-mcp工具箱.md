# dafeiyu-mcp · 大肥鱼的 MCP 工具箱

> 自己写的第一个 MCP 服务（2026-11-22）。代码：本地 `T:\云服务器\dafeiyu-mcp\`，服务器 `/root/dafeiyu-mcp/`。
> 已接入 AstrBot（`/root/astrbot/data/mcp_server.json` 里的 `dafeiyu`），以后也可以接给 Claude Code / Codex。

## 工具（大肥鱼看到 21 个；电脑端 Codex/Claude 只看到 7 个：服务器状态 ×2、聊天记录、新邮件、任务 ×3）
| 工具 | 作用 | 状态 |
|---|---|---|
| `daily_report` | **大肥鱼日报**长图：消息数/最早/最晚/字数、24 小时分布、高峰时段（代码算）+ 做了/学了/聊了/状态/点评（AI 写）+ 服务器状态条 | ✅ |
| `chat_history` | 读某天（德国日期）QQ 聊天记录 | ✅ |
| `music_taste` | 网易云口味画像：我喜欢 4913 首的歌手/语种/年代 + 所有时间/最近一周排行（一周缓存一次） | ✅ |
| `music_daily` | 今日每日推荐 ~30 首（带序号）+ 推荐理由 + 语种 + 是否收藏过的歌手 | ✅ |
| `music_report_card` | **网易云品鉴**卡：吻合度、风格分布、语种分布、今日必听 5 首、可跳过、点评 | ✅ |
| `music_style_card` | **30 首风格地图**卡：每首按风格分组，每组写适合什么时候听，收藏过的歌手打 ★ | ✅ |
| `daily_gallery` / `anime_image` | 今日画廊 15 张拼图 / 临时一张 | ✅ |
| `server_status` / `server_metrics` / `render_card` | 服务器状态、通用文字卡片 | ✅ |
| `bili_*` | B 站搜索/关注/更新（B 站推送已放弃，工具保留） | 闲置 |
| `server_report` | **服务器日报**卡：资源圆环、服务灯（含看门狗心跳）、过去 24h 每条推送 √已送达 / 已补发 / ×没发出、自动修复次数 | ✅ |
| `gallery_images` | 画廊：图和点评一张张单独发 | ✅ |
| `new_emails` | WEB.DE（代收 Gmail）上次之后的新邮件：只认 48 小时内的、一次最多 15 封、加锁、不标已读；电脑端身份只看不推进 | ✅ |
| `pc_task_add` / `pc_task_status` / `pc_task_report` | **大肥鱼用**：把事交给电脑 / 查进度 / 取完成结果 | ✅ |
| `pc_task_list` / `pc_task_claim` / `pc_task_done` | **电脑 Codex/Claude 用**（`DAFEIYU_ROLE=pc`）：看任务 / 领取 / 交结果（交完自动叫醒大肥鱼汇报） | ✅ |

## 网易云
- 账号 （网易云账号），扫码登录一次，登录态 `netease_session.txt`（600），**只读**：每日推荐、听歌排行、我喜欢
- 库：开源的 [pyncm](https://github.com/mos9527/pyncm)（帮我们做接口加密）；自己写的调用：每日推荐 `/weapi/v3/discovery/recommend/songs`、排行 `/weapi/v1/play/record`、我喜欢 `/weapi/song/like/get`
- 登录不是永久的（一般几个月），过期了重新跑 `ncm_login.py` 扫码
- 统计方式：口味画像用 Python 自带的 `collections.Counter` 做简单计数，一周算一次缓存到 `music_profile.json`；每天只拉 30 首推荐对比
- **数据采集**：`music_snapshot.py` 每天德国 23:10 存一份「最近一周排行」和「每日推荐」到 `data/*.csv`，给以后的 pandas 口味周报用

## 图库
- 图源 **Safebooru**（全年龄，北京直连快），每个角色按收藏分排序只取前 200 张，去重由代码做（不花 token）
- 角色（config.json `image_tags`，带权重）：结月缘 3 · 琉·利昂 2 · 夏目安安 2 · 魔女裁判 1
- `fetch_images.py` cron 每 4 小时补货，保持 20 张

## 文件
| 文件 | 说明 |
|---|---|
| `server.py` | 主程序，每个 `@mcp.tool()` 是一个工具，函数下面的中文注释是给大肥鱼看的「说明书」 |
| `ncm.py` / `ncm_login.py` / `music_snapshot.py` | 网易云接口 / 扫码登录 / 每日快照 |
| `report.py` / `music_card.py` / `style_map.py` / `cards.py` | 画日报 / 品鉴卡 / 风格地图 / 画廊和通用卡片（Pillow，字体 wqy-microhei，不支持 emoji） |
| `bili.py` / `fetch_images.py` | B 站 / 图库 |
| `healthcheck.sh` / `register.sh` | 体检 / 注册进 AstrBot |
| `watchdog.py` | 看门狗（**不是 MCP 工具**，系统 cron 每 10 分钟跑）：补发没送达的推送、重启、补货、清理；`server_report` 会读它的心跳和修复记录 |
| `set_mail.py` | 配邮箱：从电脑 `set-mail.ps1` 接收地址和密码，按后缀选 IMAP 服务器，试登录成功才写入 config.json |
| `mail_check.py` | 邮件门铃（**不是 MCP 工具**，系统 cron 每小时）：只看不推进，有 48 小时内的新邮件才叫醒「重要邮件」任务 |
| `dev-history/` | 开发过程的测试和补丁脚本 |
| 服务器上才有（不进 Git）| `config.json` `netease_session.txt` `state.json` `music_profile.json` `images/` `data/` |

## 下一步
- pandas 口味周报（数据攒满两周后）
- 接 Claude Code：MCP 命令 `ssh ecs /root/.local/share/uv/tools/astrbot/bin/python /root/dafeiyu-mcp/server.py`

## 网络情况（北京服务器）
网易云 ✅ ｜ B 站 API ⚠️ 风控 ｜ Safebooru ✅ ｜ pixiv 代理极慢 ｜ danbooru/yande.re/konachan ❌ ｜ Gmail IMAP ⚠️ 时通时断（3 次通 1 次）｜ QQ/163/Outlook/GMX/WEB.DE IMAP ✅ ｜ pypi：腾讯云镜像 ✅、清华 403、阿里云缺包
