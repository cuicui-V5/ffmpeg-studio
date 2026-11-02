import os
import subprocess
import json
import shutil
import math
import argparse
import sys

# ================= 配置区域 (默认阈值) =================
# 限制阈值
MAX_SIZE_BYTES = 1 * 1024 * 1024 * 1024  # 1GB
MAX_DURATION_SEC = 585                   # 10 Minutes
SAFETY_FACTOR = 0.95                     # 预留 5% 空间防止码率波动
# ======================================================

def get_video_info(file_path):
    """使用 ffprobe 获取视频信息"""
    try:
        cmd = [
            'ffprobe', '-v', 'error',
            '-show_entries', 'format=duration,size',
            '-of', 'json', file_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
        data = json.loads(result.stdout)
        return float(data['format']['duration']), int(data['format']['size'])
    except Exception as e:
        print(f"[Error] Reading info for {file_path}: {e}")
        return None, None

def process_videos(input_folder, output_folder):
    # 路径检查
    if not os.path.exists(input_folder):
        print(f"Error: Source path does not exist: {input_folder}")
        sys.exit(1)

    if not os.path.exists(output_folder):
        try:
            os.makedirs(output_folder)
            print(f"Created output folder: {output_folder}")
        except OSError as e:
            print(f"Error creating output folder: {e}")
            sys.exit(1)

    print(f"Source: {input_folder}")
    print(f"Target: {output_folder}")
    print("-" * 50)

    files = [f for f in os.listdir(input_folder) if f.lower().endswith(('.mp4', '.mkv', '.mov', '.avi', '.flv'))]
    
    if not files:
        print("No video files found in source folder.")
        return

    for filename in files:
        input_path = os.path.join(input_folder, filename)
        base_name, ext = os.path.splitext(filename)
        
        print(f"Processing: {filename}...")
        
        duration, size = get_video_info(input_path)
        
        if duration is None:
            continue

        # 规则 1: 小于1G 且 短于10分钟 -> 直接复制
        if size < MAX_SIZE_BYTES and duration < MAX_DURATION_SEC:
            print("  > Condition met: Direct Copy.")
            shutil.copy2(input_path, os.path.join(output_folder, filename))
        
        # 规则 2 & 3: 需要分割
        else:
            print("  > Splitting required.")
            avg_byte_rate = size / duration
            time_limit_by_size = (MAX_SIZE_BYTES / avg_byte_rate) * SAFETY_FACTOR
            
            # 取两者中较小的一个作为分割点
            split_time = min(MAX_DURATION_SEC, time_limit_by_size)
            
            # 微调，避免浮点数误差
            if split_time >= MAX_DURATION_SEC:
                split_time = MAX_DURATION_SEC * 0.99
            
            print(f"  > Segment time: {split_time:.2f}s")

            output_pattern = os.path.join(output_folder, f"{base_name}_part%03d{ext}")
            
            cmd = [
                'ffmpeg', '-y', '-hide_banner', '-loglevel', 'error',
                '-i', input_path,
                '-c', 'copy',
                '-f', 'segment',
                '-segment_time', str(split_time),
                '-reset_timestamps', '1',
                output_pattern
            ]
            subprocess.run(cmd)
            print("  > Done.")
            
        print("-" * 50)

def main():
    parser = argparse.ArgumentParser(description="Batch split videos using FFmpeg based on size and duration.")
    
    # 必选参数：源路径
    parser.add_argument("source", help="Path to the source folder containing videos")
    
    # 可选参数：输出路径 (nargs='?' 表示0个或1个参数)
    parser.add_argument("output", nargs="?", help="Path to the output folder (Optional)")

    args = parser.parse_args()

    input_path = os.path.abspath(args.source)
    
    # 逻辑：如果没提供 output，则默认为 source 下的 'output' 文件夹
    if args.output:
        output_path = os.path.abspath(args.output)
    else:
        output_path = os.path.join(input_path, "output")

    # 检查 ffmpeg
    if shutil.which("ffmpeg") is None:
        print("Error: 'ffmpeg' command not found. Please install FFmpeg.")
        sys.exit(1)

    process_videos(input_path, output_path)

if __name__ == "__main__":
    main()