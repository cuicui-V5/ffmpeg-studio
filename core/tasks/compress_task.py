import os
import re
import json
import subprocess
from pathlib import Path
from PySide6.QtCore import QThread, Signal
from core.tool_manager import tool_mgr
from core.hardware import HardwareDetector
from core.keyframe_helper import KeyframeHelper

EXTENSIONS = {'.mp4', '.mov', '.mkv', '.avi', '.m4v', '.3gp', '.flv', '.ts', '.webm'}

def parse_filename_date(filename: str) -> str | None:
    pattern = r'(20\d{2})[-_]?(\d{2})[-_]?(\d{2}).*?(\d{2})[-_]?(\d{2})[-_]?(\d{2})'
    match = re.search(pattern, filename)
    if match:
        y, m, d, hh, mm, ss = match.groups()
        return f"{y}:{m}:{d} {hh}:{mm}:{ss}"
    return None

def parse_gps_input(user_input: str) -> tuple[float | None, float | None]:
    if not user_input or not user_input.strip():
        return None, None
    url_match = re.search(r'@(-?\d+\.\d+),(-?\d+\.\d+)', user_input)
    if url_match:
        return float(url_match.group(1)), float(url_match.group(2))
    q_match = re.search(r'q=(-?\d+\.\d+),(-?\d+\.\d+)', user_input)
    if q_match:
        return float(q_match.group(1)), float(q_match.group(2))
    raw_match = re.search(r'(-?\d+\.\d+)[,\s]+(-?\d+\.\d+)', user_input)
    if raw_match:
        return float(raw_match.group(1)), float(raw_match.group(2))
    return None, None

class CompressItem:
    """批量压制队列项"""
    def __init__(self, filepath: str):
        self.filepath = Path(filepath).resolve()
        self.filename = self.filepath.name
        self.filesize = self.filepath.stat().st_size if self.filepath.exists() else 0
        self.duration = 0.0
        self.resolution = ""
        
        # 默认同级 output_1080p 子文件夹
        self.output_dir = self.filepath.parent / "output_1080p"
        self.output_path = self.output_dir / f"{self.filepath.stem}_1080p.mp4"
        
        self.date_source = None   # 'exif', 'filename', 'user', None
        self.gps_source = None    # 'exif', 'user', 'user_copy', None
        
        self.final_date = None
        self.final_lat = None
        self.final_lon = None
        
        self.status = "待处理"    # '待处理', '压制中', '写入元数据', '已完成', '失败', '已跳过'
        self.error_msg = ""
        self.progress = 0.0

    def probe_media_info(self):
        info = KeyframeHelper.get_video_info(str(self.filepath))
        self.duration = info.get("duration", 0.0)
        w = info.get("width", 0)
        h = info.get("height", 0)
        self.resolution = f"{w}x{h}" if w and h else "未知"

    def probe_metadata(self):
        tool_exif = tool_mgr.get_path("exiftool")
        if not tool_exif or not self.filepath.exists():
            return

        # 1. 探测 GPS
        try:
            cmd = [tool_exif, '-j', '-n', '-GPSLatitude', '-GPSLongitude', str(self.filepath)]
            res = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, text=True, errors='ignore')
            data = json.loads(res)[0]
            if 'GPSLatitude' in data and 'GPSLongitude' in data:
                self.final_lat = float(data['GPSLatitude'])
                self.final_lon = float(data['GPSLongitude'])
                self.gps_source = 'exif'
        except Exception:
            pass

        # 2. 探测 日期
        try:
            cmd = [
                tool_exif, '-api', 'QuickTimeUTC=1', '-j',
                '-CreateDate', '-MediaCreateDate', '-DateTimeOriginal', str(self.filepath)
            ]
            res = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, text=True, errors='ignore')
            data = json.loads(res)[0]
            for tag in ['DateTimeOriginal', 'CreateDate', 'MediaCreateDate']:
                if tag in data and data[tag]:
                    val = str(data[tag]).strip()
                    m = re.search(r'\d{4}:\d{2}:\d{2} \d{2}:\d{2}:\d{2}', val)
                    if m:
                        self.final_date = m.group(0)
                        self.date_source = 'exif'
                        break
        except Exception:
            pass

        # 3. 文件名正则兜底提取日期
        if not self.final_date:
            from_name = parse_filename_date(self.filename)
            if from_name:
                self.final_date = from_name
                self.date_source = 'filename'

