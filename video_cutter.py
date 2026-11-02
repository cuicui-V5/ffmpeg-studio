import sys
import os
import subprocess

def get_video_duration(file_path):
    """调用 ffprobe 获取视频时长（秒）"""
    command = [
        "ffprobe", 
        "-v", "error", 
        "-show_entries", "format=duration", 
        "-of", "default=noprint_wrappers=1:nokey=1", 
        file_path
    ]
    try:
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        return float(result.stdout.strip())
    except (subprocess.CalledProcessError, ValueError):
        return None

def parse_time(time_str):
    """解析时间字符串，返回秒数 (float)。支持格式: ss, mm:ss, hh:mm:ss"""
    try:
        return float(time_str)
    except ValueError:
        pass
    
    parts = time_str.split(':')
    try:
        if len(parts) == 3:
            return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
        elif len(parts) == 2:
            return float(parts[0]) * 60 + float(parts[1])
    except ValueError:
        pass
    
    return None

def format_time(seconds):
    """将秒数格式化为 HH:MM:SS.ms"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:05.2f}"

def main():
    if len(sys.argv) < 2:
        print("请将视频文件拖拽到此脚本图标上运行。")
        input("按回车键退出...")
        return

    input_file = sys.argv[1]

    if not os.path.isfile(input_file):
        print(f"错误：找不到文件 '{input_file}'")
        input("按回车键退出...")
        return

    print(f"已加载文件: {input_file}")
    print("-" * 40)

    # 获取总时长
    duration = get_video_duration(input_file)
    if duration is None:
        print("错误：无法读取视频时长。请确保文件合法且 FFmpeg/FFprobe 已正确安装。")
        input("按回车键退出...")
        return

    print(f"视频总时长: {format_time(duration)} ({duration:.2f} 秒)")
    print("-" * 40)

    # 获取并校验开始时间
    while True:
        start_input = input("请输入开始时间 (直接回车默认为 00:00:00): ").strip()
        if not start_input:
            start_sec = 0.0
            break
        
        start_sec = parse_time(start_input)
        if start_sec is not None and 0 <= start_sec < duration:
            break
        print(f"[!] 无效输入或超出范围，请输入 0 到 {duration:.2f} 之间的有效时间。\n")

    # 获取并校验结束时间
    while True:
        end_input = input("请输入结束时间 (直接回车默认为视频最后): ").strip()
        if not end_input:
            end_sec = duration
            break
        
        end_sec = parse_time(end_input)
        if end_sec is not None and start_sec < end_sec <= duration:
            break
        print(f"[!] 无效输入或逻辑错误，结束时间必须大于开始时间 ({start_sec:.2f}) 且小于等于总时长 ({duration:.2f})。\n")

    # 生成输出路径
    file_dir = os.path.dirname(input_file)
    file_name, file_ext = os.path.splitext(os.path.basename(input_file))
    output_file = os.path.join(file_dir, f"{file_name}_cut{file_ext}")

    # 构建 FFmpeg 命令，统一转换为秒数传递
    command = [
        "ffmpeg",
        "-ss", str(start_sec),
        "-to", str(end_sec),
        "-i", input_file,
        "-c", "copy",
        "-y",
        output_file
    ]

    print(f"\n正在截取片段: {format_time(start_sec)} -> {format_time(end_sec)}")
    print("处理中，请稍候...")
    
    try:
        subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
        print("=" * 40)
        print("处理完成！")
        print(f"输出文件: {output_file}")
    except subprocess.CalledProcessError:
        print("\n[!] FFmpeg 执行出错，请检查原视频流是否存在异常。")

    print("=" * 40)
    input("按回车键退出...")

if __name__ == "__main__":
    main()