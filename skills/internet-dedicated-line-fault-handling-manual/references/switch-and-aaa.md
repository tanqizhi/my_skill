# 交换机与3A人工查询

## 华为交换机

来源：原技能 `scripts/command_catalog.py`，目录版本 `2026-09-11.1`；原工作表 `交换机设备` A3～A6。完整编号前缀为 `huawei_switch`。

前提：已核对目标交换机、型号适配、当前查询视图、目标接口和授权；`{member}` 为三段端口编号。模板保持原接口名称/编号间空格写法，不擅自修改以试错。下面都是指定接口的只读查询。

| 动作 | 命令模板 | 来源 |
|---|---|---|
| config | `display curr interface GigabitEthernet{member}` | A3 |
| mac | `display mac-address GigabitEthernet{member}` | A4 |
| interface | `display interface GigabitEthernet{member}` | A5 |
| optics | `display transceiver interface GigabitEthernet {member} verbose` | A6 |

只查工单相关接口；需看上联时先核对台账及授权。不扩大到全网MAC搜索，不补造日志或其他厂商命令。

## 3A/AAA认证系统

来源：工作区《上网专线故障预处理标准动作与流程》中AAA能力及交付限制。3A在本技能中是人工Web查询，不是设备CLI；没有内置API、SQL或后台命令。

先确认本地系统已开放对应能力和查询权限。给操作人的查询任务必须包含：目标系统/页面（仅在已知时写真实名称）、查询账号或批准使用的标识、时间范围、所需字段与用途。未提供界面手册时不能编造菜单点击路径。

可按实际已开放字段请求：

- 用户/账号状态及对应查询时间。
- 在线状态及可见会话信息。
- 拨号错误原文、错误码和发生时间。
- 上下线记录；原材料提及近7天，实际可查窗口以已开放系统为准，不假定一定具备。

回传页面可见文字或脱敏截图即可，不索取账号密码、登录令牌或Cookie。字段不存在、能力未交付或无权限时记“未完成/不可用”，继续可做的设备侧查询或派单协查，不能作为认证正常的证据。
