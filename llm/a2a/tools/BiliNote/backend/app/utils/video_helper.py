import shutil
from pathlib import Path

from dotenv import load_dotenv
import subprocess
import os
import uuid
load_dotenv()
api_path = os.getenv("API_BASE_URL", "http://localhost")
BACKEND_PORT= os.getenv("BACKEND_PORT", 8483)

BACKEND_BASE_URL = f"{api_path}:{BACKEND_PORT}"

# 截图压缩配置
SCREENSHOT_MAX_WIDTH = int(os.getenv("SCREENSHOT_MAX_WIDTH", "1280"))  # 最大宽度
SCREENSHOT_QUALITY = int(os.getenv("SCREENSHOT_QUALITY", "75"))  # JPG质量 1-100
SCREENSHOT_CROP_TOP = int(os.getenv("SCREENSHOT_CROP_TOP", "40"))  # 裁剪顶部像素
SCREENSHOT_CROP_BOTTOM = int(os.getenv("SCREENSHOT_CROP_BOTTOM", "60"))  # 裁剪底部像素（任务栏等）

from typing import Optional
def generate_screenshot(video_path: str, output_dir: str, timestamp: int, index: int) -> str:
    """
    使用 ffmpeg 生成截图并压缩+裁剪，返回生成图片路径
    
    处理策略：
    1. 裁剪上下边缘（去掉浏览器标签栏、任务栏等）
    2. 限制最大宽度（保持比例）
    3. 降低 JPG 质量（默认75）
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    filename = f"screenshot_{index:03}_{uuid.uuid4()}.jpg"
    output_path = output_dir / filename

    # ffmpeg 质量参数：-q:v 范围 2-31，数字越大质量越低
    ffmpeg_quality = max(2, min(31, int(31 - (SCREENSHOT_QUALITY / 100) * 29)))

    # 构建滤镜链：先裁剪，再缩放
    # crop=in_w:in_h-top-bottom:0:top 表示：宽度不变，高度减去上下裁剪，从(0,top)开始
    crop_filter = f"crop=in_w:in_h-{SCREENSHOT_CROP_TOP}-{SCREENSHOT_CROP_BOTTOM}:0:{SCREENSHOT_CROP_TOP}"
    scale_filter = f"scale='min({SCREENSHOT_MAX_WIDTH},iw)':-1"
    
    command = [
        "ffmpeg",
        "-ss", str(timestamp),
        "-i", str(video_path),
        "-frames:v", "1",
        "-vf", f"{crop_filter},{scale_filter}",  # 先裁剪，再缩放
        "-q:v", str(ffmpeg_quality),  # 压缩质量
        str(output_path),
        "-y"
    ]

    print(f"Running command: {' '.join(command)}")
    result = subprocess.run(command, capture_output=True, text=True)

    if result.returncode != 0:
        print("ffmpeg failed:", result.stderr)

    return str(output_path)



def save_cover_to_static(local_cover_path: str, subfolder: Optional[str] = "cover") -> str:
    """
    将封面图片保存到 static 目录下，并返回前端可访问的路径
    :param local_cover_path: 本地原封面路径（比如提取出来的jpg）
    :param subfolder: 子目录，默认是 cover，可以自定义
    :return: 前端访问路径，例如 /static/cover/xxx.jpg
    """
    # 项目根目录
    project_root = os.getcwd()

    # static目录
    static_dir = os.path.join(project_root, "static")

    # 确定目标子目录
    target_dir = os.path.join(static_dir, subfolder or "cover")
    os.makedirs(target_dir, exist_ok=True)

    # 拷贝文件
    file_name = os.path.basename(local_cover_path)
    target_path = os.path.join(target_dir, file_name)
    shutil.copy2(local_cover_path, target_path)  # 保留原时间戳、权限
    image_relative_path = f"/static/{subfolder}/{file_name}".replace("\\", "/")
    url_path = f"{BACKEND_BASE_URL.rstrip('/')}/{image_relative_path.lstrip('/')}"
    # 返回前端可访问的路径
    return url_path
