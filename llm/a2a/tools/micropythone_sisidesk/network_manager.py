"""
network_manager.py - sisi系统网络配置管理工具
统一管理所有设备的IP地址分配，避免冲突
"""

import json
import os
from typing import Dict, List

class SisiNetworkManager:
    """sisi系统网络管理器"""
    
    def __init__(self):
        """初始化网络管理器"""
        self.config_file = "network_config.json"
        self.device_configs = self.load_config()
        
    def load_config(self) -> Dict:
        """加载网络配置"""
        default_config = {
            "network_info": {
                "base_network": "172.20.10",
                "gateway": "172.20.10.1",
                "subnet_mask": "255.255.255.240",
                "dns": "172.20.10.1"
            },
            "devices": {
                "iPhone15_hotspot": {
                    "ip": "172.20.10.1",
                    "type": "gateway",
                    "description": "iPhone15热点网关"
                },
                "sisieyes": {
                    "ip": "172.20.10.2",
                    "type": "esp32_s3_cam",
                    "description": "SISIeyes显示设备 (ESP32-S3 CAM)",
                    "mac": "unknown",
                    "status": "active"
                },
                "sisidesk": {
                    "ip": "172.20.10.5",
                    "type": "esp32_c3",
                    "description": "sisidesk坐台设备 (ESP32-C3)",
                    "mac": "unknown",
                    "status": "configured",
                    "fixed_ip": True
                },
                "pc_main": {
                    "ip": "172.20.10.9",
                    "type": "pc",
                    "description": "主控PC (动态分配)",
                    "status": "active"
                }
            },
            "reserved_ips": [
                "172.20.10.1",  # 网关
                "172.20.10.2",  # SISIeyes
                "172.20.10.5"   # sisidesk
            ],
            "available_ips": [
                "172.20.10.3",
                "172.20.10.4", 
                "172.20.10.6",
                "172.20.10.7",
                "172.20.10.8"
            ]
        }
        
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return default_config
        else:
            self.save_config(default_config)
            return default_config
    
    def save_config(self, config: Dict = None):
        """保存网络配置"""
        if config is None:
            config = self.device_configs
            
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
    
    def get_device_ip(self, device_name: str) -> str:
        """获取设备IP地址"""
        device = self.device_configs.get("devices", {}).get(device_name)
        if device:
            return device.get("ip", "unknown")
        return "unknown"
    
    def update_device_status(self, device_name: str, status: str, actual_ip: str = None):
        """更新设备状态"""
        if device_name in self.device_configs.get("devices", {}):
            self.device_configs["devices"][device_name]["status"] = status
            if actual_ip:
                self.device_configs["devices"][device_name]["actual_ip"] = actual_ip
            self.save_config()
    
    def add_device(self, device_name: str, ip: str, device_type: str, description: str):
        """添加新设备"""
        if "devices" not in self.device_configs:
            self.device_configs["devices"] = {}
            
        self.device_configs["devices"][device_name] = {
            "ip": ip,
            "type": device_type,
            "description": description,
            "status": "configured"
        }
        
        # 更新保留IP列表
        if ip not in self.device_configs.get("reserved_ips", []):
            self.device_configs["reserved_ips"].append(ip)
            
        # 从可用IP列表中移除
        if ip in self.device_configs.get("available_ips", []):
            self.device_configs["available_ips"].remove(ip)
            
        self.save_config()
    
    def get_next_available_ip(self) -> str:
        """获取下一个可用IP"""
        available = self.device_configs.get("available_ips", [])
        if available:
            return available[0]
        
        # 如果没有预定义的可用IP，生成新的
        base = self.device_configs.get("network_info", {}).get("base_network", "172.20.10")
        reserved = self.device_configs.get("reserved_ips", [])
        
        for i in range(3, 15):  # 172.20.10.3 到 172.20.10.14
            ip = f"{base}.{i}"
            if ip not in reserved:
                return ip
                
        return "172.20.10.10"  # 默认返回
    
    def print_network_status(self):
        """打印网络状态"""
        print("=" * 60)
        print("🌐 sisi系统网络配置状态")
        print("=" * 60)
        
        network_info = self.device_configs.get("network_info", {})
        print(f"📍 网络段: {network_info.get('base_network', 'unknown')}.x")
        print(f"🌐 网关: {network_info.get('gateway', 'unknown')}")
        print(f"🔗 子网掩码: {network_info.get('subnet_mask', 'unknown')}")
        
        print(f"\n📱 设备列表:")
        devices = self.device_configs.get("devices", {})
        for name, info in devices.items():
            status_icon = "✅" if info.get("status") == "active" else "🔧" if info.get("status") == "configured" else "❌"
            fixed_icon = "🔒" if info.get("fixed_ip") else "🔄"
            print(f"   {status_icon} {fixed_icon} {info['ip']} - {name} ({info['type']})")
            print(f"      📝 {info['description']}")
            if info.get("actual_ip") and info["actual_ip"] != info["ip"]:
                print(f"      ⚠️ 实际IP: {info['actual_ip']}")
        
        print(f"\n🔒 保留IP: {', '.join(self.device_configs.get('reserved_ips', []))}")
        print(f"🆓 可用IP: {', '.join(self.device_configs.get('available_ips', []))}")
    
    def check_ip_conflicts(self) -> List[str]:
        """检查IP冲突"""
        conflicts = []
        devices = self.device_configs.get("devices", {})
        ip_map = {}
        
        for name, info in devices.items():
            ip = info.get("ip")
            if ip in ip_map:
                conflicts.append(f"IP冲突: {ip} 被 {ip_map[ip]} 和 {name} 同时使用")
            else:
                ip_map[ip] = name
                
        return conflicts
    
    def generate_micropython_config(self, device_name: str = "sisidesk") -> str:
        """生成MicroPython配置代码"""
        device = self.device_configs.get("devices", {}).get(device_name)
        if not device:
            return "# 设备未找到"
            
        network_info = self.device_configs.get("network_info", {})
        
        config_code = f"""# {device_name} 网络配置 (自动生成)
WIFI_SSID = "iPhone15"
WIFI_PASSWORD = "88888888"

# 固定IP配置 (避免冲突)
FIXED_IP = "{device['ip']}"
SUBNET_MASK = "{network_info.get('subnet_mask', '255.255.255.240')}"
GATEWAY = "{network_info.get('gateway', '172.20.10.1')}"
DNS_SERVER = "{network_info.get('dns', '172.20.10.1')}"

# 设备信息
DEVICE_NAME = "{device['description']}"
DEVICE_TYPE = "{device['type']}"
"""
        return config_code

def main():
    """主函数"""
    manager = SisiNetworkManager()
    
    print("🔧 sisi系统网络管理工具")
    manager.print_network_status()
    
    # 检查冲突
    conflicts = manager.check_ip_conflicts()
    if conflicts:
        print(f"\n⚠️ 发现IP冲突:")
        for conflict in conflicts:
            print(f"   {conflict}")
    else:
        print(f"\n✅ 无IP冲突")
    
    # 生成sisidesk配置
    print(f"\n📝 sisidesk设备配置:")
    print(manager.generate_micropython_config("sisidesk"))

if __name__ == "__main__":
    main()
