"""
压缩音频文件到 5MB 以下
"""
from pathlib import Path
from pydub import AudioSegment

input_file = r"E:\liusisi\1月23日.WAV"
output_file = r"E:\liusisi\1月23日_compressed.mp3"

print(f"原始文件: {input_file}")
print(f"原始大小: {Path(input_file).stat().st_size / 1024 / 1024:.2f} MB")

# 加载音频
audio = AudioSegment.from_wav(input_file)

print(f"时长: {len(audio) / 1000:.2f} 秒")
print(f"采样率: {audio.frame_rate} Hz")
print(f"声道数: {audio.channels}")

# 截取前 10 秒（推荐时长）
audio_10s = audio[:10000]

# 导出为 MP3，降低比特率
audio_10s.export(
    output_file,
    format="mp3",
    bitrate="64k",  # 降低比特率
    parameters=["-ar", "32000"]  # 降低采样率到 32kHz
)

print(f"\n✅ 压缩完成！")
print(f"输出文件: {output_file}")
print(f"输出大小: {Path(output_file).stat().st_size / 1024:.2f} KB")
print(f"输出时长: 10 秒")
