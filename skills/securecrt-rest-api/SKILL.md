---
name: securecrt-rest-api
description: |
  SecureCRT 本地 REST 控制：把 SecureCRT 窗口里已连接的会话变成程序可读写的对象——
  列举 tab、读可见屏、读整屏与滚动回显、向会话发送命令文本、清屏、停服务。
  只监听 127.0.0.1:19191，无鉴权，仅本机可达。
  当用户提到以下关键词时必须触发：
  SecureCRT / SecureCRT 脚本 / SecureCRT REST / SecureCRT API / 19191 /
  读终端回显 / 抓终端输出 / 把回显给我 / 往会话里发命令 / 终端自动化 /
  多个 tab 会话 / 设备会话控制 / 从脚本敲设备 / 让 AI 读终端。
  也适用于：需要把"手工敲设备、肉眼抄回显"换成程序执行，或需要把终端文本
  取出做判读、比对、留痕的任何时刻。
---

# SecureCRT 本地 REST 控制

`scripts/SecureCRT_REST_API.py` 是跑在 SecureCRT 内部的脚本（Python3 引擎）。
启动后在本机 `127.0.0.1:19191` 起一个 HTTP 服务，把 SecureCRT 的终端对象暴露出来：
读回显、发命令、清屏。适合"AI 或脚本直接读写设备会话"的场景。

## 一、边界（先看这张表）

| 项 | 事实 |
|---|---|
| 监听 | 仅 `127.0.0.1`，默认端口 `19191`，可用 `SECURECRT_API_PORT` 改 |
| 鉴权 | 无。安全边界就是"只有本机能连"——**本机任何进程都能敲你的设备会话** |
| 协议 | HTTP/1.1，每请求一条连接（`Connection: close`） |
| 并发 | 单线程串行：一次只处理一个请求，循环之间还有 50ms 休眠。不要并发轰炸 |
| 前置 | SecureCRT 9.5.2+，能加载外部 Python3 引擎（位数与 SecureCRT 一致，32/64 位） |
| 服务进程 | 寄生在 SecureCRT 里。关掉那个会话所在的窗口、退出 SecureCRT、脚本被中止，服务一起消失 |
| 副作用 | 读 `/output` 会**切换 SecureCRT 当前 tab 并全选终端文本**（见第五节） |

## 二、启动与停止

启动：

1. 在 SecureCRT 里打开目标会话，让它处于**激活**状态。
2. 菜单 **Script → Run**，选择 `scripts/SecureCRT_REST_API.py`。
3. 弹出对话框写明监听地址与端口 —— 出现这个框即服务已起。框可以关掉，服务继续跑。
4. 自检 `GET /api/v1/health`。返回 `{"ok":true,...}` 才继续。

**"默认 tab"= 跑脚本时激活的那个 tab。** 不带 `tab=` 的请求都落在它上面。

换端口（19191 被占用时）：

```powershell
# 方式一：改脚本里的 DEFAULT_PORT 常量，最稳
# 方式二：设为用户级持久环境变量，然后重启 SecureCRT（子进程只继承启动时的环境）
setx SECURECRT_API_PORT 19192
```

`SECURECRT_API_PORT` 读的是 **SecureCRT 进程**的环境变量。SecureCRT 一般从开始菜单启动，拿不到你此刻在 pwsh 里 `$env:` 设的临时变量——所以要么改常量，要么 `setx` 后重启客户端。

停止：

```powershell
Invoke-RestMethod http://127.0.0.1:19191/api/v1/stop -Method Post
```

关会话、关窗口、重连之前先停服务，避免脚本与 UI 状态打架。

## 三、端点

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/api/v1/health?tab=N` | 服务与 tab 连接状态 |
| GET | `/api/v1/tabs` | 列出全部 tab 及连接状态 |
| GET | `/api/v1/screen?tab=N&row_start=1&row_end=24` | 可见屏文本（行范围可选） |
| GET | `/api/v1/output?tab=N` | 可见屏 + 滚动回显（全量取回显用这个） |
| POST | `/api/v1/input` | body `{"tab":N,"text":"show version","append_enter":true}` |
| POST | `/api/v1/clear?tab=N` | 清空该 tab 屏幕缓冲 |
| POST | `/api/v1/stop` | 停服务并关闭监听 |

字段明细、状态码矩阵、错误体格式见 [references/endpoint-contract.md](references/endpoint-contract.md)。
`tab` 省略 = 脚本启动时的那个 tab，此时响应里的 `"tab"` 字段是 `null`（正常现象，不是错误）。

## 四、调用方式

Windows（PowerShell 7）：

```powershell
$base = 'http://127.0.0.1:19191/api/v1'
Invoke-RestMethod "$base/tabs"
Invoke-RestMethod "$base/screen?tab=2"
Invoke-RestMethod "$base/output?tab=2" | Select-Object -ExpandProperty text
Invoke-RestMethod "$base/input" -Method Post -ContentType 'application/json' `
  -Body '{"tab":2,"text":"display version","append_enter":true}'
```

Windows（curl.exe，注意别用 PowerShell 的 `curl` 别名）：

