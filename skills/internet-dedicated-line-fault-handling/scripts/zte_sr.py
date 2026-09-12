#$language = "Python"
#$interface = "1.0"

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from securecrt_query_common import run_script


SETTINGS = {"system": "SR", "vendor": "中兴", "device_type": "SR", "vendor_id": "zte", "device_id": "sr"}

OPERATIONS = [
    {"name": "全局查看指定IP路由", "fields": [("target_ip", "目标IP地址", "192.0.2.10")], "commands": ["show ip forwarding route {target_ip}"]},
    {"name": "VPN实例查看指定IP路由", "fields": [("vpn", "VRF名称", "CTVPN2700001-ITMS"), ("target_ip", "目标IP地址", "192.0.2.10")], "commands": ["show ip forwarding route vrf {vpn} {target_ip}"]},
    {"name": "全局指定源地址Ping", "fields": [("target_ip", "目标IP地址", "192.0.2.10"), ("source_ip", "源IP地址", "192.0.2.1")], "commands": ["ping {target_ip} source {source_ip}"]},
    {"name": "VPN实例指定源地址Ping", "fields": [("vpn", "VRF名称", "CTVPN2700001-ITMS"), ("target_ip", "目标IP地址", "192.0.2.10"), ("source_ip", "源IP地址", "192.0.2.1")], "commands": ["ping vrf {vpn} {target_ip} source {source_ip}"]},
    {"name": "全局查看子接口ARP表", "fields": [("subinterface", "smartgroup子接口编号", "17.97703000")], "commands": ["show arp interface smartgroup{subinterface}"]},
    {"name": "VPN业务子接口查看ARP表", "fields": [("subinterface", "smartgroup子接口编号", "17.97703000")], "commands": ["show arp interface smartgroup{subinterface}"]},
]

run_script(crt, SETTINGS, OPERATIONS)
