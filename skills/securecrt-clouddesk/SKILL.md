---
name: securecrt-clouddesk
description: |
  SecureCRT REST × 天翼云电脑诊断 联合接维：一边用 SecureCRT 的本地 REST 接口
  读写设备会话（认设备、读回显、发命令），一边用 clouddesk-diag 通道看客户云电脑
  画面、执行命令、取文件。覆盖"SecureCRT 装在本机"与"SecureCRT 装在云电脑里
  （4A 拉起）"两种拓扑。
  当用户提到以下关键词时必须触发：
  云电脑 + SecureCRT / 云电脑里敲设备 / 4A + 云电脑 / 云电脑接维 + 设备回显 /
  云电脑里的终端 / SecureCRT 在云电脑里 / 客户机上看设备 / 联合诊断 /
  云电脑 + 读回显 / 云电脑 + 发命令 / 云端会话 + 本地设备会话。
  也适用于：接维现场既要看客户云电脑、又要同时操作设备会话（OLT/MSE/交换机/BRAS）
  的任何场合。
---

# SecureCRT REST × 云电脑诊断

两条通道，管两段完全不同的东西：

| 通道 | 工具 | 管什么 | 位置 |
|---|---|---|---|
| A 设备会话 | `securecrt-rest-api`（本技能内已含用法） | SecureCRT 里连着的 OLT / MSE / 交换机 / 服务器会话：读回显、发命令、清屏 | 会话在哪台机器，服务就在哪台机器 |
| B 客户现场 | `clouddesk-diag` | 客户云电脑内部：画面、命令、文件、键鼠 | 云电脑内部 |

两条通道的失败模式互相独立：REST 挂了不影响看云电脑画面，云电脑 agent 掉了不影响读设备回显。
现场排障时**先分别判活，再合并下结论**，不要因为一条通道异常就怀疑另一条。

## 一、先判拓扑（30 秒）

SecureCRT 装在哪，决定了 REST 服务在哪：

```bash
# ① 本机有没有 REST 服务
curl -s --max-time 2 http://127.0.0.1:19191/api/v1/health

# ② 云电脑内部有没有 REST 服务
clouddesk-diag.exe exec "ps:Invoke-RestMethod -Uri http://127.0.0.1:19191/api/v1/health -TimeoutSec 3 | ConvertTo-Json -Compress"
```

| ① 通 | ② 通 | 拓扑 | 走哪条 |
|---|---|---|---|
| 是 | — | **A：SecureCRT 在本机**，云电脑是另一个被诊断对象 | 本机 REST 直连 + clouddesk-diag 看云电脑（第三节） |
| 否 | 是 | **B：SecureCRT 在云电脑里**（4A 客户端在云电脑内拉起的会话，或用户在云电脑里自己开 SecureCRT） | 经 clouddesk-diag 桥接到云电脑的 loopback（第四节） |
| 否 | 否 | 服务没起，或脚本没在该机器上跑 | 先按 `securecrt-rest-api` 第二节启动脚本 |

要点：**REST 服务只监听 127.0.0.1**。云电脑里的服务，其 loopback 是云电脑自己的——本地 `curl 127.0.0.1:19191` 永远到不了它，必须经通道 B 进去打。

## 二、加载配套技能

- 设备会话的端点细节、副作用、未验证项 → `skill securecrt-rest-api`（或直接读
  `/home/tanqizhi/.dsh/skills/securecrt-rest-api/SKILL.md`）。
- 云电脑通道的部署、`status` 心跳判读、`exec`/`pull`/`push`/`cinput` 细节 → `skill clouddesk-diag`。
- 本技能只讲**两条通道怎么配合**，不重复它们的操作手册。

## 三、拓扑 A 工作流：本机 SecureCRT + 云电脑

```bash
# 0) 两条通道各自判活
clouddesk-diag.exe status
curl -s http://127.0.0.1:19191/api/v1/tabs
```

```powershell
# 1) 认设备：先看这个 tab 连的是谁，再决定发什么
Invoke-RestMethod 'http://127.0.0.1:19191/api/v1/tabs'
Invoke-RestMethod 'http://127.0.0.1:19191/api/v1/screen?tab=2' | Select-Object -ExpandProperty text
```

**认设备这一步不许省。** 用提示符、`banner`、`display version` 输出确认 tab ↔ 设备对应关系，
再对这台设备做判断。多台会话并行时最容易串单，串单会把排查结论带到别的客户身上。

```powershell
# 2) 发命令（默认由人在 SecureCRT 里敲；获授权后可由 AI 发）
Invoke-RestMethod 'http://127.0.0.1:19191/api/v1/input' -Method Post -ContentType 'application/json' `
  -Body '{"tab":2,"text":"display ont info 0 1 2 3","append_enter":true}'

