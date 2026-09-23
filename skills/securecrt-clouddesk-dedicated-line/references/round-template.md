# 每轮模板与留痕规范

## 每轮输出模板

沿用 `internet-dedicated-line-fault-handling-manual` 的字段，新增【通道状态】与【执行方式】。
两个新增行存在的意义：让操作人一眼看清"命令从哪来、往哪去、谁在执行"。

```text
【工单与轮次】工单标识 / 第N轮
【通道状态】REST：tab=<n> 设备=<别名> connected=<true|false|未使用> ｜ 云电脑：<LIVE|STALE|未使用> ｜ 取值时间 <HH:MM:SS>
【当前判断】待采集 / 信息不足 / 疑似异常 / 明确异常 / 本轮已查项未见异常
【依据与故障关联】引用已收到的证据（命令编号 + 回显字段/数值 + 时间）；说明是否足以解释报障
【派单或升级建议】目标组织/地市 + 目标岗位 + 动作 + 依据 + 随单材料 + 交接留痕；无需时写"无"
【下一步】先落实派单；再写可并行的白名单补查；没有有效补查时说明原因
【执行目标】设备类型 + 厂商/型号 + 设备名称或脱敏标识；查询对象；当前/所需视图
【本轮命令】条目编号 + 目的 + 范围 + 风险类别（只读/主动探测/视图切换）+ 可复制命令
【执行方式】只读模式（操作人粘贴）／ 直发模式（AI 经 REST 发送，当轮已授权）／ 请操作人通过 4A 执行
【请回传】命令及回显、设备提示符/视图、执行时间、报错或分页截断情况
【阶段性记录】已查事实、未查项、下一轮待办；派单时间与受理状态
```

字段规则（与人工版一致，别改）：

- 【依据与故障关联】首轮写"待采集"；没收到执行结果就不能说"已执行"或"已发现故障"。
- 【本轮命令】清单未列出的命令不出现；参数含换行/连接符/不明拼接时不代入。
- 【派单或升级建议】只在满足条件时填目标岗位，不为填栏目强行指定部门；无需要写"无"。
- 脱敏占位参数的命令必须标注"不可直接执行"。

## 通道操作片段（按当前模式取用）

### 只读模式（默认）

```powershell
# 认设备
Invoke-RestMethod 'http://127.0.0.1:19191/api/v1/tabs'
Invoke-RestMethod 'http://127.0.0.1:19191/api/v1/screen?tab=2' | Select-Object -ExpandProperty text

# 取回显（屏内 + 滚动）
Invoke-RestMethod 'http://127.0.0.1:19191/api/v1/output?tab=2' | Select-Object -ExpandProperty text
```

操作人在 SecureCRT 里粘贴命令，AI 只负责取回显与判读。

### 直发模式（当轮已授权）

```powershell
$cmd = 'display ont info 0 1 2 3'      # 白名单条目 + 已核验参数
Invoke-RestMethod 'http://127.0.0.1:19191/api/v1/input' -Method Post -ContentType 'application/json' `
  -Body (@{ tab = 2; text = $cmd; append_enter = $true } | ConvertTo-Json -Compress)
Start-Sleep -Seconds 2
Invoke-RestMethod 'http://127.0.0.1:19191/api/v1/output?tab=2' | Select-Object -ExpandProperty text
```

`Start-Sleep` 的秒数按命令耗时调整：配置类/大范围查询给足时间，等提示符回来再取。

### 云电脑内 REST（拓扑 B）

```bash
clouddesk-diag.exe exec "ps:& 'C:\Users\Public\scrt_api.ps1' -Path /api/v1/tabs"
clouddesk-diag.exe exec "ps:& 'C:\Users\Public\scrt_api.ps1' -Path /api/v1/output -Tab 2 -OutFile C:\Users\Public\scrt_out.txt"
clouddesk-diag.exe exec "ps:& 'C:\Users\Public\scrt_api.ps1' -Method POST -Path /api/v1/input -Tab 2 -Text 'display version' -Enter"
clouddesk-diag.exe exec "ps:& 'C:\Users\Public\scrt_api.ps1' -Method POST -Path /api/v1/stop"
```

### 客户侧取证据

```bash
clouddesk-diag.exe capture
clouddesk-diag.exe exec "ps:Get-NetIPConfiguration | Select-Object InterfaceAlias,IPv4Address,IPv4DefaultGateway"
clouddesk-diag.exe exec "ps:Test-NetConnection -ComputerName <目标> -InformationLevel Detailed"
```

云电脑上的连通性结论只作为客户侧体验证据，不能替代设备侧查询或现场核实。

## 命令执行状态判定（沿用人工版口径）

| 状态 | 依据 | 下一步 |
|---|---|---|
| 成功有结果 | 回显含目标字段与正常提示符 | 判读并与故障现象/时间对齐 |
| 成功无匹配 | 回显明确"无此会话/记录为空" | 核对对象、范围、时间，再决定补查 |
| 权限拒绝 | 回显报权限不足 | 记录未完成，保留原报错；按人工版规则请权限维护核验，不换账号重试 |
| 语法或视图错误 | 回显报语法/视图不接受 | 核对型号版本与视图；不盲试命令变体 |
| 超时 / 无输出 | 未取到提示符 | 确认命令是否真正执行；区分"还在跑"和"丢包/断连" |
| 分页截断 | 停在 `---- More ----` | 请操作人按既有惯例处理；不把截断当空结果 |
| 未执行 | 没有得到执行结果 | 不能说已执行；列为未查项 |

## 留痕规范

目录与命名：

```
<工单目录>/
├── <工单>-R<N>-<设备别名>-<命令编号>.txt      # /api/v1/output 落盘的回显原文
├── <工单>-R<N>-<设备别名>-<命令编号>.png      # capture 截图（需要时）
└── <工单>-R<N>-channel.log                    # 本轮通道状态、取值时间、异常
```

规则：

1. 回显原文不加工，判读结论写进轮次记录或工单说明。
2. 每份证据记录**三个时间**：设备回显内的时间戳、命令执行时间、本地取值时间，并注明已知时钟偏差。
3. 涉及其他客户、其他电路的内容不入本工单目录。
4. 敏感凭据不落盘、不回传；对象、IP、LOID 按单位规则脱敏，同一对象全程同一别名。

## 派单留痕字段（照抄人工版最小字段）

```text
目标组织/地市： / 目标岗位： / 派单动作： / 派单依据：
随单材料： / 交接留痕（时间、受理状态、退单或协调）： / 挂单状态：
```

挂单：仅非电信原因且具备时长与证据时才建议；电信侧异常、人员不足、内部等待、待派单均不符合。
AI 只提建议，不声称已派单、已挂单或已暂停计时。
