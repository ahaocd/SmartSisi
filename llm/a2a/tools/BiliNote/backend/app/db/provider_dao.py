import json
import os
import sys
from app.db.models.providers import Provider
from app.db.models.models import Model
from app.utils.logger import get_logger
from app.db.engine import get_engine, Base, get_db

logger = get_logger(__name__)

# 默认模型列表
DEFAULT_MODELS = {
    "siliconflow": [
        "THUDM/GLM-4.1V-9B-Thinking",
        "Qwen/Qwen2.5-VL-72B-Instruct",
        "deepseek-ai/DeepSeek-V3"
    ],
    "dmxapi": [
        "gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo",
        "claude-3-5-sonnet-20241022", "claude-3-opus-20240229",
        "gemini-1.5-pro", "gemini-1.5-flash",
        "qwen-turbo", "qwen-plus", "qwen-max", "qwen-vl-max",
        "deepseek-chat", "deepseek-coder"
    ],
    "openai": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"],
    "deepseek": ["deepseek-chat", "deepseek-coder", "deepseek-reasoner"],
    "qwen": ["qwen-turbo", "qwen-plus", "qwen-max", "qwen-vl-max", "qwen-vl-plus"],
    "Claude": ["claude-3-5-sonnet-20241022", "claude-3-opus-20240229", "claude-3-haiku-20240307"],
    "gemini": ["gemini-1.5-pro", "gemini-1.5-flash", "gemini-2.0-flash-exp"],
    "groq": ["llama-3.1-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768"],
    "ollama": ["llama3", "qwen2", "mistral"]
}


def get_builtin_providers_path():
    if getattr(sys, 'frozen', False):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(__file__)
    return os.path.join(base_path, 'builtin_providers.json')


def seed_default_providers():
    db = next(get_db())
    try:
        if db.query(Provider).count() > 0:
            logger.info("Providers already exist, skipping seed.")
            # 但仍然检查并添加缺失的模型
            _seed_default_models(db)
            return

        json_path = get_builtin_providers_path()
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                providers = json.load(f)
        except Exception as e:
            logger.error(f"Failed to read builtin_providers.json: {e}")
            return

        for p in providers:
            db.add(Provider(
                id=p['id'],
                name=p['name'],
                api_key=p['api_key'],
                base_url=p['base_url'],
                logo=p['logo'],
                type=p['type'],
                enabled=p.get('enabled', 1)
            ))
        db.commit()
        logger.info("Default providers seeded successfully.")
        
        # 添加默认模型
        _seed_default_models(db)
    except Exception as e:
        logger.error(f"Failed to seed default providers: {e}")
    finally:
        db.close()


def _seed_default_models(db):
    """为每个供应商添加默认模型"""
    try:
        for provider_id, models in DEFAULT_MODELS.items():
            for model_name in models:
                # 检查模型是否已存在
                existing = db.query(Model).filter_by(
                    provider_id=provider_id, 
                    model_name=model_name
                ).first()
                if not existing:
                    db.add(Model(provider_id=provider_id, model_name=model_name))
        db.commit()
        logger.info("Default models seeded successfully.")
    except Exception as e:
        logger.error(f"Failed to seed default models: {e}")


def insert_provider(id: str, name: str, api_key: str, base_url: str, logo: str, type_: str, enabled: int = 1):
    db = next(get_db())
    try:
        provider = Provider(id=id, name=name, api_key=api_key, base_url=base_url, logo=logo, type=type_, enabled=enabled)
        db.add(provider)
        db.commit()
        logger.info(f"Provider inserted successfully. id: {id}, name: {name}, type: {type_}")
        return id
    except Exception as e:
        logger.error(f"Failed to insert provider: {e}")
    finally:
        db.close()


def get_enabled_providers():
    db = next(get_db())
    try:
        return db.query(Provider).filter_by(enabled=1).all()
    finally:
        db.close()


def get_provider_by_name(name: str):
    db = next(get_db())
    try:
        return db.query(Provider).filter_by(name=name).first()
    finally:
        db.close()


def get_provider_by_id(id: str):
    db = next(get_db())
    try:
        return db.query(Provider).filter_by(id=id).first()
    finally:
        db.close()


def get_all_providers():
    db = next(get_db())
    try:
        return db.query(Provider).all()
    finally:
        db.close()


def update_provider(id: str, **kwargs):
    db = next(get_db())
    try:
        provider = db.query(Provider).filter_by(id=id).first()
        if not provider:
            logger.warning(f"Provider {id} not found for update.")
            return

        for key, value in kwargs.items():
            if hasattr(provider, key):
                setattr(provider, key, value)

        db.commit()
        logger.info(f"Provider updated successfully. id: {id}, updated_fields: {list(kwargs.keys())}")
    except Exception as e:
        logger.error(f"Failed to update provider: {e}")
    finally:
        db.close()


def delete_provider(id: str):
    db = next(get_db())
    try:
        provider = db.query(Provider).filter_by(id=id).first()
        if provider:
            db.delete(provider)
            db.commit()
            logger.info(f"Provider deleted successfully. id: {id}")
    except Exception as e:
        logger.error(f"Failed to delete provider: {e}")
    finally:
        db.close()