class BatchCompressWorker(QThread):
    """批量压制执行后台线程"""
    item_updated = Signal(int, str, float)   # (index, status, progress)
    overall_progress = Signal(int, int)      # (finished_count, total_count)
    log_emitted = Signal(str)
    all_finished = Signal()

    def __init__(self, items: list[CompressItem], encoder: str = "auto", cq: int = 28):
        super().__init__()
        self.items = items
        self.encoder = encoder
        self.cq = cq
        self._is_cancelled = False
        self._current_proc = None

    def cancel(self):
        self._is_cancelled = True
        if self._current_proc and self._current_proc.poll() is None:
            try:
                self._current_proc.terminate()
                self._current_proc.kill()
            except Exception:
                pass

    def run(self):
        tool_ffmpeg = tool_mgr.get_path("ffmpeg")
        tool_exif = tool_mgr.get_path("exiftool")

        # 自动选择最合适的 HEVC 编码器
        chosen_encoder = self.encoder
        if chosen_encoder == "auto":
            chosen_encoder = HardwareDetector.get_best_hevc_encoder()

        total = len(self.items)
        finished_count = 0
        self.overall_progress.emit(0, total)

        for idx, item in enumerate(self.items):
            if self._is_cancelled:
                item.status = "已取消"
                self.item_updated.emit(idx, item.status, item.progress)
                break

            item.status = "压制中"
            item.progress = 0.0
            self.item_updated.emit(idx, item.status, 0.0)
            self.log_emitted.emit(f"\n============================\n[{idx+1}/{total}] 开始压制: {item.filename}")

            item.output_dir.mkdir(parents=True, exist_ok=True)

            # 1. 构建 FFmpeg 压制命令
            # 保证偶数分辨率：-2 代替原来的 -1，杜绝奇数宽高报错
            scale_filter = "scale='if(gt(a,1),-2,1080)':'if(gt(a,1),1080,-2)'"
            
            cmd_ffmpeg = [tool_ffmpeg, '-y', '-hide_banner']

            # 硬件加速参数
            if chosen_encoder == "hevc_nvenc":
                cmd_ffmpeg.extend(['-hwaccel', 'cuda', '-i', str(item.filepath)])
                cmd_ffmpeg.extend(['-vf', scale_filter, '-c:v', 'hevc_nvenc', '-preset', 'p5', '-rc', 'vbr', '-cq', str(self.cq), '-b:v', '0'])
            elif chosen_encoder == "h264_nvenc":
                cmd_ffmpeg.extend(['-hwaccel', 'cuda', '-i', str(item.filepath)])
                cmd_ffmpeg.extend(['-vf', scale_filter, '-c:v', 'h264_nvenc', '-preset', 'p5', '-rc', 'vbr', '-cq', str(self.cq), '-b:v', '0'])
            elif chosen_encoder == "hevc_qsv":
                cmd_ffmpeg.extend(['-hwaccel', 'qsv', '-i', str(item.filepath)])
                cmd_ffmpeg.extend(['-vf', scale_filter, '-c:v', 'hevc_qsv', '-global_quality', str(self.cq)])
            elif chosen_encoder == "libx265":
                cmd_ffmpeg.extend(['-i', str(item.filepath)])
                cmd_ffmpeg.extend(['-vf', scale_filter, '-c:v', 'libx265', '-crf', str(self.cq), '-preset', 'medium'])
            else: # libx264
                cmd_ffmpeg.extend(['-i', str(item.filepath)])
                cmd_ffmpeg.extend(['-vf', scale_filter, '-c:v', 'libx264', '-crf', str(self.cq), '-preset', 'medium'])

            cmd_ffmpeg.extend(['-c:a', 'aac', '-b:a', '128k', str(item.output_path)])

            # 异步执行并解析进度
            out_time_pattern = re.compile(r'time=(\d{2}):(\d{2}):(\d{2}\.\d+)')
            try:
                self._current_proc = subprocess.Popen(
                    cmd_ffmpeg,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    errors='ignore',
                    bufsize=1
                )

                for line in self._current_proc.stdout:
                    if self._is_cancelled:
                        break
                    line_str = line.strip()
                    m = out_time_pattern.search(line_str)
                    if m and item.duration > 0:
                        h, mn, s = float(m.group(1)), float(m.group(2)), float(m.group(3))
                        cur_sec = h * 3600 + mn * 60 + s
                        pct = min(99.0, max(0.0, (cur_sec / item.duration) * 100))
                        item.progress = pct
                        self.item_updated.emit(idx, item.status, pct)

                self._current_proc.wait()

                if self._is_cancelled:
                    if item.output_path.exists():
                        item.output_path.unlink()
                    item.status = "已取消"
                    self.item_updated.emit(idx, item.status, 0.0)
                    break

                if self._current_proc.returncode != 0:
                    item.status = "失败"
                    item.error_msg = f"FFmpeg 编码失败 (退出码: {self._current_proc.returncode})"
                    self.item_updated.emit(idx, item.status, item.progress)
                    self.log_emitted.emit(f"❌ 压制失败: {item.error_msg}")
                    continue

            except Exception as e:
                item.status = "失败"
                item.error_msg = str(e)
                self.item_updated.emit(idx, item.status, item.progress)
                self.log_emitted.emit(f"❌ 压制发生异常: {e}")
                continue

            # 2. 调用 ExifTool 回写与补全元数据
            item.status = "写入元数据"
            self.item_updated.emit(idx, item.status, 99.0)
            self.log_emitted.emit(f"📝 注入拍摄时间与 GPS 元数据...")

            if tool_exif and os.path.exists(tool_exif):
                cmd_exif = [
                    tool_exif, '-overwrite_original',
                    '-api', 'QuickTimeUTC=1',
                    '-api', 'SystemTags=1',
                    '-tagsFromFile', str(item.filepath),
                    '-all:all', '-unsafe'
                ]
                
                if item.final_date:
                    cmd_exif.extend([
                        f'-AllDates={item.final_date}',
                        f'-CreateDate={item.final_date}',
                        f'-ModifyDate={item.final_date}',
                        f'-TrackCreateDate={item.final_date}',
                        f'-TrackModifyDate={item.final_date}',
                        f'-MediaCreateDate={item.final_date}',
                        f'-MediaModifyDate={item.final_date}'
                    ])
                    
                if item.final_lat is not None and item.final_lon is not None:
                    lat_ref = "N" if item.final_lat >= 0 else "S"
                    lon_ref = "E" if item.final_lon >= 0 else "W"
                    cmd_exif.extend([
                        f'-GPSLatitude={abs(item.final_lat)}', f'-GPSLatitudeRef={lat_ref}',
                        f'-GPSLongitude={abs(item.final_lon)}', f'-GPSLongitudeRef={lon_ref}',
                        f'-Keys:GPSCoordinates={item.final_lat} {item.final_lon}'
                    ])
                    
                cmd_exif.extend([
                    '-FileModifyDate<FileModifyDate',
                    '-FileCreateDate<FileCreateDate',
                    str(item.output_path)
                ])

                ret = subprocess.run(cmd_exif, capture_output=True, text=True, errors='ignore')
                if ret.returncode != 0:
                    self.log_emitted.emit(f"⚠️ ExifTool 提示: {ret.stderr.strip() or ret.stdout.strip()}")

            item.status = "已完成"
            item.progress = 100.0
            finished_count += 1
            self.item_updated.emit(idx, item.status, 100.0)
            self.overall_progress.emit(finished_count, total)
            self.log_emitted.emit(f"✅ 处理成功: {item.output_path.name}")

        self.all_finished.emit()
