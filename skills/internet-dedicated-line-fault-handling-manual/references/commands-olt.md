# OLT手动查询命令

来源：原技能 `scripts/command_catalog.py`，目录版本 `2026-09-11.1`；视图入口与限制来自工作区《上网专线故障预处理标准动作与流程》第八节。以下为本技能内置静态参考，不依赖原技能运行，也不宣称完成全部型号/版本现场验证。

查询命令来源工作表为 `OLT指令需求`。完整编号为“设备前缀.动作”。花括号均为待核实参数，不直接执行。读取配置不等于修改配置；进入配置视图也不代表有权变更业务。

## 共同要求

- `{slot}` / `{pon}` / `{onu}` 分别是已核实槽位、PON端口、ONU ID；`{pon_port}` 是完整三段PON端口。LOID不是ONU ID，不能代入数字位置。
- `{pon_type}` 只按实际业务取 `epon` 或 `gpon`；`{lag}` 是目标聚合编号。上联参数来自台账或已核对回显，不从客户端口猜测。
- 每条命令标注实际设备及当前/所需视图。需要切视图时，入口与查询分开发送；先等待操作人确认进入正确视图，再给该视图内查询。不将进入、查询、退出串成批处理。
- “基础查询视图”指操作人已确认本设备支持该条命令的视图，不推定所有型号相同。未列前置、返回或退出命令不自行补充。
- PON、板卡、聚合、整机范围查询需注明会涉及其他用户，确认范围/开销及授权后再给可执行命令，不遍历、不并发、不循环刷取。若仅有宽范围模板，不改造未经核验的单用户语法。
- 只有LOID时，仅下方已确认适用的中兴EPON模板可用于定位；其他场景请求服保资源或经确认的手册。

## 华为OLT

前缀：`huawei_olt`。框号 `0` 是原模板限定，现场不匹配时停止使用，不能擅自改写适配。

| 动作 | 命令模板 | 所需视图 / 范围 | 来源 |
|---|---|---|---|
| state | `display ont info 0 {slot} {pon} {onu}` | 基础查询 / 目标ONU | B7 |
| alarm | `display alarm history alarmparameter 0/{slot}/{pon} {onu} list` | 基础查询 / 目标ONU | B8 |
| mac | `display mac-address port 0/{slot}/{pon} ont {onu}` | 基础查询 / 目标ONU | B3 |
| config | `display current-configuration ont 0/{slot}/{pon} {onu}` | 基础查询 / 目标ONU | B4 |
| optics | `display ont optical-info {pon} {onu}` | 对应PON板 / 目标ONU | B5 |
| traffic | `display ont traffic {pon} {onu}` | 对应PON板 / 目标ONU | B6 |
| aggregate | `display link-aggregation all` | 基础查询 / 整机聚合 | B9 |
| board | `display board 0/{uplink_slot}` | 基础查询 / 上联板 | B10 |
| lacp | `display lacp link-aggregation verbose {lag}` | 基础查询 / 目标聚合 | B11 |

已列视图入口：`interface {pon_type} 0/{slot}`，来源原手册8.1光信息行，编号 `huawei_olt.enter_pon`。`{pon_type}` 必须择定EPON/GPON。入口所需当前视图或其他前置命令不明时先确认，不追加提权或配置入口。

## 中兴OLT

前缀：C600用 `zte_c600_olt`，C300用 `zte_c300_olt`。框号 `1` 为原模板限定；基础查询视图及版本适配须核验。以下保留型号间下划线/连字符差异，不互换。

| 动作 | C600模板 | C300模板 | 范围 / 来源 |
|---|---|---|---|
| mac | `show mac int {pon_type}_onu-1/{slot}/{pon}:{onu}` | `show mac int {pon_type}-onu_1/{slot}/{pon}:{onu}` | 目标ONU / E3 |
| config | `show collection pon-onu {pon_type}_onu-1/{slot}/{pon}:{onu} config` | `show running-config-interface {pon_type}-onu_1/{slot}/{pon}:{onu} config` | 目标ONU / E4 |
| optics | `show pon power onu-rx {pon_type}_olt-1/{slot}/{pon}` | `show pon power onu-rx {pon_type}-olt_1/{slot}/{pon}` | 整PON / E6 |
| state | `show {pon_type} onu state {pon_type}_onu-1/{slot}/{pon}` | `show {pon_type} onu state {pon_type}-onu_1/{slot}/{pon}` | 整PON / E7 |
| detail | `show {pon_type} onu detail-info {pon_type}_onu-1/{slot}/{pon}:{onu}` | `show {pon_type} onu detail-info {pon_type}-onu_1/{slot}/{pon}:{onu}` | 目标ONU / E8 |
| traffic | `show interface {pon_type}_onu-1/{slot}/{pon}:{onu}` | `show interface {pon_type}-onu_1/{slot}/{pon}:{onu}` | 目标ONU / E9 |

