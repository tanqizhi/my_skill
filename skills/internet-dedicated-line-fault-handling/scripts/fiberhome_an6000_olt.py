#$language = "Python"
#$interface = "1.0"

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from securecrt_query_common import run_script


SETTINGS = {
    "system": "OLT",
    "vendor": "烽火",
    "device_type": "AN6000 OLT",
    "vendor_id": "fiberhome",
    "device_id": "an6000_olt",
    "allow_multiple": False,
    "mode_warning": "AN6000部分查询会进入config、PON接口或diagnose视图。脚本不会执行参考表以外的退出命令；查询结束后请人工确认并返回原视图。",
}

PON_FIELDS = [("pon_port", "PON端口（例如1/1/1）", "1/1/1")]
ONU_FIELDS = PON_FIELDS + [("onu", "ONU编号", "1")]

OPERATIONS = [
    {"name": "查看ONU上报MAC", "fields": ONU_FIELDS, "commands": [{"text": "config", "expect": "(config)#"}, {"text": "interface pon {pon_port}", "expect": "(config-if-pon-{pon_port})#"}, {"text": "show onu mac-address {onu}", "expect": "(config-if-pon-{pon_port})#"}]},
    {"name": "查看ONU配置", "fields": ONU_FIELDS, "commands": [{"text": "config", "expect": "(config)#"}, {"text": "show onu running-config {pon_port} {onu}", "expect": "(config)#"}]},
    {"name": "查看OLT聚合组配置", "fields": [], "commands": [{"text": "config", "expect": "(config)#"}, {"text": "diagnose", "expect": "(diagnose)#"}, {"text": "show lacp running-config", "expect": "(diagnose)#"}]},
    {"name": "查看PON口下挂ONU收光", "fields": ONU_FIELDS, "commands": [{"text": "config", "expect": "(config)#"}, {"text": "interface pon {pon_port}", "expect": "(config-if-pon-{pon_port})#"}, {"text": "show onu optical-info {onu}", "expect": "(config-if-pon-{pon_port})#"}]},
    {"name": "查看PON口下挂ONU状态", "fields": PON_FIELDS, "commands": [{"text": "config", "expect": "(config)#"}, {"text": "show authorization {pon_port}", "expect": "(config)#"}]},
    {"name": "查看光猫离线原因", "fields": ONU_FIELDS, "commands": [{"text": "config", "expect": "(config)#"}, {"text": "interface pon {pon_port}", "expect": "(config-if-pon-{pon_port})#"}, {"text": "show onu state {onu}", "expect": "(config-if-pon-{pon_port})#"}]},
    {"name": "查看ONU流量", "fields": [("slot", "槽位号", "1"), ("pon", "PON口号或all", "all"), ("onu", "ONU编号或all", "all")], "commands": [{"text": "config", "expect": "(config)#"}, {"text": "diagnose", "expect": "(diagnose)#"}, {"text": "show onu traffic-record slot {slot} pon {pon} onu {onu}", "expect": "(diagnose)#"}]},
    {"name": "查看上行口LACP协议状态", "fields": [], "commands": [{"text": "config", "expect": "(config)#"}, {"text": "show lacp channel-group trunks", "expect": "(config)#"}]},
    {"name": "查看上联口状态", "fields": [("uplink", "上联ETH端口（例如1/9/1）", "1/9/1")], "commands": [{"text": "config", "expect": "(config)#"}, {"text": "interface eth {uplink}", "expect": "(config-if-eth-{uplink})#"}, {"text": "show port state", "expect": "(config-if-eth-{uplink})#"}]},
]

run_script(crt, SETTINGS, OPERATIONS)
