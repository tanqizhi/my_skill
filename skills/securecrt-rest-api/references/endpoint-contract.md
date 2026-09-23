# 端点契约（实测）

本文件记录 `SecureCRT_REST_API.py` 的 HTTP 层行为。数据来自
`scripts/smoke_test.py`：用 stub `crt` 对象在子进程里跑被测脚本，逐端点断言。
脚本本体未改动（SHA-256 `0ad61f33ca9e99afb53843d97411abfb1fca0ddbd4ea091af95a91994ccc8de6`）。

**未覆盖**：真实 SecureCRT 的 `crt` 行为（`GetTabCount` / `GetTab` / `Screen.Get2` /
`MENU_SELECT_ALL` / `Screen.Selection`）。这一层必须在你自己的客户端上验证，
验证方法见 SKILL.md 第七节。

## 通用约定

- 所有响应都是 JSON，UTF-8，`Content-Type: application/json; charset=utf-8`，
  带 `Cache-Control: no-store` 与 `Connection: close`（每请求一条 TCP 连接）。
- 成功：`{"ok":true, ...}`；失败：`{"ok":false,"error":"<message>"}`。
- 不做鉴权：任何能连 `127.0.0.1:19191` 的本机进程都能发命令。
- 单线程串行处理；主循环每次 `handle_request()` 之后 `crt.Sleep(50)`。
- 请求体上限 64 KiB（超限 413），非 UTF-8 JSON 或非对象体一律 400。

## GET /api/v1/health

```
{"ok":true,"service":"securecrt-rest-api","tab":null,"connected":true}
```

`tab` 为 `null` 表示"没指定 tab，用的是脚本启动时的那个 tab"。`connected` 取自
`Session.Connected`。指定不存在的 tab 时返回 404，而不是 `ok:false` 之外的形态。

## GET /api/v1/tabs

```json
{"ok":true,"count":3,"tabs":[{"tab":1,"connected":true},{"tab":2,"connected":true},{"tab":3,"connected":true}]}
```

序号从 1 开始，顺序就是当前窗口里 tab 的显示顺序（会随开/关 tab 变化）。
实现调用 `crt.GetTabCount()` 与 `crt.GetTab(index)`。

## GET /api/v1/screen

查询参数：`tab`（可选）、`row_start`（默认 1）、`row_end`（默认 `Screen.Rows`）。

```json
{"ok":true,"scope":"visible_screen","tab":2,"text":"GET2 row 1..24",
 "row_start":1,"row_end":24,"rows":24,"columns":80,"current_row":5,"current_column":1}
```

- 先试 `Screen.Get2(...)`，抛异常则退化到 `Screen.Get(...)`。
- 越界（`row_start < 1`、`row_end < row_start`、`row_end > rows`）→ 400
  `row range is outside the visible screen`。
- 会话未连接 → 409 `the SecureCRT tab is not connected`。
- 只给**可见屏**；要滚动回显用 `/output`。

## GET /api/v1/output

```json
{"ok":true,"scope":"screen_and_scrollback","tab":null,"text":"..."}
```

实现：`tab.Activate()` → `Screen.SendSpecial("MENU_SELECT_ALL")` → 读 `Screen.Selection`。
这是 VanDyke 官方 screen/scrollback 导出示例的同一机制。

两个必须预期的副作用：

1. **会切换 SecureCRT 的当前 tab**（`Activate()`）。
2. 请求结束后**终端文本保持选中态**，在终端里点一下才清除。

未连接 → 409。

## POST /api/v1/input

请求体：

```json
{"tab":2,"text":"show version","append_enter":true}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `tab` | 整数，可省 | 省略 = 脚本启动的 tab。布尔值会被拒绝（400） |
| `text` | 字符串，必填 | 原样送 `Screen.Send()` |
| `append_enter` | 布尔，可省 | 为真时在末尾补一个 `\r` |

响应：`{"ok":true,"tab":2,"sent_length":13}` —— `sent_length` 是**补回车之后**的长度。

注意：`\r` 是回车字符，实际换行方式由会话设置决定；不要在 `text` 里自己再补 `\n`，
否则可能产生两次回车。

错误：`tab` 类型错 400、`text` 缺失或非字符串 400、`text` 超 64 KiB 413、
tab 越界 404、会话未连接 409。

## POST /api/v1/clear?tab=N

```json
{"ok":true,"tab":1}
```

调 `Screen.Clear()` 清该 tab 的屏幕缓冲（不影响滚动缓冲、不影响设备侧）。
未连接 → 409。

## POST /api/v1/stop

```json
{"ok":true,"stopping":true}
```

置 `stop_requested`，主循环退出、`server_close()`，脚本结束。之后端口不再监听
（实测：停止后再次请求直接连接被拒）。

## 状态码矩阵（实测）

| 请求 | 状态码 |
|---|---|
| `GET /api/v1/health` | 200 |
| `GET /api/v1/tabs` | 200 |
| `GET /api/v1/screen?tab=2` | 200 |
| `GET /api/v1/screen?tab=99` | 404 `tab index 99 does not exist` |
| `GET /api/v1/screen?row_start=30&row_end=40` | 400 `row range is outside the visible screen` |
| `GET /api/v1/nope` | 404 `unknown endpoint` |
| `POST /api/v1/input` 正常体 | 200 |
| `POST /api/v1/input` `{"tab":true,"text":"x"}` | 400 `'tab' must be an integer` |
| `POST /api/v1/input` `{"tab":2}`（缺 text） | 400 `'text' must be a string` |
| `POST /api/v1/input` `not-json` | 400 `request body must be UTF-8 JSON` |
| `POST /api/v1/clear?tab=1` | 200 |
| `POST /api/v1/stop` | 200 → 监听关闭 |

## 复现

```bash
python3 scripts/smoke_test.py            # 全部端点 + stub 调用日志校验
SECURECRT_SMOKE_PORT=19199 python3 scripts/smoke_test.py /path/to/SecureCRT_REST_API.py
```

通过时输出 `N checks, 0 failed`；副产物 `scripts/_smoke_calls.log` 记录 stub 收到的
`send` / `clear` / `activate` / `SendSpecial` 调用，可核对"到底往会话里发了什么"。
