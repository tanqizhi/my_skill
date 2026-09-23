# 桥接细节与失败模式

本文件讲"云电脑里的 SecureCRT REST 服务怎么被本机调到"，以及每一步会怎么坏。

## 通道事实（依据 clouddesk-diag 的 agent 实现）

云电脑侧 agent（`agent.ps1`）的取命令循环：

```powershell
if ($cmd -like 'ps:*') {
    $out = Invoke-Expression $cmd.Substring(3).Trim() 2>&1 | Out-String
} else {
    $out = Invoke-Cmd $cmd
}
```

三条推论，直接决定调用写法：

1. `ps:` 后面的内容是**一条 PowerShell 语句**，在本机（云电脑）的 agent 会话里执行，
   不经过 `cmd.exe`——因此不存在 cmd 层的引号转义问题，但也**不能用 cmd 语法**。
2. 命令内容是写进 `cmd.txt` 文件再被读走的，不经过命令行解析，所以参数里带空格、括号、
   中文都没问题；真正要小心的只有**你自己那一层 shell（bash / pwsh）怎么把参数交给 `clouddesk-diag.exe`**。
3. 输出经 `Out-String` 落成 UTF-8 的 `result.txt`，本地侧做多编码解码——中文安全。

## 调用写法（按可靠性排序）

### 1) 经 `scrt_api.ps1`（推荐）

```bash
clouddesk-diag.exe exec "ps:& 'C:\Users\Public\scrt_api.ps1' -Path /api/v1/output -Tab 2 -OutFile C:\Users\Public\scrt_out.txt"
```

- 只用单引号包路径，没有嵌套双引号。
- 复杂请求体（`input` 的 JSON）在脚本内部用 `ConvertTo-Json` 生成，不经过命令行。
- `-OutFile` 落无 BOM UTF-8；再 `pull` 回本地读，绕开一切控制台编码问题。

### 2) 直接写 `ps:` 表达式

```bash
clouddesk-diag.exe exec "ps:(Invoke-RestMethod 'http://127.0.0.1:19191/api/v1/tabs') | ConvertTo-Json -Depth 6"
```

注意：这里的内层用**单引号**。如果你在 bash 里用双引号包整条命令，内层就必须是单引号；
在 pwsh 里同理。反过来把双引号塞进内层，会在某层被吃掉，得到
`Invoke-RestMethod : 缺少参数` 之类的报错。

### 3) 直接落文件再取（回显很长时）

```bash
clouddesk-diag.exe exec "ps:& 'C:\Users\Public\scrt_api.ps1' -Path /api/v1/output -Tab 2 -OutFile C:\Users\Public\scrt_out.txt"
clouddesk-diag.exe pull "C:\Users\Public\scrt_out.txt"
```

`exec` 有 60 秒量级的超时；整屏 + 滚动回显可能上千行，落文件比走标准输出稳。

## 投放桥脚本

```bash
clouddesk-diag.exe push "/home/tanqizhi/.dsh/skills/securecrt-clouddesk/scripts/scrt_api.ps1" --to "C:\Users\Public"
```

- 需要 agent 活着（`clouddesk-diag.exe status` 显示 `LIVE`）。agent 没起来先按 clouddesk-diag 技能
  的第四节处理，不要指望 push 能"顺带"把 agent 拉起来。
- `--via clip` 只在磁盘映射不可用时用；默认 `fs` 通道更快且无大小限制。
- 收工清理：`clouddesk-diag.exe exec "del C:\Users\Public\scrt_api.ps1 C:\Users\Public\scrt_out.txt"`。

## 在云电脑里启动 REST 脚本

REST 服务必须由 SecureCRT 的 GUI 触发一次 `Script → Run`。可选路径：