两型号在原目录共有的查询：

| 动作 | 命令模板 | 范围 / 来源 |
|---|---|---|
| aggregate_config | `show running-config-interface smartgroup{lag}` | 目标聚合 / E5 |
| lacp | `show lacp {lag} internal` | 目标聚合 / E10 |
| uplink | `show interface xgei-1/{uplink}` | 已知上联；`uplink`为两段编号 / E11 |
| loid | `show epon onu by loid {loid}` | LOID定位，仅已确认适用的EPON / E12 |

`loid` 不自动改成GPON语法。`state` 等原表模板若报语法错误，保留型号、视图和报错，交维护方核验，不自动试其他拼写。

## 烽火AN6000

前缀：`fiberhome_an6000_olt`。

| 动作 | 命令模板 | 所需视图 / 范围 | 来源 |
|---|---|---|---|
| mac | `show onu mac-address {onu}` | 对应PON接口 / 目标ONU | H3 |
| config | `show onu running-config {pon_port} {onu}` | 配置 / 目标ONU | H4 |
| aggregate_config | `show lacp running-config` | diagnose / 整机，特殊审批 | H5 |
| optics | `show onu optical-info {onu}` | 对应PON接口 / 目标ONU | H6 |
| state | `show authorization {pon_port}` | 配置 / 整PON | H7 |
| detail | `show onu state {onu}` | 对应PON接口 / 目标ONU | H8 |
| traffic | `show onu traffic-record slot {slot} pon all onu all` | diagnose / 整板，特殊审批 | H9 |
| lacp | `show lacp channel-group trunks` | 配置 / 整机聚合 | H10 |
| uplink | `show port state` | 对应以太接口 / 目标上联 | H11 |

原手册8.3列出的入口，仍需确认当前视图、权限与目标：

| 入口编号 | 命令模板 | 条件与来源 |
|---|---|---|
| enter_config | `config` | 进入配置视图仅为后续查询；H3/H4对应视图步骤 |
| enter_pon | `interface pon {pon_port}` | 从配置视图进入已知PON接口；H3/H6/H8步骤 |
| enter_eth | `interface eth {eth_port}` | 从配置视图进入已知三段上联端口；H11步骤 |
| enter_diagnose | `diagnose` | 配置视图的特殊入口，须维护方确认；H5/H9步骤 |

`diagnose` 及相关查询不是默认必做项。进入前须设备维护方确认型号适配、执行开销及4A放行，并由操作人明确确认本轮执行。

## 烽火AN5000

前缀：`fiberhome_an5000_olt`。

| 动作 | 命令模板 | 所需视图 / 范围 | 来源 |
|---|---|---|---|
| mac | `show mac-address port {pon_port} onu {onu}` | Admin / 目标ONU | H3 |
| config | `show running-config slot {slot} pon {pon} onu {onu}` | Admin / 目标ONU | H4 |
| aggregate_config | `show lacp running-config` | protocol/lacp / 整机聚合 | H5 |
| optics | `show onu optical-info slot {slot} pon {pon} onu all` | onu / 整PON | H6 |
| state | `show authorization slot {slot} pon {pon}` | onu / 整PON | H7 |
| detail | `show onu state-info slot {slot} pon {pon} onu {onu}` | onu / 目标ONU | H8 |
| traffic | `show onu traffic record slot {slot} pon {pon} onu all` | DEBUG_H / 整PON，特殊审批 | H9 |
| lacp | `show lacp channel-group trunks` | protocol/lacp / 整机聚合 | H10 |
| uplink | `show uplink slot {uplink_slot} port {uplink_port}` | interface / 目标上联 | H11 |

原手册8.3列出的入口：

| 入口编号 | 命令 | 起点与来源 |
|---|---|---|
| enter_protocol | `cd protocol` | Admin，H5步骤 |
| enter_lacp | `cd lacp` | protocol，H5步骤 |
| enter_onu | `cd onu` | Admin，H8步骤 |
| enter_debug | `lll` | 原表H9的DEBUG_H入口，起点/适配待维护方核实，特殊审批 |

不得因原表列有 `lll` 就默认允许使用。DEBUG_H入口及查询须设备维护方确认适配、开销、放行和起始视图，操作人明确确认本轮执行后才可列为待执行命令。`interface` 视图未提供入口，不自行编造；请操作人按已授权流程进入并确认。
