# MCP 开发详解 · dafeiyu-mcp 是怎么写出来的

> 这篇讲「给 AI 用的工具」怎么写。不用 AI 的后台程序（看门狗、邮件门铃）怎么写 → `08-看门狗与邮件门铃开发详解.md`

## 1. MCP 是什么
**MCP（Model Context Protocol）** = 给 AI 用的「工具插座」标准。
- AI（DeepSeek）本身只会说话，不会去读网易云、不会画图
- 我们写一个 **MCP 服务器**，里面放一堆「工具」（Python 函数），每个工具带一段**说明书**
- AstrBot（**MCP 客户端**）启动时会问 MCP 服务器：「你有哪些工具？」，然后把工具清单和说明书交给 DeepSeek
- DeepSeek 聊天时觉得需要，就说「我要调用 music_daily」，AstrBot 去执行函数，把结果再交还给 DeepSeek

```
主人 / 定时任务 ──► AstrBot ──「有哪些工具？」──► dafeiyu-mcp
                        │◄──── 工具清单 + 说明书 ────┘
                        ▼
                    DeepSeek：「我要调 music_daily」
                        │
AstrBot ──「执行 music_daily()」──► dafeiyu-mcp ──► 网易云 API
        ◄──── 返回 30 首歌的文字 ────┘
                        ▼
                    DeepSeek 分析，再调 music_report_card 画图 → 发给主人
```
同一个 MCP 服务器，Claude Code / Codex 也能接，因为它们都说「MCP」这门语言。

## 2. 它们之间怎么通信：stdio
`mcp_server.json` 里写的是一条命令：
```json
"dafeiyu": {"command": "/root/.local/share/uv/tools/astrbot/bin/python",
            "args": ["/root/dafeiyu-mcp/server.py"], "active": true}
```
AstrBot 启动时**把 server.py 当子进程跑起来**，通过它的标准输入/输出（stdin/stdout）互相发 JSON 消息。
所以：**改了 server.py 要 `systemctl restart astrbot`**，AstrBot 才会重新启动这个子进程。
（stdout 被用来通信，所以调试信息只能往 stderr 打，不能随便 `print`。）

## 3. 最小例子
```python
from mcp.server.fastmcp import FastMCP     # 官方 Python SDK 里的简便写法

mcp = FastMCP("dafeiyu")                    # 服务器名字

@mcp.tool()                                 # 这个装饰器 = 「把下面的函数登记成一个工具」
def server_status() -> str:
    """查看云服务器的状态：运行时间、内存、磁盘……"""   # ← 说明书，DeepSeek 靠它决定什么时候用、怎么用
    return "运行时间: 3 小时 ..."              # ← 返回的文字交给 DeepSeek

if __name__ == "__main__":
    mcp.run()                               # 开始用 stdio 等 AstrBot 来调用
```
就这么多。**函数名 = 工具名，参数 = 工具参数（类型注解很重要），docstring = 说明书，返回值 = 结果。**

## 4. 我们的工具是怎么设计的（以网易云为例）
| 层 | 文件 | 干什么 |
|---|---|---|
| 接口层 | `ncm.py` | 只负责从网易云拿数据：`daily_recommend()`、`play_record()`、`liked_songs()` |
| 工具层 | `server.py` 里的 `music_*` | 拼装数据、做统计，返回给 AI 看的文字 |
| 画图层 | `music_card.py`、`style_map.py` | 用 Pillow 把数据画成卡片 |
| 任务层 | AstrBot 未来任务 | 每晚 23:05 告诉 DeepSeek：「先调 A，再调 B，最后画图发给主人」 |

**分工原则**（省 token 又准确）：
- **能用代码算的，绝不让 AI 算**：消息数、时段分布、语种占比、收藏过的歌手 → 代码统计
- **需要「理解」的才交给 AI**：这首歌什么风格、哪首值得听、点评 → DeepSeek 写
- **大数据先压缩**：4913 首「我喜欢」不会喂给 AI，先用 `Counter` 统计成「最常收藏的 25 个歌手」，一周算一次缓存

## 5. 网易云接口是怎么调的
- 网易云网页版的接口叫 **weapi**，请求内容要加密（AES + RSA），自己实现很麻烦
- 开源库 **pyncm** 已经实现了加密，还提供了一些现成函数（比如登录、查歌曲详情）
- 它**没有**「每日推荐」「听歌排行」的函数，所以我们自己写，套用它的加密装饰器：
```python
from pyncm.apis import WeapiCryptoRequest

@WeapiCryptoRequest                       # 这个装饰器帮我们加密、发请求、解析结果
def _daily():
    return "/weapi/v3/discovery/recommend/songs", {}    # 只要告诉它：接口路径 + 参数
```
- **扫码登录**：pyncm 提供了「申请二维码 key」和「查扫码状态」两个接口；
  二维码图片生成（`qrcode` 库）、轮询等待、把登录态存成文件（权限 600）是 `ncm_login.py` 我们自己写的
- 登录态（cookie）存在 `netease_session.txt`，每次调用前 `ensure_login()` 读进来

## 6. 画图（Pillow）
所有卡片都是同一个套路：
```python
im = Image.new("RGB", (宽, 高), 背景色)        # 新建画布
d = ImageDraw.Draw(im)
d.rounded_rectangle((x0, y0, x1, y1), 圆角, fill=颜色)   # 画圆角卡片 / 进度条
d.text((x, y), "文字", font=ImageFont.truetype(字体, 字号), fill=颜色)
im.save("xxx.png")
```
难点只有两个：**先算好总高度**（文字要按宽度自动换行，`wrap()` 函数）、**中文字体**（装了 `fonts-wqy-microhei`，它没有 emoji，所以说明书里都写了「不要用 emoji」）。
图片存到 `/root/astrbot/data/temp/`，因为 AstrBot 只允许发送这个目录里的本地文件。

