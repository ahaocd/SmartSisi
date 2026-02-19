"""
配置加载器 - 从system.conf读取配置
"""
import configparser
import os


def load_xhs_cover_config():
    """
    加载小红书封面生成配置
    
    Returns:
        dict: 配置信息
    """
    # 找到system.conf路径（在SmartSisi根目录）
    # 当前路径：SmartSisi/llm/a2a/tools/social_auto_upload/uploader/xhs_uploader
    # 目标路径：SmartSisi/system.conf
    config_path = os.path.join(
        os.path.dirname(__file__),
        "../../../../../../system.conf"
    )
    config_path = os.path.normpath(config_path)
    
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"配置文件不存在: {config_path}")
    
    config = configparser.ConfigParser()
    config.read(config_path, encoding='utf-8')
    
    return {
        # 背景图生成
        'bg_api_key': config.get('key', 'xhs_cover_bg_api_key'),
        'bg_base_url': config.get('key', 'xhs_cover_bg_base_url'),
        'bg_model': config.get('key', 'xhs_cover_bg_model'),
        
        # 标题生成
        'title_api_key': config.get('key', 'xhs_cover_title_api_key'),
        'title_base_url': config.get('key', 'xhs_cover_title_base_url'),
        'title_model': config.get('key', 'xhs_cover_title_model'),
        'title_temperature': float(config.get('key', 'xhs_cover_title_temperature', fallback='0.8')),
        'title_max_tokens': int(config.get('key', 'xhs_cover_title_max_tokens', fallback='150')),
    }


if __name__ == "__main__":
    # 测试配置加载
    try:
        config = load_xhs_cover_config()
        print("✓ 配置加载成功:")
        for key, value in config.items():
            if 'key' in key:
                print(f"  {key}: {value[:20]}...")
            else:
                print(f"  {key}: {value}")
    except Exception as e:
        print(f"✗ 配置加载失败: {str(e)}")

