import os
import sys
import subprocess
import re
import json
import shutil
from pathlib import Path

# ================= 配置区域 =================
OUTPUT_DIR_NAME = "output_1080p"
CQ_VALUE = 28  # 压制质量 (24-30)
EXTENSIONS = {'.mp4', '.mov', '.mkv', '.avi', '.m4v', '.3gp', '.flv'}

# 全局工具路径变量
TOOL_FFMPEG = ""
TOOL_EXIFTOOL = ""
# ===========================================

class VideoTask:
    def __init__(self, filepath):
        self.filepath = Path(filepath)
        self.filename = self.filepath.name
        self.output_path = self.filepath.parent / OUTPUT_DIR_NAME / f"{self.filepath.stem}_1080p.mp4"
        
        self.date_source = None 
        self.gps_source = None  
        
        self.final_date = None
        self.final_lat = None
        self.final_lon = None

def init_tools():
    global TOOL_FFMPEG, TOOL_EXIFTOOL
    script_dir = Path(sys.path[0])
    
    ffmpeg_name = "ffmpeg.exe" if os.name == 'nt' else "ffmpeg"
    exiftool_name = "exiftool.exe" if os.name == 'nt' else "exiftool"
    
    local_ffmpeg = script_dir / ffmpeg_name
    local_exiftool = script_dir / exiftool_name
    
    TOOL_FFMPEG = str(local_ffmpeg) if local_ffmpeg.exists() else shutil.which("ffmpeg")
    TOOL_EXIFTOOL = str(local_exiftool) if local_exiftool.exists() else shutil.which("exiftool")

    missing = []
    if not TOOL_FFMPEG: missing.append(ffmpeg_name)
    if not TOOL_EXIFTOOL: missing.append(exiftool_name)
    
    if missing:
        print("❌ 严重错误: 找不到以下工具:")
        for m in missing: print(f"   - {m}")
        input("\n按回车键退出...")
        sys.exit(1)
    else:
        print(f"✅ 工具加载成功 (位于: {script_dir})")

def parse_filename_date(filename):
    pattern = r'(20\d{2})[-_]?(\d{2})[-_]?(\d{2}).*?(\d{2})[-_]?(\d{2})[-_]?(\d{2})'
    match = re.search(pattern, filename)
    if match:
        y, m, d, hh, mm, ss = match.groups()
        return f"{y}:{m}:{d} {hh}:{mm}:{ss}"
    return None

def get_media_create_date(filepath):
    try:
        cmd = [
            TOOL_EXIFTOOL, '-api', 'QuickTimeUTC=1', '-j', '-CreateDate', '-MediaCreateDate', '-DateTimeOriginal', str(filepath)
        ]
        # 保留 errors='ignore' 防止中文字符导致 subprocess 崩溃
        result = subprocess.run(cmd, capture_output=True, text=True, errors='ignore')
        
        if result.returncode == 0 and result.stdout:
            data = json.loads(result.stdout)[0]
            for tag in ['DateTimeOriginal', 'CreateDate', 'MediaCreateDate']:
                if tag in data and data[tag]:
                    val = str(data[tag]).strip()
                    match = re.search(r'\d{4}:\d{2}:\d{2} \d{2}:\d{2}:\d{2}', val)
                    if match:
                        return match.group(0)
    except:
        pass
    return None

def parse_gps_input(user_input):
    if not user_input or user_input.strip() == "": return None, None
    url_match = re.search(r'@(-?\d+\.\d+),(-?\d+\.\d+)', user_input)
    if url_match: return float(url_match.group(1)), float(url_match.group(2))
    q_match = re.search(r'q=(-?\d+\.\d+),(-?\d+\.\d+)', user_input)
    if q_match: return float(q_match.group(1)), float(q_match.group(2))
    raw_match = re.search(r'(-?\d+\.\d+)[,\s]+(-?\d+\.\d+)', user_input)
    if raw_match: return float(raw_match.group(1)), float(raw_match.group(2))
    return None, None

