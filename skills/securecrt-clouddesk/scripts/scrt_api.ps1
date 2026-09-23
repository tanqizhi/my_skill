param(
    [ValidateSet('GET', 'POST')] [string] $Method = 'GET',
    [string] $Path = '/api/v1/tabs',
    [int] $Tab = 0,
    [string] $Text = '',
    [switch] $Enter,
    [int] $RowStart = 0,
    [int] $RowEnd = 0,
    [int] $Port = 19191,
    [string] $OutFile = '',
    [int] $TimeoutSec = 30
)
$ErrorActionPreference = 'Stop'

# SecureCRT REST 桥：把一次调用压成一条命令行，避免多层引号转义。
# 常用于云电脑内部（经 clouddesk-diag 的 ps: 通道）或本机 PowerShell。

$base = "http://127.0.0.1:$Port"
$query = @()
if ($Tab -gt 0) { $query += "tab=$Tab" }
if ($RowStart -gt 0) { $query += "row_start=$RowStart" }
if ($RowEnd -gt 0) { $query += "row_end=$RowEnd" }
$uri = $base + $Path
if ($query.Count -gt 0) { $uri += '?' + ($query -join '&') }

$call = @{ Uri = $uri; Method = $Method; TimeoutSec = $TimeoutSec }
if ($Method -eq 'POST') {
    if ($Path -eq '/api/v1/input') {
        $body = @{ text = $Text }
        if ($Tab -gt 0) { $body.tab = $Tab }
        if ($Enter) { $body.append_enter = $true }
        $call.Body = ($body | ConvertTo-Json -Compress)
        $call.ContentType = 'application/json'
    } else {
        $call.ContentType = 'application/json'
    }
}

try {
    $result = Invoke-RestMethod @call
} catch {
    # 只输出 ASCII 字段：Exception.Message 是本地化文本，经控制台代码页会变乱码。
    # http_status + detail（服务返回的原始 JSON）在任何代码页下都可读。
    $status = ''
    if ($_.Exception.Response -and $_.Exception.Response.StatusCode) {
        $status = [int] $_.Exception.Response.StatusCode
    }
    $detail = ''
    if ($_.ErrorDetails -and $_.ErrorDetails.Message) { $detail = $_.ErrorDetails.Message }
    # 不能 exit：本脚本常被云电脑侧 agent 用 & 调用，exit 会连带结束 agent 会话。
    Write-Output (@{ ok = $false; http_status = $status; detail = $detail } | ConvertTo-Json -Compress)
    return
}

if ($OutFile -ne '') {
    # 有 text 字段就落原文（终端回显），否则落完整 JSON。
    $payload = $result | ConvertTo-Json -Depth 8
    if ($result.PSObject.Properties.Name -contains 'text') { $payload = [string] $result.text }
    # 无 BOM 的 UTF-8：本地 pull 回 WSL 后可直接读，不会多出字节。
    [System.IO.File]::WriteAllText($OutFile, $payload, (New-Object System.Text.UTF8Encoding($false)))
    $size = (Get-Item -LiteralPath $OutFile).Length
    Write-Output ("[written] {0} ({1} bytes)" -f $OutFile, $size)
} else {
    Write-Output ($result | ConvertTo-Json -Depth 8)
}