| 路径 | 适用 | 注意 |
|---|---|---|
| 手工点菜单 | 有画面权限、使用者配合 | 最稳 |
| `cinput` 键鼠 | 只能远程操作 | `alt+s` 打开 Script 菜单后逐项 `capture` 确认，再 `enter`；菜单名称随版本本地化，不要盲敲 |
| Session Options → Logon Actions 挂脚本 | 需要长期自动 | 改的是客户端配置，先确认现场允许 |
| 使用者自己启动 | 用户就在电脑前 | 让他把脚本路径记好 |

启动成功的标志：SecureCRT 里弹出监听地址对话框（截图存证），随后
`ps:& 'C:\Users\Public\scrt_api.ps1' -Path /api/v1/health` 返回 `"ok": true`。

## 失败模式对照表

| 报错/现象 | 含义 | 处理 |
|---|---|---|
| `exec` 返回 `(no output)` | 表达式没产生输出，或 agent 把空输出替换掉 | 给表达式加 `| Out-String` 或 `ConvertTo-Json`，确保有输出 |
| `无法将"Invoke-RestMethod"项识别为 cmdlet` | 命令走了 cmd 分支而非 `ps:` | 检查 `ps:` 前缀是否被 shell 吃掉（比如整条命令被当成 cmd 执行） |
| `无法连接到远程服务器` | 云电脑里 REST 服务没起 | 按上一节启动脚本 |
| `The underlying connection was closed` | 服务在处理中被停掉/中止 | 检查是否误发过 `/api/v1/stop`，重新 Run 脚本 |
| 命令很快返回但内容为空 | 设备的回显还没渲染完 | 稍等后再取一次；或先 `Screen` 后 `output` 分两步看 |
| `'\u5f00\u59cb'` 一类转义 | PowerShell 5.1 的 `ConvertTo-Json` 转义非 ASCII | 无害（JSON 语义正确）；要看原文就 `-OutFile` 落文本再 `pull` |
| `exec` 超时 | 单次命令超过 60 秒量级 | 拆小；REST 是单线程串行，别在云电脑里并发打它 |

## 已验证项（本机实测）

测试方式：Windows PowerShell 7 调用 `scripts/scrt_api.ps1`，服务端是**用 stub `crt` 跑的
SecureCRT REST 脚本**（验证桥脚本与 HTTP 契约，不涉及真实 SecureCRT）。

| 验证项 | 结果 |
|---|---|
| 脚本语法（`[Parser]::ParseFile`） | SYNTAX OK |
| GET 经桥调用（`tabs` / `screen`） | 返回完整 JSON |
| POST `input` ASCII | 服务端收到 `display version\r` |
| POST `input` 中文 | 服务端收到 `display 版本信息\r`（原样，无乱码） |
| `-OutFile` 落盘 | 14 字节，无 BOM，内容与响应 `text` 逐字节一致 |
| 错误路径（`tab=99`） | 输出 `{"http_status":404,"ok":false,"detail":"..."}`，全 ASCII，不中断调用方 |

两条来自实测的写法约定（已固化进脚本，改脚本时别退回去）：

1. **不能用 `exit`**：本脚本常被云电脑侧 agent 用 `&` 在**同一个 PowerShell 进程里**调用，
   `exit` 会连带结束 agent 会话（心跳断、通道死）。脚本内一律用 `return`。
2. **错误输出不要用 `$_.Exception.Message`**：那是本地化文本，经控制台代码页会变乱码；
   只输出 `http_status` 与 `detail`（服务返回的原始 JSON，英文），任何代码页下都可读。

## 安全提醒（工程事实，不是套话）
云电脑里起了 REST 服务，等于**云电脑上任何进程都能控制 SecureCRT 的全部会话**。
接维结束、或交付给使用者之前：

```bash
clouddesk-diag.exe exec "ps:Invoke-RestMethod -Uri http://127.0.0.1:19191/api/v1/stop -Method POST | ConvertTo-Json -Compress"
```

同时清理推送的桥脚本与落盘回显文件，并在 SecureCRT 里确认脚本已结束（对话框关闭、无残留进程）。
