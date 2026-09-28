# 最小调用协议与 PowerShell 7 客户端

来源：AI Agent 操作说明 v0.2（工具 0.1.0 / 协议版本 1）。示例需在所用 Agent 环境复核，不得当作已经发生的连接或执行。

## 一、最小调用协议

| 项目 | 约定 |
| --- | --- |
| 地址 | 工程师 Windows 的 `http://127.0.0.1:<本地转发端口>` |
| 状态 | `GET /v1/health` |
| 执行 | `POST /v1/exec` |
| 请求类型 | `application/json; charset=utf-8` |
| 请求体传输 | 单个 Content-Length，不压缩、不分块；普通 JSON 客户端自动设置长度 |
| 认证 | 无，不添加令牌、会话字段或浏览器 Origin |
| 单次命令超时 | 默认 60 秒，范围 1-300 秒，以实际 health 限制为准 |
| HTTP 执行请求超时 | 至少为命令超时加 15 秒；长命令期间服务端每 5 秒发送一次 JSON 空白保活 |
| 脚本上限 | UTF-8 编码后 128 KiB |
| 请求体上限 | 256 KiB |
| 输出上限 | stdout 与 stderr 合计保留 4 MiB，检查截断标志 |

执行请求：

```json
{
  "request_id": "diag-unique-id",
  "script": "$ErrorActionPreference = 'Stop'; Get-Service | Select-Object -First 5 Name,Status | ConvertTo-Json -Depth 3",
  "timeout_seconds": 60
}
```

`request_id` 使用 1-64 位 ASCII 字母、数字、短横线或下划线。为每次新执行生成新 ID，用于记录和关联结果，但它不保证命令只执行一次。

优先使用 Agent 已有的原生 HTTP 工具，只要它支持读取无 `Content-Length`、直到连接关闭的 HTTP 响应，并满足直连、UTF-8、超时、禁用重定向和禁用自动重试的要求。不要为一次请求生成大型临时脚本或安装额外软件。

## 二、PowerShell 7 示例的适用条件

没有合适的原生 HTTP 工具时，可在工程师 Windows 的 PowerShell 7（`pwsh`）中使用下列示例。不通过 CMD、旧版 `powershell.exe`、Bash 或 WSL 执行这些本地示例；若 `pwsh` 不可用，使用现有 HTTP 工具或转人工，不自动安装。

这里的 PowerShell 7 要求只适用于工程师侧示例。目标端仍由转发器调用系统 Windows PowerShell，不要求升级到 7。

### 2.1 配置和请求函数

该函数只发 HTTP 请求，不执行任何目标诊断脚本。配置和后续示例需在同一工程师侧 PowerShell 会话中运行；如果 Agent 每次启动新进程，应在本次调用中包含所需定义，不要假定本地状态一定保留。

```powershell
$ErrorActionPreference = 'Stop'
$BridgePort = 21451
$ExpectedComputerName = 'REPLACE_WITH_CONFIRMED_COMPUTER_NAME'

if ($BridgePort -lt 1 -or $BridgePort -gt 65535) {
    throw 'Invalid engineer-side port.'
}
if ($ExpectedComputerName -eq 'REPLACE_WITH_CONFIRMED_COMPUTER_NAME') {
    throw 'Set the computer name confirmed by the engineer first.'
}
$BaseUri = "http://127.0.0.1:$BridgePort"

function Invoke-BridgeRequest {
    param(
        [ValidateSet('GET', 'POST')][string]$Method,
        [ValidateSet('/v1/health', '/v1/exec')][string]$Path,
        [object]$Body,
        [ValidateRange(1, 600)][int]$HttpTimeoutSeconds = 10
    )
    $handler = [System.Net.Http.HttpClientHandler]::new()
    $handler.UseProxy = $false
    $handler.AllowAutoRedirect = $false
    $client = [System.Net.Http.HttpClient]::new($handler)
    $client.Timeout = [TimeSpan]::FromSeconds($HttpTimeoutSeconds)
    $request = [System.Net.Http.HttpRequestMessage]::new(
        [System.Net.Http.HttpMethod]::new($Method), "$BaseUri$Path"
    )
    $response = $null
    try {
        if ($null -ne $Body) {
            $json = $Body | ConvertTo-Json -Depth 8 -Compress
            if ([Text.Encoding]::UTF8.GetByteCount($json) -gt 262144) {
                throw 'Request body exceeds the size limit.'
            }
            $request.Content = [System.Net.Http.StringContent]::new(
                $json, [Text.Encoding]::UTF8, 'application/json'
            )
        }
        $response = $client.SendAsync($request).GetAwaiter().GetResult()
        $text = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
        [pscustomobject]@{
            http_status = [int]$response.StatusCode
            data = ($text | ConvertFrom-Json -ErrorAction Stop)
        }
    }
    finally {
        if ($null -ne $response) { $response.Dispose() }
        $request.Dispose()
        $client.Dispose()
    }
}
```

