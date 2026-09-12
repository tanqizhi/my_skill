#$language = "Python"
#$interface = "1.0"

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from securecrt_query_common import run_script


SETTINGS = {
    "system": "OLT",
    "vendor": "烽火",
    "device_type": "AN5000 OLT",
    "vendor_id": "fiberhome",
    "device_id": "an5000_olt",
    "allow_multiple": False,
    "mode_warning": "AN5000部分查询会进入protocol、lacp、onu或DEBUG视图。脚本不会执行参考表以外的退出命令；查询结束后请人工确认并返回原视图。",
}

ONU_FIELDS = [("slot", "槽位号", "2"), ("pon", "PON口号", "2"), ("onu", "ONU编号", "9")]

OPERATIONS = [
    {"name": "查看ONU上报MAC", "fields": [("pon_port", "PON端口（例如1/1/3）", "1/1/3"), ("onu", "ONU编号", "17")], "commands": ["show mac-address port {pon_port} onu {onu}"]},
    {"name": "查看ONU配置", "fields": ONU_FIELDS, "commands": ["show running-config slot {slot} pon {pon} onu {onu}"]},
    {"name": "查看OLT聚合组配置", "fields": [], "commands": [{"text": "cd protocol", "expect": "\\protocol#"}, {"text": "cd lacp", "expect": "\\protocol\\lacp#"}, {"text": "show lacp running-config", "expect": "\\protocol\\lacp#"}]},
    {"name": "查看PON口下挂ONU收光", "fields": [("slot", "槽位号", "2"), ("pon", "PON口号", "2"), ("onu", "ONU编号或all", "all")], "commands": [{"text": "cd onu", "expect": "\\onu#"}, {"text": "show onu optical-info slot {slot} pon {pon} onu {onu}", "expect": "\\onu#"}]},
    {"name": "查看PON口下挂ONU状态", "fields": [("slot", "槽位号", "2"), ("pon", "PON口号", "2")], "commands": [{"text": "cd onu", "expect": "\\onu#"}, {"text": "show authorization slot {slot} pon {pon}", "expect": "\\onu#"}]},
    {"name": "查看光猫离线原因", "fields": ONU_FIELDS, "commands": [{"text": "cd onu", "expect": "\\onu#"}, {"text": "show onu state-info slot {slot} pon {pon} onu {onu}", "expect": "\\onu#"}]},
    {"name": "查看ONU流量", "fields": [("slot", "槽位号", "2"), ("pon", "PON口号", "2"), ("onu", "ONU编号或all", "all")], "commands": [{"text": "lll", "expect": "(DEBUG_H)>"}, {"text": "show onu traffic record slot {slot} pon {pon} onu {onu}", "expect": "(DEBUG_H)>"}]},
    {"name": "查看上行口LACP协议状态", "fields": [], "commands": [{"text": "cd protocol", "expect": "\\protocol#"}, {"text": "cd lacp", "expect": "\\protocol\\lacp#"}, {"text": "show lacp channel-group trunks", "expect": "\\protocol\\lacp#"}]},
    {"name": "查看上联口状态", "fields": [("slot", "上联槽位号", "19"), ("port", "上联端口号", "1")], "precondition": "参考表只提供了interface视图下的show命令，没有提供进入该视图的命令。请先人工进入 Admin\\interface# 视图，再运行脚本并将该视图提示符作为设备提示符。", "commands": ["show uplink slot {slot} port {port}"]},
]

run_script(crt, SETTINGS, OPERATIONS)
