import os
import json
import bisect
import subprocess
from core.tool_manager import tool_mgr

class KeyframeHelper:
    """提取视频关键帧并执行高精度的关键帧吸附对齐算法（杜绝剪辑黑屏/花屏）"""

    _cache = {}

    @staticmethod
    def parse_time(time_str: str) -> float | None:
        """解析时间输入，支持纯秒数、mm:ss、hh:mm:ss 或带小数点格式"""
        if not time_str or not time_str.strip():
            return None
        time_str = time_str.strip()
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

    @staticmethod
    def format_time(seconds: float, show_ms: bool = True) -> str:
        """秒数转为时间码 00:00:00.00"""
        if seconds < 0:
            seconds = 0
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = seconds % 60
        if show_ms:
            return f"{h:02d}:{m:02d}:{s:05.2f}"
        return f"{h:02d}:{m:02d}:{int(s):02d}"

    @classmethod
    def get_video_info(cls, file_path: str) -> dict:
        """获取视频完整媒体信息"""
        ffprobe = tool_mgr.get_path("ffprobe")
        if not ffprobe or not os.path.isfile(file_path):
            return {}

        cmd = [
            ffprobe, "-v", "error",
            "-show_entries", "format=duration,size,bit_rate:stream=width,height,codec_name,r_frame_rate,duration",
            "-of", "json", file_path
        ]
        try:
            ret = subprocess.run(cmd, capture_output=True, text=True, errors="ignore", timeout=10)
            if ret.returncode != 0 or not ret.stdout:
                return {}
            data = json.loads(ret.stdout)
            
            fmt = data.get("format", {})
            duration = float(fmt.get("duration", 0.0))
            size = int(fmt.get("size", 0))
            bit_rate = int(fmt.get("bit_rate", 0)) if fmt.get("bit_rate") else 0
            
            width, height, codec = 0, 0, "unknown"
            fps = 0.0
            for stream in data.get("streams", []):
                if stream.get("width") and stream.get("height"):
                    width = int(stream["width"])
                    height = int(stream["height"])
                    codec = stream.get("codec_name", "unknown")
                    # 解析帧率
                    r_fps = stream.get("r_frame_rate", "")
                    if "/" in r_fps:
                        num, den = r_fps.split("/")
                        if float(den) > 0:
                            fps = float(num) / float(den)
                    elif r_fps:
                        fps = float(r_fps)
                    break
                    
            return {
                "file_path": file_path,
                "duration": duration,
                "size": size,
                "bit_rate": bit_rate,
                "width": width,
                "height": height,
                "codec": codec,
                "fps": round(fps, 2)
            }
        except Exception:
            return {}

    @classmethod
    def get_keyframes(cls, file_path: str) -> list[float]:
        """高速读取视频的所有关键帧时间戳（基于 packet 标志解析，无解码开销）"""
        if file_path in cls._cache:
            return cls._cache[file_path]

        ffprobe = tool_mgr.get_path("ffprobe")
        if not ffprobe or not os.path.isfile(file_path):
            return []

        cmd = [
            ffprobe, "-v", "error",
            "-select_streams", "v:0",
            "-show_packets",
            "-show_entries", "packet=pts_time,flags",
            "-of", "csv=p=0",
            file_path
        ]

        keyframes = []
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, errors="ignore")
            for line in proc.stdout:
                parts = line.strip().split(',')
                if len(parts) >= 2 and 'K' in parts[1]:
                    try:
                        keyframes.append(float(parts[0]))
                    except ValueError:
                        pass
            proc.wait()
        except Exception:
            pass

        keyframes = sorted(list(set(keyframes)))
        # 保证起始至少有 0.0
        if not keyframes or keyframes[0] > 0.05:
            keyframes.insert(0, 0.0)

        cls._cache[file_path] = keyframes
        return keyframes

    @classmethod
    def snap_to_keyframe(cls, target_sec: float, keyframes: list[float], mode: str = "nearest") -> tuple[float, float]:
        """
        将目标时间戳吸附到最合适的关键帧：
        - mode='floor'：吸附到前一个关键帧 (适合裁剪开始时间，确保内容不丢失且以IDR帧开始)
        - mode='ceil'：吸附到后一个关键帧 (适合裁剪结束时间)
        - mode='nearest'：吸附到绝对距离最近的关键帧
        返回 (吸附后的秒数, 偏移秒数)
        """
        if not keyframes:
            return target_sec, 0.0

        idx = bisect.bisect_left(keyframes, target_sec)
        
        if mode == "floor":
            if idx == 0:
                snapped = keyframes[0]
            elif idx < len(keyframes) and abs(keyframes[idx] - target_sec) < 0.02:
                snapped = keyframes[idx]
            else:
                snapped = keyframes[idx - 1]
        elif mode == "ceil":
            if idx >= len(keyframes):
                snapped = keyframes[-1]
            else:
                snapped = keyframes[idx]
        else: # nearest
            if idx == 0:
                snapped = keyframes[0]
            elif idx >= len(keyframes):
                snapped = keyframes[-1]
            else:
                before = keyframes[idx - 1]
                after = keyframes[idx]
                snapped = before if (target_sec - before) <= (after - target_sec) else after

        return round(snapped, 3), round(snapped - target_sec, 3)
