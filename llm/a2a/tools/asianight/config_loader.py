"""
ASIANIGHT配置加载器
从SmartSisi的system.conf读取配置
"""

import os
import configparser
from pathlib import Path
from typing import Dict, Any, Optional

class AsianightConfig:
    """ASIANIGHT配置管理器"""
    
    def __init__(self, config_path: Optional[str] = None):
        """
        初始化配置
        
        Args:
            config_path: system.conf路径，默认自动查找
        """
        # 自动查找system.conf
        if config_path is None:
            # 从当前文件位置向上查找
            current = Path(__file__).resolve()
            for parent in current.parents:
                conf_file = parent / "system.conf"
                if conf_file.exists():
                    config_path = str(conf_file)
                    break
        
        if config_path is None:
            raise FileNotFoundError("未找到system.conf配置文件")
        
        self.config_path = config_path
        self.config = configparser.ConfigParser()
        self.config.read(config_path, encoding='utf-8')
        
        print(f"✅ 加载配置: {config_path}")
    
    def _get(self, section: str, key: str, default: Any = None) -> Any:
        """安全获取配置"""
        try:
            value = self.config.get(section, key)
            # 处理空值
            if value == '':
                return default
            return value
        except (configparser.NoSectionError, configparser.NoOptionError):
            return default
    
    def get_decision_model_config(self) -> Dict[str, Any]:
        """
        获取采集决策模型配置
        用途：判定哪些内容需要采集（快速、低成本）
        """
        return {
            'api_key': self._get('key', 'asianight_decision_api_key', ''),
            'base_url': self._get('key', 'asianight_decision_base_url', 'https://www.dmxapi.cn/v1'),
            'model': self._get('key', 'asianight_decision_model', 'gpt-4o-mini'),
            'temperature': float(self._get('key', 'asianight_decision_temperature', '0.3')),
            'max_tokens': int(self._get('key', 'asianight_decision_max_tokens', '1000')),
            'enabled': self._get('key', 'asianight_decision_enabled', 'true').lower() == 'true'
        }
    
    def get_organize_model_config(self) -> Dict[str, Any]:
        """
        获取内容整理模型配置
        用途：视频/图片/封面信息提取和分类（推理能力强）
        """
        return {
            'api_key': self._get('key', 'asianight_organize_api_key', ''),
            'base_url': self._get('key', 'asianight_organize_base_url', 'https://www.dmxapi.cn/v1'),
            'model': self._get('key', 'asianight_organize_model', 'gpt-4o'),
            'temperature': float(self._get('key', 'asianight_organize_temperature', '0.2')),
            'max_tokens': int(self._get('key', 'asianight_organize_max_tokens', '2000')),
            'enabled': self._get('key', 'asianight_organize_enabled', 'true').lower() == 'true'
        }
    
    def get_rewrite_model_config(self) -> Dict[str, Any]:
        """
        获取洗稿优化模型配置
        用途：AI理解视频内容并重新创作文章（创作能力强）
        """
        return {
            'api_key': self._get('key', 'asianight_rewrite_api_key', ''),
            'base_url': self._get('key', 'asianight_rewrite_base_url', 'https://www.dmxapi.cn/v1'),
            'model': self._get('key', 'asianight_rewrite_model', 'claude-3.5-sonnet'),
            'temperature': float(self._get('key', 'asianight_rewrite_temperature', '0.8')),
            'max_tokens': int(self._get('key', 'asianight_rewrite_max_tokens', '4000')),
            'enabled': self._get('key', 'asianight_rewrite_enabled', 'true').lower() == 'true'
        }
    
    def get_extend_model_config(self) -> Dict[str, Any]:
        """
        获取扩展功能模型配置
        用途：后期功能扩展预留（通用大模型）
        """
        return {
            'api_key': self._get('key', 'asianight_extend_api_key', ''),
            'base_url': self._get('key', 'asianight_extend_base_url', 'https://www.dmxapi.cn/v1'),
            'model': self._get('key', 'asianight_extend_model', 'gemini-2.5-flash-lite'),
            'temperature': float(self._get('key', 'asianight_extend_temperature', '0.5')),
            'max_tokens': int(self._get('key', 'asianight_extend_max_tokens', '3000')),
            'enabled': self._get('key', 'asianight_extend_enabled', 'true').lower() == 'true'
        }
    
    def get_telegram_config(self) -> Dict[str, Any]:
        """获取Telegram配置"""
        return {
            'api_id': self._get('key', 'asianight_telegram_api_id', ''),
            'api_hash': self._get('key', 'asianight_telegram_api_hash', ''),
            'phone': self._get('key', 'asianight_telegram_phone', '')
        }
    
    def get_asianight_api_config(self) -> Dict[str, Any]:
        """获取ASIANIGHT网站API配置"""
        return {
            'api_url': self._get('key', 'asianight_api_url', ''),
            'api_key': self._get('key', 'asianight_api_key', ''),
            'author': self._get('key', 'asianight_api_author', 'ASIANIGHT智能体')
        }
    
    def get_scraper_config(self) -> Dict[str, Any]:
        """获取采集配置"""
        return {
            'limit': int(self._get('key', 'asianight_scraper_limit', '100')),
            'interval': int(self._get('key', 'asianight_scraper_interval', '5')),
            'watermark_enabled': self._get('key', 'asianight_watermark_enabled', 'true').lower() == 'true'
        }
    
    def get_all_config(self) -> Dict[str, Any]:
        """获取完整配置"""
        return {
            'decision_model': self.get_decision_model_config(),
            'organize_model': self.get_organize_model_config(),
            'rewrite_model': self.get_rewrite_model_config(),
            'extend_model': self.get_extend_model_config(),
            'telegram': self.get_telegram_config(),
            'asianight_api': self.get_asianight_api_config(),
            'scraper': self.get_scraper_config()
        }
    
    def print_config_summary(self):
        """打印配置摘要"""
        print("\n" + "="*60)
        print("📋 ASIANIGHT配置摘要")
        print("="*60)
        
        # 决策模型
        decision = self.get_decision_model_config()
        print(f"\n🎯 采集决策模型:")
        print(f"   模型: {decision['model']}")
        print(f"   状态: {'✅ 启用' if decision['enabled'] else '❌ 禁用'}")
        
        # 内容整理模型
        organize = self.get_organize_model_config()
        print(f"\n📊 内容整理模型:")
        print(f"   模型: {organize['model']}")
        print(f"   状态: {'✅ 启用' if organize['enabled'] else '❌ 禁用'}")
        
        # 洗稿模型
        rewrite = self.get_rewrite_model_config()
        print(f"\n✍️  洗稿优化模型:")
        print(f"   模型: {rewrite['model']}")
        print(f"   状态: {'✅ 启用' if rewrite['enabled'] else '❌ 禁用'}")
        
        # 扩展模型
        extend = self.get_extend_model_config()
        print(f"\n🚀 扩展功能模型:")
        print(f"   模型: {extend['model']}")
        print(f"   状态: {'✅ 启用' if extend['enabled'] else '❌ 禁用'}")
        
        # Telegram
        telegram = self.get_telegram_config()
        print(f"\n📱 Telegram配置:")
        if telegram['api_id']:
            print(f"   API ID: {telegram['api_id']}")
            print(f"   手机号: {telegram['phone']}")
            print(f"   状态: ✅ 已配置")
        else:
            print(f"   状态: ⚠️  未配置（请填写system.conf）")
        
        # 采集配置
        scraper = self.get_scraper_config()
        print(f"\n⚙️  采集配置:")
        print(f"   每次采集: {scraper['limit']} 条")
        print(f"   间隔: {scraper['interval']} 秒")
        print(f"   去水印: {'✅ 启用' if scraper['watermark_enabled'] else '❌ 禁用'}")
        
        print("\n" + "="*60 + "\n")


# 全局配置实例
_config_instance = None

def get_config() -> AsianightConfig:
    """获取全局配置实例"""
    global _config_instance
    if _config_instance is None:
        _config_instance = AsianightConfig()
    return _config_instance


if __name__ == '__main__':
    # 测试
    config = AsianightConfig()
    config.print_config_summary()
    
    # 测试获取配置
    print("\n📋 详细配置:")
    import json
    all_config = config.get_all_config()
    
    # 隐藏敏感信息
    for model_key in ['decision_model', 'organize_model', 'rewrite_model', 'extend_model']:
        if 'api_key' in all_config[model_key]:
            key = all_config[model_key]['api_key']
            if key:
                all_config[model_key]['api_key'] = key[:10] + '...' + key[-10:] if len(key) > 20 else '***'
    
    print(json.dumps(all_config, ensure_ascii=False, indent=2))



