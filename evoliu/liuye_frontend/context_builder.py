import json
from typing import Any, Dict, List, Optional


def build_liuye_messages(
    system_messages: List[Dict[str, str]],
    recent_messages: List[Dict[str, str]],
    handoff_messages: Optional[List[Dict[str, str]]],
    user_message: Any,
) -> List[Dict[str, Any]]:
    messages: List[Dict[str, Any]] = []
    messages.extend(system_messages or [])
    messages.extend(recent_messages or [])
    if handoff_messages:
        messages.extend(handoff_messages)
    if isinstance(user_message, list):
        messages.append({"role": "user", "content": user_message})
    elif isinstance(user_message, dict):
        messages.append({"role": "user", "content": json.dumps(user_message, ensure_ascii=False)})
    else:
        messages.append({"role": "user", "content": str(user_message or "")})
    return messages

