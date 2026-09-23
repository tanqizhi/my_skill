---
name: securecrt-clouddesk-dedicated-line
description: |
  上网（互专）专线故障接维的通道增强版：诊断规则、4A 命令白名单、派单与挂单纪律
  全部沿用人工版，只把"手工搬运命令"换成 SecureCRT REST 通道执行与读回显，并用
  云电脑通道取客户侧现场证据。
  当用户提到以下关键词时必须触发：
  互专 / 上网专线 / 专线故障 / 宽带专线 / 专线工单 / 派单 / 加派 / 挂单 /
  用户IP + OLT / LOID / OLT 查询 / MSE 查询 / 光功率 / ONU 离线 /
  4A + SecureCRT / 通道版 / 自动取回显 / 云电脑 + 专线。
  前提：现场具备 SecureCRT REST 通道（本机或云电脑内）或 clouddesk-diag 通道。
  通道不可用时，改用 internet-dedicated-line-fault-handling-manual 的人工搬运版，
  诊断标准与派单纪律完全相同。
---

# 互专故障接维：通道版（SecureCRT REST + 云电脑）

三层叠加，缺一层都不完整：

| 层 | 来源 | 内容 |
|---|---|---|
| **规则层** | `internet-dedicated-line-fault-handling-manual` | 4A 命令白名单、质量参照标准、组织与工单术语、派单/挂单纪律 |
| **通道层 A** | `securecrt-rest-api` | 设备会话：认设备、发命令、读回显 |
| **通道层 B** | `clouddesk-diag` | 客户侧现场：画面、命令、文件 |

**本技能不新增任何设备命令、不新增任何权限。** 它只定义：命令怎么送出去、回显怎么取回来、
两条通道的证据怎么合并，以及通道存在时哪些纪律反而更要守住。

## 一、开工三步

1. 加载规则：`skill internet-dedicated-line-fault-handling-manual`，并按需读它的
   `references/` （commands-olt / commands-mse-sr / switch-and-aaa / 组织与工单术语 /
   质量参照标准 / manual-workflow）。**命令只从这些清单里选，引用条目编号。**
2. 判通道：`skill securecrt-clouddesk` 第一节的 30 秒判定（本机 REST / 云电脑内 REST / 都没有）。
3. 记工单现状：工单标识、现象、起始时间、影响范围、已知资源（用户 IP、OLT、MSE/SR、LOID）、
   已派单情况。缺项只补问决定下一条查询的必要项。

## 二、通道纪律（本技能的核心，逐条都是硬约束）

### D1 发命令前必须认设备

```powershell
Invoke-RestMethod 'http://127.0.0.1:19191/api/v1/tabs'
Invoke-RestMethod 'http://127.0.0.1:19191/api/v1/screen?tab=2' | Select-Object -ExpandProperty text
```

用提示符 / banner / `display version` 输出确认 `tab ↔ 设备`，与工单对象比对后再动手。
**对不上就停，先查清 tab 归属**。一次接维里同时开着多个会话时，串单是把 A 客户的回显写进
B 客户结论的最短路径——这正是人工版最强调的事，通道化之后风险更大（因为发命令变得太容易）。

### D2 三种模式，默认最保守

| 模式 | 谁发命令 | AI 的动作 | 何时用 |
|---|---|---|---|
| **只读模式（默认）** | 操作人在 SecureCRT 里粘贴 | 只用 `GET`（screen / output / tabs / health） | 一切默认场景，人在环 |
| **直发模式** | AI 用 `POST /input` 发送 | 白名单条目内、参数已核验的命令，一条一发一读 | **操作人当轮显式授权后** |
| **禁用** | —— | 自动关分页、自动切视图、连发、批量重试、在非工单对象上执行 | 任何时候 |

进入直发模式必须由操作人在当轮明确说清（例如"这条你直接发"）。沉默、含糊、或"上次说过"
都不构成授权。切换回只读模式不需要理由。

### D3 一条一发一读，等提示符返回

设备 CLI 是交互式的：命令交叠会把两段回显揉在一起，判读时无法区分哪段属于哪条命令。
每条命令发出后必须取回显、确认提示符回到正常状态，再考虑下一条。`/output` 全量取一次最稳。

```powershell
Invoke-RestMethod 'http://127.0.0.1:19191/api/v1/output?tab=2' | Select-Object -ExpandProperty text
```

### D4 回显落盘，作为工单证据