```powershell
curl.exe -s http://127.0.0.1:19191/api/v1/tabs
curl.exe -s -X POST http://127.0.0.1:19191/api/v1/input -H "Content-Type: application/json" --data "{\"tab\":2,\"text\":\"display version\",\"append_enter\":true}"
```

WSL：服务挂在 **Windows 的 loopback** 上，WSL 能不能直连取决于网络模式。

```bash
curl -s --max-time 3 http://127.0.0.1:19191/api/v1/health && echo "WSL 可直连（mirrored 网络模式）"
```

直连不通时，让请求从 Windows 侧发出（WSL 只是调用 Windows 程序，不是换成 pwsh 交互）：

```bash
powershell.exe -NoProfile -Command "Invoke-RestMethod 'http://127.0.0.1:19191/api/v1/tabs' | ConvertTo-Json -Depth 6"
```

原因：NAT 模式下 WSL 的 `127.0.0.1` 是它自己的 loopback，而服务只绑 Windows loopback，主机 IP 也进不去。别去改脚本绑 `0.0.0.0` —— 那会把无鉴权的终端控制暴露到局域网。

## 五、副作用与坑（踩过的都在这）

| 现象 | 原因 | 应对 |
|---|---|---|
| 读一次 `/output`，SecureCRT 跳到别的 tab 了 | `read_output` 先 `Activate()` 再 `MENU_SELECT_ALL`（选中滚动回显的官方做法） | 需要看某个 tab 的回显就得让它变成前台；巡检多台设备时预期到会来回切 |
| 终端文字全变蓝（被选中） | 同上，SecureCRT 请求后保留选中态 | 在终端里点一下清除；这是 VanDyke 官方导出示例的行为，不是 bug |
| 发中文/长命令被截 | `input` 的 `text` 上限 64KB；`append_enter` 只补一个 `\r` | 超长命令写文件后执行；回车由会话的换行设置决定，不要自己再补 `\n` |
| `tab=2` 报 404 `tab index 2 does not exist` | tab 序号是**当前窗口的顺序**，开/关 tab 会变 | 每次操作前先 `/api/v1/tabs` 取一次 |
| 响应很慢 | 单线程 + 每次循环 50ms；`/output` 要等终端全选完成 | 逐条串行调用，别并发 |
| 返回 409 `not connected` | 那个 tab 没连（会话断了/还没连上） | 回 SecureCRT 把会话连上；脚本不负责建连 |
| 分页/`---- More ----` 卡住 | 命令回显带分页，`/output` 只能拿到屏幕上已渲染的部分 | 分页是传输器/设备侧行为：先关分页（会话或设备侧既有惯例），或分屏取值；本 API 不代点空格 |
| `GetTab` 相关报错 | 见第七节 | 只用默认 tab（不带 `tab=`） |

## 六、故障排查

| 现象 | 原因 | 处理 |
|---|---|---|
| 对话框提示 `Could not bind 127.0.0.1:19191` | 端口被占用（另开了脚本、或别的程序占用） | 改端口重跑；确认没有跑着第二个实例 |
| Script → Run 里看不到该脚本 / 报语言错误 | SecureCRT 没配外部 Python3 引擎，或位数不匹配 | 按 README 配好 Python3 引擎，位数与 SecureCRT 一致 |
| `curl: (7) Failed to connect` | 服务没起、已 `/stop`、或 SecureCRT 关了 | 看对话框是否出现过；重新 Script → Run |
| 返回 `{"ok":false,"error":"unknown endpoint"}` | 路径写错（例如漏了 `/api/v1`） | 按第三节的路径表核对 |
| WSL 连不上 | 网络模式（见第四节） | 走 `powershell.exe` 桥 |
| 拿到的是旧内容 | 设备回显已滚出滚动缓冲 | 增大 SecureCRT 滚动缓冲行数，或更早取值 |

自检脚本（**不需要 SecureCRT**，用 stub 跑通全部端点契约）：

```bash
python3 scripts/smoke_test.py                       # 默认测同目录的 SecureCRT_REST_API.py
python3 scripts/smoke_test.py /path/to/SecureCRT_REST_API.py
```

## 七、已知未验证项（照实说）

- 本 skill 附带的脚本哈希已核对，脚本的**HTTP 层已实测**（stub `crt`，见 `references/endpoint-contract.md`）；`crt.*` 这一层按 VanDyke 脚本 API 使用，**没有在真实 SecureCRT 上跑过**。
- `list_tabs` / `resolve_tab` 依赖 `crt.GetTabCount()` 与 `crt.GetTab(n)`。若你的 SecureCRT 版本没有这两个方法，`/api/v1/tabs` 和任何带 `tab=N` 的请求会返回 500。**首次使用先打一次 `/api/v1/tabs` 验证**：
  - 正常 → 全部端点可用，多 tab 控制成立；
  - 报方法不存在 → 退化为"只控制默认 tab"：所有请求都不带 `tab=`，要操作另一台设备就切到那个 tab 重新 Run 脚本。
- `MENU_SELECT_ALL` 与 `Screen.Selection` 是 VanDyke 官方 screen/scrollback 导出示例所用的机制；若某版本取不到回显，改用 `/api/v1/screen` 分屏读。