def main():
    try:
        init_tools() 
        
        if len(sys.argv) > 1:
            input_path = sys.argv[1]
        else:
            input_path = input("\n📂 请输入文件或文件夹路径 (支持拖入): ").strip('"')
        
        if not os.path.exists(input_path): return

        tasks = []
        if os.path.isfile(input_path):
            if Path(input_path).suffix.lower() in EXTENSIONS: tasks.append(VideoTask(input_path))
        else:
            for root, dirs, files in os.walk(input_path):
                for file in files:
                    if Path(file).suffix.lower() in EXTENSIONS:
                        tasks.append(VideoTask(os.path.join(root, file)))

        if not tasks:
            print("❌ 未找到视频文件。")
            return

        print(f"\n🔍 正在扫描 {len(tasks)} 个视频的信息...")

        for task in tasks:
            try:
                cmd = [
                    TOOL_EXIFTOOL, '-j', '-n', '-GPSLatitude', '-GPSLongitude', str(task.filepath)
                ]
                res = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, text=True, errors='ignore')
                d = json.loads(res)[0]
                if 'GPSLatitude' in d and 'GPSLongitude' in d:
                    task.final_lat = float(d['GPSLatitude'])
                    task.final_lon = float(d['GPSLongitude'])
                    task.gps_source = 'exif'
            except: pass

            date_found = get_media_create_date(task.filepath)
            if date_found:
                task.final_date = date_found
                task.date_source = 'media_info'
            else:
                date_from_name = parse_filename_date(task.filename)
                if date_from_name:
                    task.final_date = date_from_name
                    task.date_source = 'filename'
                else:
                    task.date_source = None

            status_gps = "📍GPS:OK" if task.gps_source else "❌GPS:无"
            status_date = f"📅日期:{task.date_source}" if task.date_source else "❌日期:无"
            print(f"  [{task.filename[:20]}...] {status_date} | {status_gps}")

        missing_gps = [t for t in tasks if not t.gps_source]
        missing_date = [t for t in tasks if not t.date_source]

        if missing_gps:
            print(f"\n======== 📍 需补充 GPS ({len(missing_gps)}个) ========")
            last_lat, last_lon = None, None
            for t in missing_gps:
                prompt = f"文件 {t.filename}"
                if last_lat: prompt += " [按s复用]"
                val = input(f"{prompt}: ").strip()
                
                if val.lower() == 'q':
                    print("⏭️ 已跳过剩余文件的 GPS 输入流程。")
                    break
                if (val == 's' or val == '') and last_lat:
                    t.final_lat, t.final_lon = last_lat, last_lon
                    t.gps_source = 'user_copy'
                    continue
                
                lat, lon = parse_gps_input(val)
                if lat:
                    t.final_lat, t.final_lon = lat, lon
                    t.gps_source = 'user'
                    last_lat, last_lon = lat, lon

        if missing_date:
            print(f"\n======== 📅 需补充日期 ({len(missing_date)}个) ========")
            for t in missing_date:
                val = input(f"{t.filename} 日期 (格式 2025:01:01 12:00:00): ").strip()
                if val:
                    t.final_date = val
                    t.date_source = 'user'

        print(f"\n🚀 开始处理 {len(tasks)} 个任务...")
        
        for i, task in enumerate(tasks):
            print(f"\n[{i+1}/{len(tasks)}] 处理: {task.filename}")
            task.output_path.parent.mkdir(exist_ok=True)
            
            # --- 1. FFmpeg 压制 ---
            scale_filter = "scale='if(gt(a,1),-1,1080)':'if(gt(a,1),1080,-1)'"
            cmd_ffmpeg = [
                TOOL_FFMPEG, '-y', '-hide_banner', '-loglevel', 'error',
                '-hwaccel', 'cuda',
                '-i', str(task.filepath),
                '-vf', scale_filter,
                '-c:v', 'hevc_nvenc', '-preset', 'p5',
                '-rc', 'vbr', '-cq', str(CQ_VALUE), '-b:v', '0',
                '-c:a', 'aac', '-b:a', '128k',
                str(task.output_path)
            ]
            try:
                print("   🔨 视频压制中...")
                subprocess.run(cmd_ffmpeg, check=True)
            except Exception as e:
                print(f"   ❌ 压制失败: {e}")
                continue

            # --- 2. ExifTool 注入元数据 ---
            print("   📝 注入元数据...")
            
            cmd_exif = [
                TOOL_EXIFTOOL, '-overwrite_original',
                '-api', 'QuickTimeUTC=1',
                '-api', 'SystemTags=1',
                '-tagsFromFile', str(task.filepath),
                '-all:all', '-unsafe'
            ]
            
            if task.final_date:
                cmd_exif.extend([
                    f'-AllDates={task.final_date}',
                    f'-CreateDate={task.final_date}',
                    f'-ModifyDate={task.final_date}',
                    f'-TrackCreateDate={task.final_date}',
                    f'-TrackModifyDate={task.final_date}',
                    f'-MediaCreateDate={task.final_date}',
                    f'-MediaModifyDate={task.final_date}'
                ])
                
            if task.final_lat:
                lat_ref = "N" if task.final_lat >= 0 else "S"
                lon_ref = "E" if task.final_lon >= 0 else "W"
                cmd_exif.extend([
                    f'-GPSLatitude={abs(task.final_lat)}', f'-GPSLatitudeRef={lat_ref}',
                    f'-GPSLongitude={abs(task.final_lon)}', f'-GPSLongitudeRef={lon_ref}',
                    f'-Keys:GPSCoordinates={task.final_lat} {task.final_lon}'
                ])
                
            cmd_exif.extend([
                '-FileModifyDate<FileModifyDate',
                '-FileCreateDate<FileCreateDate'
            ])
            
            cmd_exif.append(str(task.output_path))
            
            print(f"   [DEBUG] 注入命令: {' '.join(cmd_exif)}")
            
            result = subprocess.run(cmd_exif, capture_output=True, text=True, errors='ignore')
            
            if result.stdout:
                print(f"   [DEBUG] ExifTool 正常输出:\n{result.stdout.strip()}")
            if result.stderr:
                print(f"   [DEBUG] ExifTool 错误/警告:\n{result.stderr.strip()}")
                
            if result.returncode == 0:
                print("   ✅ 完成")
            else:
                print("   ❌ 元数据注入发生错误，请查看上方 DEBUG 日志")

        print("\n🎉 全部搞定！")
        
    except Exception as e:
        print(f"\n💥 程序崩溃: {e}")
        import traceback
        traceback.print_exc()
    
    input("按回车键退出...")

if __name__ == "__main__":
    main()