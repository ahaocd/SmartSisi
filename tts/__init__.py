from utils import config_util

def get_engine():
    tts_type = config_util.tts_module or config_util.tts_type or "siliconflow"
    if tts_type == "gptsovits":
        from tts.gptsovits import Speech
        return Speech()
    elif tts_type == "gptsovits_v3":
        from tts.gptsovits_v3 import Speech
        return Speech()
    elif tts_type == "siliconflow":
        from tts.siliconflow_tts import Speech
        return Speech()
    else:
        from tts.siliconflow_tts import Speech
        return Speech()
