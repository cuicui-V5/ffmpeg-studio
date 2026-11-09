import os
import json
import bisect
import subprocess
from core.tool_manager import tool_mgr

def _get_av():
    """按需延迟加载 PyAV，避免应用启动时初始化数十个底层 C-FFmpeg 动态库造成数百毫秒启动阻塞"""
    try:
        import av
        return av
    except Exception:
        return None

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
        """高速获取视频媒体信息 (优先 PyAV 8ms 读取，异常时回退至 ffprobe)"""
        if not os.path.isfile(file_path):
            return {}

        # 1. 优先使用 PyAV 直接解析容器 Header (毫秒级响应)
        av_module = _get_av()
        if av_module:
            try:
                with av_module.open(file_path) as container:
                    stream = container.streams.video[0]
                    dur = float(container.duration / 1000000.0) if container.duration else 0.0
                    if dur <= 0 and stream.duration:
                        dur = float(stream.duration * stream.time_base)
                    
                    r_fps = stream.average_rate
                    fps = float(r_fps) if r_fps and float(r_fps) > 0 else 30.0
                    pix_fmt = getattr(stream, "pix_fmt", "") or ""

                    # 解析音频流属性
                    audio_codec = "none"
                    sample_rate = 0
                    channels = 0
                    if container.streams.audio:
                        astream = container.streams.audio[0]
                        audio_codec = getattr(astream.codec_context, "name", "unknown") if astream.codec_context else "unknown"
                        sample_rate = getattr(astream, "sample_rate", 0) or 0
                        channels = getattr(astream, "channels", 0) or 0

                    return {
                        "file_path": file_path,
                        "duration": dur,
                        "size": os.path.getsize(file_path),
                        "bit_rate": int(container.bit_rate) if container.bit_rate else 0,
                        "width": stream.width,
                        "height": stream.height,
                        "codec": stream.codec_context.name,
                        "pix_fmt": pix_fmt,
                        "fps": round(fps, 2),
                        "audio_codec": audio_codec,
                        "sample_rate": sample_rate,
                        "channels": channels
                    }
            except Exception:
                pass

        # 2. 回退机制：使用 ffprobe (无窗口执行)
        ffprobe = tool_mgr.get_path("ffprobe")
        if not ffprobe:
            return {}

        cmd = [
            ffprobe, "-v", "error",
            "-show_entries", "format=duration,size,bit_rate:stream=width,height,codec_type,codec_name,pix_fmt,r_frame_rate,sample_rate,channels",
            "-of", "json", file_path
        ]
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        try:
            ret = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                errors="ignore",
                timeout=8,
                creationflags=creationflags
            )
            if ret.returncode != 0 or not ret.stdout:
                return {}
            data = json.loads(ret.stdout)
            
            fmt = data.get("format", {})
            duration = float(fmt.get("duration", 0.0))
            size = int(fmt.get("size", 0))
            bit_rate = int(fmt.get("bit_rate", 0)) if fmt.get("bit_rate") else 0
            
            width, height, codec, pix_fmt = 0, 0, "unknown", ""
            fps = 0.0
            audio_codec, sample_rate, channels = "none", 0, 0

            for stream in data.get("streams", []):
                ctype = stream.get("codec_type")
                if ctype == "video" and not width and stream.get("width") and stream.get("height"):
                    width = int(stream["width"])
                    height = int(stream["height"])
                    codec = stream.get("codec_name", "unknown")
                    pix_fmt = stream.get("pix_fmt", "")
                    r_fps = stream.get("r_frame_rate", "")
                    if "/" in r_fps:
                        num, den = r_fps.split("/")
                        if float(den) > 0:
                            fps = float(num) / float(den)
                    elif r_fps:
                        fps = float(r_fps)
                elif ctype == "audio" and audio_codec == "none":
                    audio_codec = stream.get("codec_name", "unknown")
                    sample_rate = int(stream.get("sample_rate", 0))
                    channels = int(stream.get("channels", 0))
                    
            return {
                "file_path": file_path,
                "duration": duration,
                "size": size,
                "bit_rate": bit_rate,
                "width": width,
                "height": height,
                "codec": codec,
                "pix_fmt": pix_fmt,
                "fps": round(fps, 2),
                "audio_codec": audio_codec,
                "sample_rate": sample_rate,
                "channels": channels
            }
        except Exception:
            return {}

    @classmethod
    def find_keyframe_instant(cls, container, stream, target_sec: float, mode: str = "floor") -> tuple[float, float]:
        """
        利用已经打开的视频容器索引，在 1 毫秒内瞬间定位目标时间点邻近的关键帧
        - mode='floor'：吸附至前一个关键帧 (适合裁剪开始时间，确保以 IDR 关键帧启动)
        - mode='ceil'：吸附至后一个关键帧 (适合裁剪结束时间)
        返回 (吸附后秒数, 偏差秒数)
        """
        if target_sec <= 0.02:
            return 0.0, 0.0

        if not container or not stream:
            return target_sec, 0.0

        try:
            pts = int(target_sec / stream.time_base)
            backward = (mode == "floor")
            container.seek(pts, stream=stream, any_frame=False, backward=backward)
            
            for packet in container.demux(stream):
                if packet.is_keyframe and packet.pts is not None:
                    kf_sec = float(packet.pts * stream.time_base)
                    return round(kf_sec, 3), round(kf_sec - target_sec, 3)
        except Exception:
            pass

        return target_sec, 0.0

    @classmethod
    def get_keyframes(cls, file_path: str) -> list[float]:
        """异步/后台使用的全量关键帧读取 (完全静默执行)"""
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

        creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        keyframes = []
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                errors="ignore",
                creationflags=creationflags
            )
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
        if not keyframes or keyframes[0] > 0.05:
            keyframes.insert(0, 0.0)

        cls._cache[file_path] = keyframes
        return keyframes

    @classmethod
    def snap_to_keyframe(cls, target_sec: float, keyframes: list[float], mode: str = "nearest") -> tuple[float, float]:
        """已具备全量索引时的吸附算法"""
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
        else:
            if idx == 0:
                snapped = keyframes[0]
            elif idx >= len(keyframes):
                snapped = keyframes[-1]
            else:
                before = keyframes[idx - 1]
                after = keyframes[idx]
                snapped = before if (target_sec - before) <= (after - target_sec) else after

        return round(snapped, 3), round(snapped - target_sec, 3)