```bash
# 云电脑内 REST（拓扑 B）
clouddesk-diag.exe exec "ps:& 'C:\Users\Public\scrt_api.ps1' -Path /api/v1/output -Tab 2 -OutFile C:\Users\Public\scrt_out.txt"
clouddesk-diag.exe pull "C:\Users\Public\scrt_out.txt" --to "./<工单>-R<N>-<设备别名>-<命令编号>.txt"
```

文件命名与目录规范见 [references/round-template.md](references/round-template.md)。
截图（`clouddesk-diag capture`）与回显文件放同一目录，时间戳对齐。

### D5 通道不是权限，更不是跳过派单的理由

REST 让"发一条命令"变成零成本，于是最容易犯的错是：**把该派单的工单留着自己一条条查**。
规则不因通道变快而放松：

- 需要其他部门协同、客户侧可能性较高、下一步超权限 → **先给派单建议**，再去查；
- MSE/SR/BRAS 只有查看权限 → 只发查询类命令，变更需求派云网调度中心；
- 白名单之外的命令，通道再顺手也不发；
- 派单后可以继续做有权限的补查，补查不能成为延迟派单的理由。

### D6 通道挂了就回退，不停工

REST 服务停了、云电脑 agent 掉了、SecureCRT 重连了 —— 直接退回人工搬运模式
（`internet-dedicated-line-fault-handling-manual` 的原始流程）：把命令给操作人，他执行、复制回显回来。
**不得以"等通道恢复"为由暂停排查或延迟派单**，也不得因此降低诊断标准。

### D7 客户侧证据的边界

云电脑通道能看到客户桌面（画面、命令、文件），这是**客户侧体验证据**：能回答
"客户现在是什么状态""业务能不能通"，可以替代一遍电话询问。但：

- 客户云电脑 ≠ 客户 CPE / 光猫 / 线路，**不能**用它替代现场查线或装维核实；
- 云电脑上 ping 通，只证明"从这台终端到某目标可达"，不证明专线侧无异常；
- 客户侧可能性较高的判断仍按人工版规则，用设备侧证据 + 客户反馈共同支撑，不武断定责。

## 三、每轮执行流程

```text
核对对象（工单 / 设备 / 视图 / 通道状态）
  → 判断是否立即派单（满足条件先给派单建议）
  → 从白名单选 1~3 条本设备本视图的命令，标注条目编号
  → 选执行模式（只读 / 直发）
  → 执行 → 取回显 → 落盘
  → 判读（状态 + 依据 + 是否解释报障）
  → 决定下一轮
```

每轮输出格式见 [references/round-template.md](references/round-template.md)，
字段沿用人工版并新增【通道状态】【执行方式】两行。

## 四、现场常见情形对照

| 情形 | 通道侧动作 | 注意 |
|---|---|---|
| 通道刚起，还没确认过设备归属 | 先 `tabs` + `screen` 认设备 | 认完再谈命令 |
| 命令回显带分页（`---- More ----`） | 人工版规则：不新增关分页命令，请操作人按既有惯例处理 | 不要经 REST 空格翻页刷屏 |
| 需要切视图 | 入口与查询分开，等操作人确认进入正确视图 | 不把 `enter/query/exit` 串成批处理 |
| 回显拿到的可能不是最新 | 确认滚动缓冲深度；必要时改用 `/screen` 分屏 | 别把旧回显当本轮结果 |
| 客户就在电脑前 | 用 `capture` 看现场，必要时 `cinput` 协助操作 | `cinput` 会占云电脑剪贴板；不要让使用者觉得被抢控制 |
| 需要 MSE/SR 变更 | 派云网调度中心 | 通道再方便也不发变更命令 |
| 工单即将超时 | 立即给派单/升级建议，附已查证据 | 通道排查不是延迟派单的挡箭牌 |

## 五、收工

1. 停止 REST 服务：`POST /api/v1/stop`（本机或经桥）。
2. 清理云电脑侧临时文件与桥脚本：`clouddesk-diag.exe exec "del C:\Users\Public\scrt_api.ps1 C:\Users\Public\scrt_out.txt"`。
3. 归档证据目录，写明工单标识、轮次、设备别名、取值时间。
4. 阶段性记录交给操作人：已查事实、未查项、派单/受理状态、下一步。

## 六、边界

- 本技能不生成设备变更命令，不扩大 4A 白名单，不代表任何权限。
- AI 不代点 4A、不登录设备、不自建通道；REST 服务与云电脑通道都是**操作人自己已经建好**的本地能力。
- 内网数据经操作人按单位规定审核脱敏后搬运；不收集 4A 账号、密码、令牌。
- 工单对象、客户信息、拓扑按单位规则脱敏；同一对象保持一致别名。
