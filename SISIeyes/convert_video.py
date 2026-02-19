#!/usr/bin/env python3
"""
视频转换脚本 - 将MP4转换为ESP32可播放的MJPEG格式
适配SISIeyes项目的1.47寸显示屏 (172x320)
"""

import os
import sys
import subprocess
import argparse

def check_ffmpeg():
    """检查FFmpeg是否安装"""
    try:
        subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False

def convert_to_mjpeg(input_file, output_file, width=172, height=320, fps=15, quality=5):
    """
    转换视频为MJPEG格式
    
    Args:
        input_file: 输入视频文件路径
        output_file: 输出MJPEG文件路径
        width: 目标宽度 (默认172，适配1.47寸屏)
        height: 目标高度 (默认320，适配1.47寸屏)
        fps: 目标帧率 (默认15fps，适配ESP32性能)
        quality: JPEG质量 (1-31，数字越小质量越高，默认5)
    """
    
    if not os.path.exists(input_file):
        print(f"❌ 输入文件不存在: {input_file}")
        return False
    
    if not check_ffmpeg():
        print("❌ FFmpeg未安装或不在PATH中")
        print("请安装FFmpeg: https://ffmpeg.org/download.html")
        return False
    
    print(f"🎬 开始转换视频...")
    print(f"   输入: {input_file}")
    print(f"   输出: {output_file}")
    print(f"   分辨率: {width}x{height}")
    print(f"   帧率: {fps}fps")
    print(f"   质量: {quality}")
    
    # FFmpeg命令
    cmd = [
        'ffmpeg',
        '-i', input_file,                    # 输入文件
        '-vf', f'scale={width}:{height}',    # 缩放到目标分辨率
        '-r', str(fps),                      # 设置帧率
        '-q:v', str(quality),                # JPEG质量
        '-f', 'mjpeg',                       # 输出格式为MJPEG
        '-y',                                # 覆盖输出文件
        output_file
    ]
    
    try:
        # 执行转换
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            # 检查输出文件大小
            if os.path.exists(output_file):
                file_size = os.path.getsize(output_file)
                print(f"✅ 转换成功!")
                print(f"   输出文件: {output_file}")
                print(f"   文件大小: {file_size / 1024:.1f} KB")
                
                # 检查文件大小是否适合ESP32
                if file_size > 1024 * 1024:  # 1MB
                    print("⚠️  警告: 文件较大，可能需要降低质量或帧率")
                    print("   建议: 增加quality参数值 (降低质量) 或减少fps")
                
                return True
            else:
                print("❌ 转换失败: 输出文件未生成")
                return False
        else:
            print("❌ FFmpeg转换失败:")
            print(result.stderr)
            return False
            
    except Exception as e:
        print(f"❌ 转换过程出错: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description='将视频转换为ESP32可播放的MJPEG格式')
    parser.add_argument('input', help='输入视频文件路径')
    parser.add_argument('-o', '--output', help='输出MJPEG文件路径 (默认: input.mjp)')
    parser.add_argument('-w', '--width', type=int, default=172, help='目标宽度 (默认: 172)')
    parser.add_argument('-h', '--height', type=int, default=320, help='目标高度 (默认: 320)')
    parser.add_argument('-f', '--fps', type=int, default=15, help='目标帧率 (默认: 15)')
    parser.add_argument('-q', '--quality', type=int, default=5, help='JPEG质量 1-31 (默认: 5)')
    
    args = parser.parse_args()
    
    # 确定输出文件名
    if args.output:
        output_file = args.output
    else:
        base_name = os.path.splitext(args.input)[0]
        output_file = f"{base_name}.mjp"
    
    # 执行转换
    success = convert_to_mjpeg(
        args.input, 
        output_file, 
        args.width, 
        args.height, 
        args.fps, 
        args.quality
    )
    
    if success:
        print("\n🎯 使用方法:")
        print(f"1. 将 {output_file} 复制到ESP32的SPIFFS分区")
        print("2. 在代码中调用:")
        print(f"   sisi_ui_start_idle_video(\"/spiffs/{os.path.basename(output_file)}\");")
        print("\n📝 提示:")
        print("- 如果文件太大，尝试增加 -q 参数 (降低质量)")
        print("- 如果播放卡顿，尝试减少 -f 参数 (降低帧率)")
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == '__main__':
    main()
