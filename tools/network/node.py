# tools/network/node.py

import platform
import psutil


class NodeIdentity:
    _custom_name = None

    @classmethod
    def get_hostname(cls):
        return cls._custom_name if cls._custom_name else platform.node()

    @classmethod
    def set_hostname(cls, name):
        if name.strip():
            cls._custom_name = name.strip()

    @staticmethod
    def get_local_ip():
        VIRTUAL_KEYWORDS = (
            "tap", "clash", "mihomo", "meta", "wireguard", "virtual",
            "vmware", "virtualbox", "vethernet", "loopback", "hyper-v"
        )

        candidates = []
        interfaces = psutil.net_if_addrs()

        for name, addrs in interfaces.items():
            name_lower = name.lower()
            if any(k in name_lower for k in VIRTUAL_KEYWORDS):
                continue

            for addr in addrs:
                if addr.family.name == "AF_INET":
                    ip = addr.address
                    if ip.startswith(("192.168.", "10.", "172.16.")):
                        candidates.append(ip)

        return candidates[0] if candidates else "127.0.0.1"

    @classmethod
    def get_info(cls):
        return {
            "hostname": cls.get_hostname(),
            "ip": cls.get_local_ip(),
            "os": platform.system()
        }