import subprocess
from core.tool_manager import tool_mgr

class HardwareDetector:
    """检测显卡硬件加速编解码器支持情况"""
    
    _cached_support = None

    @classmethod
    def detect_encoders(cls) -> dict:
        if cls._cached_support is not None:
            return cls._cached_support

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
                # CPU 软解软编一般都支持
                results[enc] = {"supported": True, "desc": desc}
                continue
            
            # 真实运行 1 帧空测试检验当前显卡驱动是否支持该编码器
            test_cmd = [
                ffmpeg, "-y", "-loglevel", "error",
                "-f", "lavfi", "-i", "color=s=256x256:d=0.04",
                "-c:v", enc,
                "-f", "null", "-"
            ]
            try:
                ret = subprocess.run(test_cmd, capture_output=True, timeout=3)
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