## 7. 怎么加一个新工具（练习）
1. 在 `server.py` 里写一个函数，加 `@mcp.tool()`，写清楚 docstring
2. 先在服务器上直接测：`python -c "import server; print(server.你的函数())"`
3. `systemctl restart astrbot`，看日志里 `Connected to MCP server dafeiyu, Tools: [...]` 有没有它
4. 在 QQ 里让大肥鱼用一下；要定时就在未来任务里写进去

## 8. healthcheck.sh 在干嘛（逐段解释）
| 段落 | 命令 | 含义 |
|---|---|---|
| 服务 | `systemctl is-active astrbot` | AstrBot 在不在跑（active = 正常） |
| 资源 | `free -h` / `df -h /` | 内存、磁盘还剩多少 |
| cron | `cat /etc/cron.d/...` | 三个后台定时脚本的配置 |
| 图库 | 数 `images/*.json` 里没发过的 | 画廊存货够不够 |
| 备份 | `ls -lt /root/backups` | 最近一次备份是什么时候 |
| 数据 | `wc -l data/*.csv` | 听歌快照攒了多少行 |
| 权限 | `ls -l config.json ...` | 放密码的文件是不是 600（只有 root 能读） |
| 定时任务 | 用 Python 读 AstrBot 数据库的 `cron_jobs` 表 | 每个任务的时间、时区、下次运行时间、上次错误 |
| 报错 | `journalctl ... | grep ERRO | sort | uniq -c` | 最近 6 小时的报错按类型计数 |
| 冒烟测试 | 直接调用几个工具函数 | 每个工具能不能正常返回（[OK]/[FAIL]） |
| 看门狗 | 读 `watchdog_state.json` | 看门狗心跳是否在 25 分钟内、自身有没有出错 |

跑法：`ssh ecs` 登录后 `bash /root/dafeiyu-mcp/healthcheck.sh`。它只读，不会改任何东西。

## 8.5 看门狗为什么不做成 MCP 工具（完整讲解见 08）
MCP 工具是**给 AI 调用的**：大肥鱼想看什么（日报、画廊、服务器状态）就调哪个工具。如果把“检查并修复”也做成 MCP 工具，会有三个问题：
1. **要 AI 想起来才会调**：大肥鱼要是卡住、掉线，正是它最没法自己调工具的时候
2. **每次检查都要过一遍 DeepSeek**：每 10 分钟一次，一天 144 次，白花 token
3. **修复动作不该让 AI 决定**：重启、重跑这种操作，规则写死比让 AI 判断更可靠（R6：能用代码算的不让 AI 算）

所以看门狗是**站在外面的普通程序**：系统 cron 叫醒它 → 读数据库和日志 → 按写死的规则修 → 写日志 → 退出。和 MCP 的关系只有一处：MCP 工具 `server_report` 会读看门狗的心跳和修复记录，画进服务器日报。

**看门狗调 AstrBot 的方式**：AstrBot 后台有 HTTP 接口（网页后台就是用它的），比如 `POST /api/v1/cron/jobs/{id}/run` 立即执行一个定时任务。接口要登录，看门狗用 AstrBot 配置里的 `jwt_secret` 签一个 JWT 令牌（和网页后台登录后拿到的令牌是同一种），5 分钟过期：
```python
token = jwt.encode({"username": "...", "exp": now + 5min}, jwt_secret, algorithm="HS256")
POST http://127.0.0.1:6185/api/v1/cron/jobs/{id}/run   Header: Authorization: Bearer <token>
```
因为只在服务器本机（127.0.0.1）调用、令牌用完就丢，外面拿不到。

## 8.6 「门铃」模式：便宜的检查 + 贵的判断（以邮件为例）
邮件一天来几十封，绝大多数是广告。如果每小时让大肥鱼自己去翻邮箱，一天 17 次 DeepSeek 调用，大多白花。所以拆成两半：

```
mail_check.py（cron，纯代码）          大肥鱼（AI）
  _mail_scan(advance=False)  ──有新的──►  后台接口 run 「重要邮件」任务
  没有 → 直接退出                          └─ 调 MCP 工具 new_emails（advance=True，推进位置）
                                            └─ 判断重要 → send_message_to_user / 不重要 → 不发
```
- **同一个函数两种模式**：`_mail_scan(advance=False)` 只看（门铃、体检用），`advance=True` 看完把“已读位置”往前推（只有大肥鱼真正处理时用）。这样体检永远不会吞掉邮件
- **位置怎么记**：IMAP 每封邮件有个递增编号 UID，记住“处理到第几号”；再配合邮箱的 UIDVALIDITY（邮箱重建时会变，变了就从头记）
- **为什么还要看日期**：代收服务会把旧邮件陆续搬进来，编号是新的、日期是旧的 → 只认 48 小时内的
- **「重要邮件」任务为什么设成不启用**：它不该按钟点跑，只该被门铃叫醒；AstrBot 的「立即执行」会忽略启用状态（`run_job_now → ignore_enabled=True`），而看门狗只检查启用的任务，所以它“没发消息”不会被当成故障

## 9. 接给 Claude Code / Codex（以后）
因为 MCP 走的是 stdio，而 SSH 也能转发 stdio，所以在电脑上直接用这条命令当 MCP 服务器：
```
ssh ecs /root/.local/share/uv/tools/astrbot/bin/python /root/dafeiyu-mcp/server.py
```
Claude Code 就能调用服务器上的全部工具了。反方向（大肥鱼派活给电脑）需要「任务队列」，以后单独做。