函数保留 HTTP 状态码和 JSON 内容，不把非 200 响应简单当作命令结果。执行响应没有 `Content-Length`，服务端会在同一个连接中每 5 秒发送一次换行作为应用层保活，命令完成后关闭连接并给出完整 JSON；JSON 空白对解析无影响。连接异常或响应无法解析时会抛错；若发生在 POST 期间，应按「结果未知」处理，不能重新调用来试运气。

### 2.2 查询状态

```powershell
$ErrorActionPreference = 'Stop'
$reply = Invoke-BridgeRequest -Method GET -Path '/v1/health'
if ($reply.http_status -ne 200) {
    throw "Health request failed: HTTP $($reply.http_status)"
}
$health = $reply.data
if ($health.protocol_version -ne 1) { throw 'Unsupported protocol version.' }
if ($health.computer_name -ne $ExpectedComputerName) {
    throw 'Target computer mismatch. Stop and ask the engineer.'
}
if ($health.os_arch -ne 'x64') { throw 'Unsupported architecture. Hand off.' }
$health | ConvertTo-Json -Depth 8
```

查看输出后，确认系统在支持列表、PowerShell 版本可用、权限符合预期、当前没有其他命令在执行，并且 `unhealthy` 不为 true。`user_name` 用于确认实际执行账户；`os_arch` 为 x64 并不能证明不是裁剪镜像，镜像范围仍以工程师确认和实际异常为依据。

字段缺失、协议不符或机器名不匹配时停止，不「猜测兼容」。状态查询不是服务端强制握手，但 Agent 应将其作为操作检查步骤。

### 2.3 提交一次只读诊断

仅在上一步核对通过后运行。实际脚本放在单引号 here-string 中，防止 `$env:COMPUTERNAME` 等变量提前在工程师电脑展开。

```powershell
$ErrorActionPreference = 'Stop'
if ($health.busy) { throw 'Bridge is busy. Do not enqueue another command.' }

$script = @'
$ErrorActionPreference = 'Stop'
[pscustomobject]@{
    ComputerName = $env:COMPUTERNAME
    UserName = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    PowerShellVersion = $PSVersionTable.PSVersion.ToString()
    Is64BitProcess = [Environment]::Is64BitProcess
    Services = @(Get-Service | Select-Object -First 5 Name,Status)
} | ConvertTo-Json -Depth 4
'@

if ([Text.Encoding]::UTF8.GetByteCount($script) -gt $health.limits.max_script_bytes) {
    throw 'Script exceeds the bridge limit.'
}
$commandTimeout = [Math]::Min(60, [int]$health.limits.max_timeout_seconds)
if ($commandTimeout -lt 1) { throw 'Invalid timeout limit from health response.' }
$body = @{
    request_id = 'diag-' + [guid]::NewGuid().ToString('N')
    script = $script
    timeout_seconds = $commandTimeout
}
$result = Invoke-BridgeRequest -Method POST -Path '/v1/exec' `
    -Body $body -HttpTimeoutSeconds ($commandTimeout + 15)
$result | ConvertTo-Json -Depth 8
```

不要在本地对 `$script` 调用 `Invoke-Expression`、`&` 或脚本块执行。它只是发送给目标转发器的数据。

示例为方便查看，将整个响应输出为 JSON。真实诊断要检查 HTTP 状态、返回的 `request_id`、`status`、退出码、stderr 和截断标志，再分析 stdout。如果预期 stdout 是 JSON，可额外解析该字段，但不是所有脚本都会输出 JSON。

## 三、参考链接

- [A1] Microsoft，HttpClientHandler 的代理和重定向属性：`https://learn.microsoft.com/en-us/dotnet/api/system.net.http.httpclienthandler`
- [A2] Microsoft，PowerShell 引号及 here-string 规则：`https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_quoting_rules`
