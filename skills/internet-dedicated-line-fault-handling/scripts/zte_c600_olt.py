#$language = "Python"
#$interface = "1.0"

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from securecrt_query_common import run_script


SETTINGS = {"system": "OLT", "vendor": "中兴", "device_type": "C600 OLT", "vendor_id": "zte", "device_id": "c600_olt"}
ONU_FIELDS = [("pon_type", "PON类型（epon或gpon）", "gpon"), ("slot", "槽位号 x", "1"), ("pon", "PON口号 y", "1"), ("onu", "ONU编号 z", "1")]

OPERATIONS = [
    {"name": "查看ONU上报MAC", "fields": ONU_FIELDS, "commands": ["show mac int {pon_type}_onu-1/{slot}/{pon}:{onu}"]},
    {"name": "查看ONU配置", "fields": ONU_FIELDS, "commands": ["show collection pon-onu {pon_type}_onu-1/{slot}/{pon}:{onu} config"]},
    {"name": "查看OLT聚合组配置", "fields": [("smartgroup", "smartgroup编号", "1")], "commands": ["show running-config-interface smartgroup{smartgroup}"]},
    {"name": "查看PON口下挂ONU收光", "fields": ONU_FIELDS[:-1], "commands": ["show pon power onu-rx {pon_type}_olt-1/{slot}/{pon}"]},
    {"name": "查看PON口下挂ONU状态", "fields": ONU_FIELDS[:-1], "commands": ["show {pon_type} onu state {pon_type}_onu-1/{slot}/{pon}"]},
    {"name": "查看光猫离线原因", "fields": ONU_FIELDS, "commands": ["show {pon_type} onu detail-info {pon_type}_onu-1/{slot}/{pon}:{onu}"]},
    {"name": "查看ONU流量等情况", "fields": ONU_FIELDS, "commands": ["show interface {pon_type}_onu-1/{slot}/{pon}:{onu}"]},
    {"name": "查看上行口LACP协议状态", "fields": [("lacp", "LACP组编号", "1")], "commands": ["show lacp {lacp} internal"]},
    {"name": "查看上联口状态", "fields": [("uplink", "上联接口全名", "xgei-1/1/1")], "commands": ["show interface {uplink}"]},
    {"name": "通过LOID查询用户所在PON口", "fields": [("loid", "用户LOID", "")], "commands": ["show epon onu by loid {loid}"]},
]

run_script(crt, SETTINGS, OPERATIONS)
