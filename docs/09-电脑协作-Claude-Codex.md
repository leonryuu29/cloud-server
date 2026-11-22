# 电脑协作 · 大肥鱼 ⇄ Claude / Codex（走 SSH）

> 2026-11-22 上线。代码在 `server.py` 最后一节「电脑协作：任务队列」。测试记录见 `07`。

## 1. 能做什么
| 方向 | 场景 | 怎么用 |
|---|---|---|
| **手机 → 电脑** | 在外面想到一件要在电脑上做的事 | QQ 跟大肥鱼说：「让电脑上的 Claude 帮我……」→ 大肥鱼记进任务队列 |
| **电脑 → 领任务** | 回到电脑前 | 打开 Codex 或 Claude 桌面版，说：「看看大肥鱼有没有给我派任务」→ 它会列出、领取、开始做 |
| **电脑 → 手机** | 电脑做完了 | Claude/Codex 调 `pc_task_done` 填结果 → **服务器马上叫醒大肥鱼 → QQ 告诉你做完了、结果是什么** |
| **电脑读服务器** | 在电脑上想看大肥鱼的数据 | 在 Codex/Claude 里直接问「服务器状态怎么样」「今天的日报」「网易云今天推了什么」「有什么新邮件」 |

## 2. 架构
```
 手机 QQ ─► 大肥鱼（AstrBot，身份 astrbot）
              │ pc_task_add / pc_task_status / pc_task_report
              ▼
      /root/dafeiyu-mcp/data/pc_tasks.json   ← 任务队列（加锁读写，权限 600）
              ▲
              │ pc_task_list / pc_task_claim / pc_task_done
 电脑 Codex / Claude 桌面版
   └─ MCP 命令：ssh ecs "DAFEIYU_ROLE=pc python server.py"   ← 同一个 server.py，换个身份
              │
   pc_task_done ──► 后台接口 /run「电脑任务汇报」──► 大肥鱼调 pc_task_report ──► QQ
```
**关键点：同一个 MCP 服务器，两种身份**
| 身份 | 谁在用 | 能看到的协作工具 | 读邮件 |
|---|---|---|---|
| `astrbot`（默认） | 大肥鱼 | `pc_task_add`、`pc_task_status`、`pc_task_report` | 会推进“已读位置” |
| `pc` | 电脑上的 Codex / Claude | `pc_task_list`、`pc_task_claim`、`pc_task_done`（**一共只有 7 个工具**，见第 8 节） | **只看不推进**（不会抢大肥鱼的邮件） |

身份由环境变量 `DAFEIYU_ROLE` 决定；工具用 `_for("pc")` / `_for("astrbot")` 装饰器按身份注册，另一个身份根本看不到。

## 3. 为什么走 SSH
MCP 用 stdio（标准输入输出）通信，而 `ssh ecs "命令"` 正好把远端程序的输入输出接到本地。所以电脑上的 MCP 客户端以为自己在跑一个本地程序，其实那个程序在北京服务器上跑：
- 不用开新端口（服务器安全组仍然只开 22）
- 用现成的 SSH 密钥认证，不用再搞 API Key
- 每次对话开一个连接，对话结束就断，服务器上不常驻新进程
- 实测连接 3 秒

## 4. 电脑上的配置（已经配好）
**Codex**：`C:\Users\1\.codex\config.toml`
```toml
[mcp_servers.dafeiyu]
command = "C:\\Windows\\System32\\OpenSSH\\ssh.exe"
args = ["-o", "BatchMode=yes", "-o", "ServerAliveInterval=30", "ecs", "DAFEIYU_ROLE=pc /root/.local/share/uv/tools/astrbot/bin/python /root/dafeiyu-mcp/server.py"]
startup_timeout_sec = 30
tool_timeout_sec = 120
```
**Claude 桌面版**：`%APPDATA%\Claude\claude_desktop_config.json` 的 `mcpServers.dafeiyu`（同样的 command 和 args）

- 改之前两个文件都备份了（同目录 `.bak-时间戳`）
- **要重启 Codex / Claude 桌面版才会加载**
- 配置脚本：`dev-history/register_pc.js`（以后重装可以再跑一次）
- 以后装了 Claude Code 命令行：`claude mcp add dafeiyu -- ssh -o BatchMode=yes ecs "DAFEIYU_ROLE=pc /root/.local/share/uv/tools/astrbot/bin/python /root/dafeiyu-mcp/server.py"`

## 5. 一个任务的一生
```
pending（待领取） ──pc_task_claim──► claimed（进行中） ──pc_task_done──► done（已完成）
                                                                    └─► 叫醒大肥鱼 → reported（已汇报）
```
任务记录：`id、title、detail、status、created、agent、claimed、finished、result、reported`

## 6. 安全边界
- 大肥鱼**只能往队列里写字**，不能在电脑上执行任何东西（规则 R8 不变）
- 电脑上真正干活的是你打开的 Codex / Claude，**它们照常会问你要权限**，你在电脑前看得到
- 电脑端身份读邮件只读、看不到 `pc_task_add`（不能自己给自己派活）
- 队列文件 600；任务内容不含密钥

## 7. 省钱
- 队列读写、领取、标记完成：纯代码，不花 token
- 只有“汇报结果”这一步叫醒大肥鱼，一次任务一次
- 电脑这边用的模型由 Codex / Claude 自己的设置决定（你的 Codex 现在用的是 DeepSeek）

