# MSE/SR手动查询命令

来源：原技能 `scripts/command_catalog.py`，目录版本 `2026-09-11.1`，以及工作区《上网专线故障预处理标准动作与流程》中的使用边界。以下保留原目录模板与工作表/单元格来源，不代表已在所有设备版本上实测。

不依赖原技能文件运行；本表可独立使用。根据设备类型选择前缀 `huawei_mse` / `huawei_sr`、`zte_mse` / `zte_sr`、`h3c_mse` / `h3c_sr`，完整编号为“前缀.动作”。来源工作表统一为 `MSE、SR指令需求`。

## 参数与执行条件

- 当前岗位对MSE/SR/BRAS只有查看权限；本表不提供变更命令。需要配置修改、清表、会话刷新、强制下线或重启时，停止本轮查询并派云网调度中心接手。
- BRAS仅使用已确认适配该设备且获准执行的查询手册，不因名称相近直接套用MSE/SR模板，也不新增未经核验的命令。
- `{username}` / `{user_ip}` / `{mac}` 为已核对的用户账号/IP/WAN MAC，不是设备管理IP或ONU自身MAC。
- `{subif}` 为聚合编号和子接口号，例如 `17.100`，不含接口类型；示例不得作为实际工单值。
- `{lag}` 为聚合编号；`{member}` 为原模板要求的三段成员编号。不得擅自改变接口名称、前缀或分隔符以适配另一种端口。
- `{vpn}` 必须是本业务实际实例。只有已明确属于全局表才用 `route_global` / `ping_global`；未知实例不是全局。
- `{source_ip}` 为发起设备在对应上下文可用的本地地址，不能直接拿客户IP当源；`{target_ip}` 为工单相关目的地址。
- 模板中的花括号不能直接执行。先核验实际型号/版本、当前查询视图与4A放行；本表未提供前置提权、进入或退出视图命令，不自行补加。
- 除Ping为主动探测，其余为只读查询。Ping只做有限次默认探测；无法确认可有界结束时先核验，不添加持续、洪泛、大包等参数。

## 华为

| 动作 | 命令模板 | 来源单元格 |
|---|---|---|
| session_username | `display access-user username {username}` | C5 |
| session_user_ip | `display access-user ip-address {user_ip}` | C4 |
| session_mac | `display access-user mac-address {mac}` | C3 |
| fail_username | `display aaa online-fail-record username {username}` | C11 |
| fail_mac | `display aaa online-fail-record mac-address {mac}` | C10 |
| offline_username | `display aaa offline-fail-record username {username}` | C13 |
| offline_mac | `display aaa offline-fail-record mac-address {mac}` | C12 |
| config | `display current-configuration interface Eth-Trunk {subif}` | C18 |
| interface | `display interface Eth-Trunk {subif}` | C8 |
| aggregate | `display interface Eth-Trunk` | C7 |
| member | `display interface GigabitEthernet {member}` | C9 |
| arp | `display arp interface Eth-Trunk {subif}` | C23 |
| route_global | `display ip routing-table {target_ip}` | C14 |
| route_vpn | `display ip routing-table vpn-instance {vpn} {target_ip}` | C15 |
| ping_global | `ping -a {source_ip} {target_ip}` | C16 |
| ping_vpn | `ping -vpn-instance {vpn} -a {source_ip} {target_ip}` | C17 |

`aggregate` 原模板无聚合编号，不能擅自补号或认为只查目标聚合；先确认查询范围、开销及授权，不适合则交维护方补证。本表未列华为MSE专用LACP查询，不拿OLT命令套用。

## 中兴

| 动作 | 命令模板 | 来源单元格 |
|---|---|---|
| session_username | `show subscriber user-name {username}` | F5 |
| session_user_ip | `show subscriber ipv4-address {user_ip}` | F4 |
| session_mac | `show subscriber user-mac {mac}` | F3 |
| fail_username | `show online-fail-record user-name {username}` | F12 |
| fail_mac | `show online-fail-record user-mac {mac}` | F11 |
| offline_username | `show offline-exception-record user-name {username}` | F14 |
| offline_mac | `show offline-exception-record user-mac {mac}` | F13 |
| config | `show running-config-interface smartgroup{subif}` | F6 |
| interface | `show interface smartgroup{subif}` | F9 |
| aggregate | `show interface smartgroup{lag}` | F7 |
| lacp | `show lacp {lag} internal` | F8 |
| member | `show interface xgei-0/{member}` | F10 |
| arp | `show arp interface smartgroup{subif}` | F19 |
| route_global | `show ip forwarding route {target_ip}` | F15 |
| route_vpn | `show IP forwarding route vrf {vpn} {target_ip}` | F16 |
| ping_global | `ping {target_ip} source {source_ip}` | F17 |
| ping_vpn | `ping vrf {vpn} {target_ip} source {source_ip}` | F18 |

## 华三

PPPoE与IPoE会话查询二选一，业务方式不明先确认，不以另一类查询无结果判离线。

| 动作 | 命令模板 | 来源单元格 |
|---|---|---|
| session_pppoe_username | `display ppp access-user username {username}` | I5 |
| session_pppoe_user_ip | `display ppp access-user ip-address {user_ip}` | I4 |
| session_pppoe_mac | `display ppp access-user mac-address {mac}` | I3 |
| session_ipoe_username | `display ip subscriber session username {username}` | I5 |
| session_ipoe_user_ip | `display ip subscriber session ip {user_ip}` | I4 |
| session_ipoe_mac | `display ip subscriber session mac {mac}` | I3 |
| fail_username | `display aaa online-fail-record username {username}` | I12 |
| fail_mac | `display aaa online-fail-record mac-address {mac}` | I11 |
| offline_username | `display aaa offline-record username {username}` | I14 |
| offline_mac | `display aaa offline-record mac-address {mac}` | I13 |
| config | `display current-configuration interface Route-Aggregation {subif}` | I6 |
| interface | `display interface Route-Aggregation {subif}` | I9 |
| aggregate | `display interface Route-Aggregation {lag}` | I7 |
| lacp | `display link-aggregation verbose Route-Aggregation {lag}` | I8 |
| member | `display interface ten-GigabitEthernet {member}` | I10 |
| arp | `display arp interface Route-Aggregation {subif}` | I24 |
| route_global | `display ip routing-table {target_ip}` | I15 |
| route_vpn | `display ip routing-table vpn-instance {vpn} {target_ip}` | I16 |
| ping_global | `ping -a {source_ip} {target_ip}` | I17 |
| ping_vpn | `ping -vpn-instance {vpn} -a {source_ip} {target_ip}` | I18 |

## 结果边界

`offline_*` 只称“下线相关记录”，按设备实际语义和时间窗口解释，不声称涵盖全部掉线历史。ARP命令限定接口，须确认接口归属实例；路由记录实际匹配前缀/掩码，不将默认或汇总路由称为客户/32。配置查询需要已知接口，不能宣称按IP直接反查子接口。
