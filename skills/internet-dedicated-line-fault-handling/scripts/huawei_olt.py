#$language = "Python"
#$interface = "1.0"

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from securecrt_query_common import run_script


SETTINGS = {
    "system": "OLT",
    "vendor": "华为",
    "device_type": "OLT",
    "vendor_id": "huawei",
    "device_id": "olt",
    "allow_multiple": False,
    "mode_warning": "部分查询会进入PON接口视图。脚本只执行参考表中的查询命令，不会自动执行未提供的退出命令；查询结束后请人工确认并返回原视图。",
}

PON_FIELDS = [("slot", "槽位号 x（0/x/y中的x）", "1"), ("pon", "PON口号 y（0/x/y中的y）", "1")]
ONU_FIELDS = PON_FIELDS + [("onu", "ONT编号 z", "1")]

OPERATIONS = [
    {"name": "查看ONT MAC地址学习", "fields": ONU_FIELDS, "commands": ["display mac-address port 0/{slot}/{pon} ont {onu}"]},
    {"name": "查看具体ONT业务配置", "fields": ONU_FIELDS, "commands": ["display current-configuration ont 0/{slot}/{pon} {onu}"]},
    {"name": "查看ONT用户光衰", "fields": [("pon_type", "PON类型（epon或gpon）", "gpon"), ("slot", "槽位号 x", "1"), ("pon", "PON口号 y", "1"), ("onu", "ONT编号 z", "1"), ("interface_prompt", "进入PON接口后的完整提示符", "[OLT-GPON0/1]")], "commands": [{"text": "interface {pon_type} 0/{slot}", "expect": "{interface_prompt}"}, {"text": "display ont optical-info {pon} {onu}", "expect": "{interface_prompt}"}]},
    {"name": "查看ONT用户流量", "fields": [("pon_type", "PON类型（epon或gpon）", "gpon"), ("slot", "槽位号 x", "1"), ("pon", "PON口号 y", "1"), ("onu", "ONT编号 z", "1"), ("interface_prompt", "进入PON接口后的完整提示符", "[OLT-GPON0/1]")], "commands": [{"text": "interface {pon_type} 0/{slot}", "expect": "{interface_prompt}"}, {"text": "display ont traffic {pon} {onu}", "expect": "{interface_prompt}"}]},
    {"name": "查看ONT用户状态", "fields": ONU_FIELDS, "commands": ["display ont info 0 {slot} {pon} {onu}"]},
    {"name": "查看ONT用户离线告警", "fields": ONU_FIELDS, "commands": ["display alarm history alarmparameter 0/{slot}/{pon} {onu} list"]},
    {"name": "查看上行聚合配置", "fields": [], "commands": ["display link-aggregation all"]},
    {"name": "查看上行板卡状态", "fields": [("slot", "上行板卡槽位号", "1")], "commands": ["display board 0/{slot}"]},
    {"name": "查看上行LACP状态", "fields": [("lag", "链路聚合组编号", "1")], "commands": ["display lacp link-aggregation verbose {lag}"]},
]

run_script(crt, SETTINGS, OPERATIONS)