## 8. 2026-11-22 的决定：先不做全自动
- **桌面版 vs 命令行版的本质区别**：桌面版（Codex / Claude 客户端）只在有人发消息时才动，不会自己去看队列；命令行版（`claude` / `codex`）能被 Windows 定时任务叫起来，没人打字也能自己读需求、自己干完
- **决定**：不装命令行版、不做无人值守执行。够用的流程是：手机上派活（QQ 给大肥鱼，或直接用手机上的 Claude）→ 电脑上的 Claude 开着并连上 → 跟它说一句“看看大肥鱼的任务” → 做完自动回 QQ
- **token**：电脑端每个新对话会带上工具说明书。实测 21 个约 3,200–4,100 token → **电脑端精简成 7 个**（`server_status`、`server_metrics`、`chat_history`、`new_emails`、`pc_task_list/claim/done`），约 850–1,050 token，省约 75%。画图/网易云/画廊这些是给大肥鱼发 QQ 用的，电脑端用不上。代码：`server.py` 最后的 `PC_KEEP`。大肥鱼仍是 21 个
- **连上 ≠ 消耗**：开对话只建一条闲置 SSH 连接，不调工具不花 token，大肥鱼也不知道
- **流程里只有一步是手动的**：对电脑上的 Claude 说“看看大肥鱼派的任务”。派活进队列、做完后 QQ 汇报都是自动的
- **Codex 的限制**：手机远程控制 Codex 要用 ChatGPT 账号登录（扫码配对），而且对 Windows 支持还在逐步开放；这里的 Codex 用的是 DeepSeek API，所以手机控制不了，只能在电脑前用。手机远程干活用 Claude

## 9. 工作原理总结（2026-11-22 讨论定下来的）
### 9.1 一个任务从头到尾
```
① 派活（自动）   QQ：「让电脑上的 Claude 帮我……」
                 → 大肥鱼调 pc_task_add → 任务写进 data/pc_tasks.json（状态 pending）
② 领活（手动）   在电脑上的 Claude / Codex 里说一句：「看看大肥鱼派的任务」
                 → 它调 pc_task_list 读队列（通过 SSH，走 MCP）→ pc_task_claim 领取（claimed）
③ 干活            它在电脑上正常干活（照常问你要权限）
④ 交结果（它自己） 它认为做完了 → 调 pc_task_done 写结果（done）
⑤ 汇报（自动）   服务器代码立刻调后台 /run 叫醒「电脑任务汇报」
                 → 大肥鱼调 pc_task_report 从队列读出结果 → 用它的口吻发 QQ（标记 reported）
```
**全程只有第 ② 步要你开口。** 第 ④ 步靠的是工具说明里写着“做完后调用 pc_task_done”——这是 AI 按说明办事，不是程序保证；重要任务可以加一句“做完记得交结果”。第 ⑤ 步是纯代码触发，100% 会发生。

### 9.2 几个容易误会的点
| 问题 | 答案 |
|---|---|
| 电脑上开着 Claude / Codex 就会自动领活吗？ | 不会。桌面版只在你发消息时动；要自动得装命令行版 + 定时任务（决定不做） |
| “连上了”会一直耗 token 吗？ | 不会。只是一条闲置 SSH 连接；只有开新对话时加载一次 7 个工具的说明书（约 1,000 token） |
| 大肥鱼会知道我在电脑上干了什么吗？ | 不会。它只知道从队列交回来的任务结果 |
| 每做完一个任务都会汇报吗？ | 会，一个任务汇报一次（叫醒大肥鱼一次）。中间进度不汇报，不会重复汇报 |
| 什么时候算“做完”？ | 由电脑上的 Claude / Codex 自己判断。如果它交得太早，可以让它“把最新结果再交一次”（再调一次 pc_task_done，会覆盖结果并再汇报一次） |
| 汇报完了，还想在同一个项目上继续提需求？ | 可以：在 QQ 跟大肥鱼说新需求（= 新任务进队列）→ 在**原来那个对话**里说「再看看大肥鱼有没有新任务」→ 它带着之前的上下文接着做 → 再汇报一次（2026-11-22 实测 ✅） |
| Codex 能接活吗？ | 能，和 Claude 完全一样（同一个队列、同一套工具），只是要坐在电脑前；Codex 用 DeepSeek，便宜，适合日常开发 |
| 不经过队列、直接在 Claude 里让它干的活？ | 不会有任何汇报（和大肥鱼无关） |

### 9.3 为什么不做“进度汇报 / 双向商量”
讨论过：让电脑端随时汇报进度、遇到问题通过 QQ 问你、你再通过大肥鱼回复……来回一轮要经过 QQ → 大肥鱼 → 队列 → 电脑好几个环节，又慢又花 token，还多出容易坏的地方。
**结论：越轻越不容易坏。** 需要来回商量的开发，直接用手机上的 Claude 连电脑干（当场问、当场答）；大肥鱼的队列只用来扔“不用商量、做完告诉我”的小事。

### 9.4 三种干活方式怎么选
| 场景 | 用什么 |
|---|---|
| 在外面，需要边做边商量的开发 | 手机上的 Claude（直接远程操作电脑 + SSH 服务器） |
| 在外面，扔一件不用商量的小事，回头看结果 | QQ 跟大肥鱼说 → 队列 → 回到电脑前让 Claude / Codex 领 |
| 坐在电脑前 | 直接用 Claude 或 Codex（Codex 用 DeepSeek 更省钱） |

## 10. 以后可以加的（还没做）
- **全自动执行**：电脑开机时自动领任务、无人值守地让 Codex/Claude 做完。需要命令行版（`codex exec` / `claude -p`）+ Windows 定时任务，并且要限定它能动的文件夹和工具 —— 等主人决定要不要
- 电脑端主动发消息给 QQ（现在只能通过“完成任务”汇报）
