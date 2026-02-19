import base64
import os
from typing import Dict, Optional

import requests

from utils import config_util


def _choose_vision_provider(persona: str) -> Dict[str, str]:
    try:
        mm_override = config_util.get_multimodal_llm_override(persona)
        if isinstance(mm_override, dict):
            base_url = str(mm_override.get("base_url") or "").strip()
            api_key = str(mm_override.get("api_key") or "").strip()
            model = str(mm_override.get("model") or "").strip()
            if base_url and api_key and model:
                return {"api_key": api_key, "base_url": base_url.rstrip("/"), "model": model}
    except Exception:
        pass

    key = str(getattr(config_util, "image_model_api_key", "") or "").strip()
    base_url = str(getattr(config_util, "image_model_base_url", "") or "").strip()
    model = str(getattr(config_util, "image_model_engine", "") or "").strip()
    if key and base_url and model:
        return {"api_key": key, "base_url": base_url.rstrip("/"), "model": model}

    llm = config_util.get_persona_llm_config(persona)
    return {
        "api_key": str(llm.get("api_key") or "").strip(),
        "base_url": str(llm.get("base_url") or "").strip().rstrip("/"),
        "model": str(llm.get("model") or "").strip(),
    }


def _to_image_content(item: Dict[str, str]) -> Optional[Dict[str, Dict[str, str]]]:
    storage = str(item.get("storage") or "")
    if storage == "url":
        url = str(item.get("url") or "").strip()
        if not url:
            return None
        return {"type": "image_url", "image_url": {"url": url}}

    p = str(item.get("path") or "").strip()
    if not p or not os.path.exists(p):
        return None
    with open(p, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    mime = str(item.get("mime") or "image/jpeg")
    return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}


def summarize_image(item: Dict[str, str], *, persona: str = "sisi") -> str:
    """
    Fallback image understanding: ask vision model for concise Chinese summary.
    """
    try:
        conf = _choose_vision_provider(persona)
        if not conf.get("api_key") or not conf.get("base_url") or not conf.get("model"):
            return ""
        image_content = _to_image_content(item)
        if not image_content:
            return ""

        prompt = (
            "请用简洁中文描述这张图片，给出关键对象、场景、可见文字（如有），"
            "控制在80字以内，不要虚构。"
        )
        payload = {
            "model": conf["model"],
            "messages": [
                {"role": "system", "content": "你是严谨的多模态解析助手。"},
                {
                    "role": "user",
                    "content": [
                        image_content,
                        {"type": "text", "text": prompt},
                    ],
                },
            ],
            "temperature": 0.1,
            "max_tokens": 180,
        }
        headers = {
            "content-type": "application/json",
            "authorization": f"Bearer {conf['api_key']}",
        }
        url = f"{conf['base_url']}/chat/completions"
        res = requests.post(url, headers=headers, json=payload, timeout=20)
        if not res.ok:
            return ""
        data = res.json() if res.headers.get("content-type", "").startswith("application/json") else {}
        choices = data.get("choices") if isinstance(data, dict) else None
        if not isinstance(choices, list) or not choices:
            return ""
        msg = choices[0].get("message", {}) if isinstance(choices[0], dict) else {}
        text = msg.get("content")
        return str(text or "").strip()
    except Exception:
        return ""