# 3) 取回显：屏内用 screen，含滚动内容用 output
Invoke-RestMethod 'http://127.0.0.1:19191/api/v1/output?tab=2' | Select-Object -ExpandProperty text
```

```bash
# 4) 云电脑侧看现场（不打断使用者）
clouddesk-diag.exe capture
clouddesk-diag.exe exec "ps:Get-NetIPConfiguration | Select-Object InterfaceAlias,IPv4Address"
```

```bash
# 5) 把设备回显落盘留痕（见第六节）
```

## 四、拓扑 B 工作流：SecureCRT 在云电脑里

### 4.1 投放桥脚本（一次）

把本技能的 `scripts/scrt_api.ps1` 推到云电脑，之后所有 REST 调用都经它，避免多层引号：

```bash
clouddesk-diag.exe push "/home/tanqizhi/.dsh/skills/securecrt-clouddesk/scripts/scrt_api.ps1" --to "C:\Users\Public"
```

### 4.2 在云电脑里启动 SecureCRT REST 脚本

REST 脚本必须在 SecureCRT 的 GUI 里 **Script → Run** 启动一次，云电脑那边：

1. 手上有画面权限就手点一次（`capture` 先确认画面状态）。
2. 只能键盘操作时用 `cinput`（在云电脑内部按键，不抢本地键鼠）：

```bash
clouddesk-diag.exe cinput --key "alt+s"      # 打开 Script 菜单
clouddesk-diag.exe cinput --key "down"       # 逐项下移，边移边 capture 确认高亮项
clouddesk-diag.exe cinput --key "enter"
clouddesk-diag.exe cinput --text "C:\Users\Public\SecureCRT_REST_API.py"
clouddesk-diag.exe cinput --key "enter"
```

菜单项名称随版本地化可能不同，**每一步之后 `capture` 看一眼再继续**，不要盲敲。
3. 长期方案：在 SecureCRT 的 **Session Options → Logon Actions** 里挂脚本，会话建立时自动执行；
   这一步属于改客户端配置，须先确认现场允许。

### 4.3 日常调用

```bash
# 列 tab
clouddesk-diag.exe exec "ps:& 'C:\Users\Public\scrt_api.ps1' -Path /api/v1/tabs"

# 认设备：读某个 tab 的可见屏
clouddesk-diag.exe exec "ps:& 'C:\Users\Public\scrt_api.ps1' -Path /api/v1/screen -Tab 2"

# 取回显（含滚动）到文件，再 pull 回本地——中文最稳的路径
clouddesk-diag.exe exec "ps:& 'C:\Users\Public\scrt_api.ps1' -Path /api/v1/output -Tab 2 -OutFile C:\Users\Public\scrt_out.txt"
clouddesk-diag.exe pull "C:\Users\Public\scrt_out.txt" --to ./scrt_out.txt

# 发命令（一条一条来，发完必读回显）
clouddesk-diag.exe exec "ps:& 'C:\Users\Public\scrt_api.ps1' -Method POST -Path /api/v1/input -Tab 2 -Text 'display version' -Enter"
```

为什么经 `ps:` 而不是 cmd：云电脑侧的 `ps:` 表达式在 agent 的 PowerShell 会话里执行
（`Invoke-Expression`），输出是 .NET 字符串，不经过控制台代码页——中文不会变成乱码。
细节与失败模式见 [references/bridge-recipes.md](references/bridge-recipes.md)。

## 五、两条通道的联合判定

| 现象 | 先查 | 判读 |
|---|---|---|
| 设备回显取不到 | `GET /health` 是否 200；`tabs` 里该 tab `connected` 是否 true | `connected:false` = 会话断了，属 SecureCRT 侧，与云电脑无关 |
| `GET /output` 拿到旧内容 | 设备侧是否已滚屏 | 扩大 SecureCRT 滚动缓冲；或改用 `/screen` 分屏取值 |
| 云电脑命令不返回 | `clouddesk-diag.exe status` 的心跳 | `STALE`/`old` = agent 死了；在客户端里断开云电脑重连一次，注入会重新拉起 |
| 云电脑里 19191 连不上 | 脚本是否在云电脑里跑过 | 没跑过就按 4.2 启动；跑过就 `capture` 看有没有弹框/报错 |
| 回显中文乱码 | 取值路径 | 走 `-OutFile` + `pull` 落 UTF-8 文件；不要指望控制台管道 |
| 两边都正常但结论对不上 | 对象是否同一台 | 先确认 tab ↔ 设备、云电脑 ↔ 客户的对应关系，再谈现象 |

## 六、留痕

一次接维的完整证据链 = 设备侧回显文本 + 云电脑侧画面/命令输出。建议：

1. 每轮把 `/output` 的 `text` 落成文件：`工单-轮次-设备-命令.txt`（拓扑 B 用 `-OutFile` + `pull`）。
2. `capture` 的 PNG 存同目录，文件名带时间戳。
3. 记录取值时间：设备回显的时间戳、云电脑命令的执行时间、本地取值时间——**三者可能有时钟偏差**，
   判定"故障是否还在持续"时不能只看一个。

## 七、边界

- REST 服务**无鉴权**且只绑 loopback：谁在那台机器上，谁就能敲你的设备会话。共享/多人使用的
  机器上用完即 `POST /api/v1/stop`。
- 读 `/output` 会切换 SecureCRT 的当前 tab 并全选终端文本——在客户看着的云电脑画面上操作时，
  这个跳变是可见的；节奏上避免连续狂切。
- `cinput` 的文本输入会覆盖云电脑剪贴板。
- 云电脑重启/注销后 agent 会死、云电脑里的 SecureCRT 也要重开——两件独立的事，分别处理。
- 本技能不新增任何设备侧命令权限：能查什么、能不能改，仍由所属岗位权限与工单规则决定。
