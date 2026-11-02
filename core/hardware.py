import os
import sys
import json
import subprocess
from pathlib import Path
from core.tool_manager import tool_mgr

class HardwareDetector:
    """检测显卡硬件加速编解码器支持情况 (支持本地磁盘缓存以实现极速秒启)"""
    
    _cached_support = None
    _app_dir = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent
    _cache_file = _app_dir / ".hardware_cache.json"

    @classmethod
    def detect_encoders(cls, force_refresh: bool = False) -> dict:
        if not force_refresh:
            if cls._cached_support is not None:
                return cls._cached_support

            # 读取本地缓存
            if cls._cache_file.exists():
                try:
                    with open(cls._cache_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if isinstance(data, dict) and data:
                            cls._cached_support = data
                            return cls._cached_support
                except Exception:
                    pass

        ffmpeg = tool_mgr.get_path("ffmpeg")
        if not ffmpeg:
            return {"cpu": True}

        encoders = {
            "hevc_nvenc": "NVIDIA NVENC (HEVC / H.265)",
            "h264_nvenc": "NVIDIA NVENC (AVC / H.264)",
            "hevc_qsv": "Intel QuickSync (HEVC / H.265)",
            "h264_qsv": "Intel QuickSync (AVC / H.264)",
            "hevc_amf": "AMD AMF (HEVC / H.265)",
            "h264_amf": "AMD AMF (AVC / H.264)",
            "libx265": "CPU 软件编码 (libx265)",
            "libx264": "CPU 软件编码 (libx264)"
        }

        results = {}
        for enc, desc in encoders.items():
            if enc.startswith("libx"):
                results[enc] = {"supported": True, "desc": desc}
                continue
            
            test_cmd = [
                ffmpeg, "-y", "-loglevel", "error",
                "-f", "lavfi", "-i", "color=s=256x256:d=0.04",
                "-c:v", enc,
                "-f", "null", "-"
            ]
            try:
                ret = subprocess.run(test_cmd, capture_output=True, timeout=2)
                results[enc] = {
                    "supported": ret.returncode == 0,
                    "desc": desc
                }
            except Exception:
                results[enc] = {
                    "supported": False,
                    "desc": desc
                }

        cls._cached_support = results
        # 写入缓存
        try:
            with open(cls._cache_file, "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

        return results

    @classmethod
    def get_best_hevc_encoder(cls) -> str:
        res = cls.detect_encoders()
        if res.get("hevc_nvenc", {}).get("supported"):
            return "hevc_nvenc"
        if res.get("hevc_qsv", {}).get("supported"):
            return "hevc_qsv"
        if res.get("hevc_amf", {}).get("supported"):
            return "hevc_amf"
        return "libx265"
