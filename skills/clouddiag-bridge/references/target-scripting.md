# 编写目标诊断脚本

发送给转发器的 `script` 字段是目标端 PowerShell 脚本。规则：

- 从 `$ErrorActionPreference = 'Stop'` 开始，明确处理会影响判断的错误。
- 避免 PowerShell 7 专属语法及未经检查的新系统命令；先查询目标版本或用 `Get-Command` 检查可用性。
- 每次脚本自包含。需要目录切换、变量定义和多步操作时，放在同一请求内。
- 优先用 `Select-Object` 选择必要字段和数量，再用 `ConvertTo-Json -Depth ...` 输出结构化数据。
- 读取事件日志时限制时间和条数，查询进程时限制字段，不拉取无关的大量信息。
- 不依赖交互输入、弹窗、用户配置文件或长期运行的子进程。
- 转发器关闭进度显示，不提供 PowerShell 交互进度流；不要依赖该流判断命令结果。
- 转发器已配置脚本输入和返回流编码，不要随意替换控制台标准流或更改编码；第三方 EXE 使用不同代码页时，先确认其输出格式。
- 调用原生命令时，在执行后立即检查 `$LASTEXITCODE`；不要假定非零退出一定触发 PowerShell 的错误处理。
- 提交脚本中的路径、字符串通过结构化数据或正确引号处理，不将客户描述、日志内容直接拼接成待执行代码。
- 确需落盘的操作必须在授权范围内，指定 UTF-8 编码，并记录文件位置；优先使用内存输出。

具体故障命令由实际证据决定，本说明不预设「重启服务」「重置网络」等自动修复动作。

## 脚本骨架

```powershell
$ErrorActionPreference = 'Stop'
[pscustomobject]@{
    ComputerName = $env:COMPUTERNAME
    UserName = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    PowerShellVersion = $PSVersionTable.PSVersion.ToString()
    Is64BitProcess = [Environment]::Is64BitProcess
    Services = @(Get-Service | Select-Object -First 5 Name,Status)
} | ConvertTo-Json -Depth 4
```

原生命令调用后的退出码检查：

```powershell
& some-native.exe /flag
if ($LASTEXITCODE -ne 0) { throw "native command failed: $LASTEXITCODE" }
```
