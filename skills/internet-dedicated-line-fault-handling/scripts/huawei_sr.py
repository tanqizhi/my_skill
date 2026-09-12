#$language = "Python"
#$interface = "1.0"

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from securecrt_query_common import run_script


SETTINGS = {"system": "SR", "vendor": "华为", "device_type": "SR", "vendor_id": "huawei", "device_id": "sr"}

OPERATIONS = [
    {"name": "全局查看指定IP路由", "fields": [("target_ip", "目标IP地址", "192.0.2.10")], "commands": ["display ip routing-table {target_ip}"]},
    {"name": "VPN实例查看指定IP路由", "fields": [("vpn", "VPN实例名称", "CTVPN2700001-ITMS"), ("target_ip", "目标IP地址", "192.0.2.10")], "commands": ["display ip routing-table vpn-instance {vpn} {target_ip}"]},
    {"name": "全局指定源地址Ping", "fields": [("source_ip", "源IP地址", "192.0.2.1"), ("target_ip", "目标IP地址", "192.0.2.10")], "commands": ["ping -a {source_ip} {target_ip}"]},
    {"name": "VPN实例指定源地址Ping", "fields": [("vpn", "VPN实例名称", "CTVPN2700001-ITMS"), ("source_ip", "源IP地址", "192.0.2.1"), ("target_ip", "目标IP地址", "192.0.2.10")], "commands": ["ping -vpn-instance {vpn} -a {source_ip} {target_ip}"]},
    {"name": "查看Eth-Trunk子接口配置", "fields": [("subinterface", "Eth-Trunk子接口编号", "17.97703000")], "commands": ["display current-configuration interface Eth-Trunk {subinterface}"]},
    {"name": "全局查询直连路由详情", "fields": [("target_ip", "目标IP地址", "192.0.2.10")], "commands": ["display ip routing-table protocol direct | include {target_ip}"]},
    {"name": "VPN实例查询直连路由详情", "fields": [("vpn", "VPN实例名称", "CTVPN2700001-ITMS"), ("target_ip", "目标IP地址", "192.0.2.10")], "commands": ["display ip routing-table vpn-instance {vpn} protocol direct | include {target_ip}"]},
    {"name": "全局查询静态路由详情", "fields": [("target_ip", "目标IP地址", "192.0.2.10")], "commands": ["display ip routing-table protocol static | include {target_ip}"]},
    {"name": "VPN实例查询静态路由详情", "fields": [("vpn", "VPN实例名称", "CTVPN2700001-ITMS"), ("target_ip", "目标IP地址", "192.0.2.10")], "commands": ["display ip routing-table vpn-instance {vpn} protocol static | include {target_ip}"]},
    {"name": "全局查看子接口ARP表", "fields": [("subinterface", "Eth-Trunk子接口编号", "17.97703000")], "commands": ["display arp interface Eth-Trunk {subinterface}"]},
    {"name": "VPN业务子接口查看ARP表", "fields": [("subinterface", "Eth-Trunk子接口编号", "17.97703000")], "commands": ["display arp interface Eth-Trunk {subinterface}"]},
]

run_script(crt, SETTINGS, OPERATIONS)
