import os
import sys
import json
import subprocess
from pathlib import Path
from core.tool_manager import tool_mgr

class HardwareDetector:
    """
    检测显卡硬件加速编解码器支持情况 (NVENC / QSV / AMF)
    极致性能设计：
    1. 优先内存命中与多路径本地磁盘缓存 (0ms 响应)
    2. 无缓存时优先微秒级显卡驱动 DLL 快速探针，绝不在主线程阻塞启动
    3. 全程使用 CREATE_NO_WINDOW，杜绝 Windows 控制台窗口闪烁弹窗
    """
    
    _cached_support = None
    _candidate_dirs = [
        Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent,
        Path.cwd(),
        Path(__file__).resolve().parent.parent
    ]

    @classmethod
    def _find_cache_file(cls) -> Path:
        for d in cls._candidate_dirs:
            p = d / ".hardware_cache.json"
            if p.exists():
                return p
        return cls._candidate_dirs[0] / ".hardware_cache.json"

    @classmethod
    def _fast_probe_driver_dlls(cls) -> dict:
        """微秒级显卡驱动探针：检查系统核心编解码 DLL 是否存在 (耗时 < 0.1ms，零进程开销)"""
        has_nvenc = False
        has_amf = False
        has_qsv = False

        if os.name == 'nt':
            # NVIDIA NVENC 官方核心驱动库
            nv_paths = [
                r"C:\Windows\System32\nvencodeapi64.dll",
                r"C:\Windows\System32\nvencodeapi.dll",
                r"C:\Windows\System32\nvcuda.dll"
            ]
            has_nvenc = any(os.path.exists(p) for p in nv_paths)

            # AMD AMF 驱动库
            amf_paths = [
                r"C:\Windows\System32\amfrt64.dll",
                r"C:\Windows\System32\amfrt32.dll"
            ]
            has_amf = any(os.path.exists(p) for p in amf_paths)

            # Intel QuickSync 驱动库
            qsv_paths = [
                r"C:\Windows\System32\libmfx64.dll",
                r"C:\Windows\System32\mfx64.dll",
                r"C:\Windows\System32\igfx_installer.exe"
            ]
            has_qsv = any(os.path.exists(p) for p in qsv_paths)

        return {
            "hevc_nvenc": {"supported": has_nvenc, "desc": "NVIDIA NVENC H.265"},
            "h264_nvenc": {"supported": has_nvenc, "desc": "NVIDIA NVENC H.264"},
            "hevc_qsv": {"supported": has_qsv, "desc": "Intel QuickSync H.265"},
            "h264_qsv": {"supported": has_qsv, "desc": "Intel QuickSync H.264"},
            "hevc_amf": {"supported": has_amf, "desc": "AMD AMF H.265"},
            "h264_amf": {"supported": has_amf, "desc": "AMD AMF H.264"},
            "libx265": {"supported": True, "desc": "CPU 软件编码 libx265"},
            "libx264": {"supported": True, "desc": "CPU 软件编码 libx264"}
        }

    @classmethod
    def detect_encoders(cls, force_refresh: bool = False, run_real_test: bool = True) -> dict:
        if not force_refresh:
            if cls._cached_support is not None:
                return cls._cached_support

            # 1. 尝试读取本地缓存文件
            cache_file = cls._find_cache_file()
            if cache_file.exists():
                try:
                    with open(cache_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if isinstance(data, dict) and data:
                            cls._cached_support = data
                            return cls._cached_support
                except Exception:
                    pass

            # 2. 若无缓存且不要求强制真实测试，先使用微秒级驱动探针秒返，避免首启阻塞
            if not run_real_test:
                probe_res = cls._fast_probe_driver_dlls()
                cls._cached_support = probe_res
                return probe_res

        ffmpeg = tool_mgr.get_path("ffmpeg")
        if not ffmpeg:
            probe_res = cls._fast_probe_driver_dlls()
            cls._cached_support = probe_res
            return probe_res

        encoders = {
            "hevc_nvenc": "NVIDIA NVENC H.265",
            "h264_nvenc": "NVIDIA NVENC H.264",
            "hevc_qsv": "Intel QuickSync H.265",
            "h264_qsv": "Intel QuickSync H.264",
            "hevc_amf": "AMD AMF H.265",
            "h264_amf": "AMD AMF H.264",
            "libx265": "CPU 软件编码 libx265",
            "libx264": "CPU 软件编码 libx264"
        }

        creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
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
                ret = subprocess.run(
                    test_cmd,
                    capture_output=True,
                    timeout=2,
                    creationflags=creationflags
                )
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

        # 写入所有可写候选目录缓存
        for d in cls._candidate_dirs:
            try:
                if d.exists() and os.access(d, os.W_OK):
                    target_file = d / ".hardware_cache.json"
                    with open(target_file, "w", encoding="utf-8") as f:
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
