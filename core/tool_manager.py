import os
import sys
import shutil
import subprocess
from pathlib import Path

class ToolManager:
    """管理并定位 FFmpeg, FFprobe, FFplay, ExifTool 二进制工具"""
    
    def __init__(self):
        if getattr(sys, "frozen", False):
            self.app_dir = Path(sys.executable).parent
        else:
            self.app_dir = Path(__file__).resolve().parent.parent

        self.tools = {
            "ffmpeg": self._find_tool("ffmpeg"),
            "ffprobe": self._find_tool("ffprobe"),
            "ffplay": self._find_tool("ffplay"),
            "exiftool": self._find_tool("exiftool")
        }
        self.versions = {}
        # 优化：启动时不阻塞运行外部命令，仅在使用时按需延迟探测
        self._versions_detected = False

    def _find_tool(self, name: str) -> str:
        exe_name = f"{name}.exe" if os.name == 'nt' else name
        
        # 1. 优先检查当前程序工作目录、安装目录及其上级目录
        candidates = [
            self.app_dir / exe_name,
            self.app_dir.parent / exe_name,
            self.app_dir.parent.parent / exe_name,
            Path.cwd() / exe_name
        ]
        for c in candidates:
            if c.exists() and os.access(c, os.X_OK):
                return str(c)
                
        # 2. 检查系统 PATH
        system_path = shutil.which(name)
        if system_path:
            return system_path
            
        return ""

    def _detect_versions(self):
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        for name, path in self.tools.items():
            if not path or not os.path.exists(path):
                self.versions[name] = "未找到"
                continue
            try:
                if name in ["ffmpeg", "ffprobe", "ffplay"]:
                    res = subprocess.run(
                        [path, "-version"],
                        capture_output=True,
                        text=True,
                        errors="ignore",
                        creationflags=creationflags,
                        timeout=2
                    )
                    first_line = res.stdout.splitlines()[0] if res.stdout else ""
                    self.versions[name] = first_line.split("Copyright")[0].strip() if first_line else "已就绪"
                elif name == "exiftool":
                    res = subprocess.run(
                        [path, "-ver"],
                        capture_output=True,
                        text=True,
                        errors="ignore",
                        creationflags=creationflags,
                        timeout=2
                    )
                    self.versions[name] = f"v{res.stdout.strip()}" if res.stdout else "已就绪"
            except Exception:
                self.versions[name] = "已就绪"

    def get_path(self, name: str) -> str:
        return self.tools.get(name, "")

    def is_available(self, name: str) -> bool:
        path = self.get_path(name)
        return bool(path and os.path.exists(path))

    def get_status_dict(self) -> dict:
        if not self._versions_detected:
            self._detect_versions()
            self._versions_detected = True
        return {
            name: {
                "available": self.is_available(name),
                "path": self.get_path(name),
                "version": self.versions.get(name, "已就绪")
            }
            for name in self.tools
        }

# 全局单例
tool_mgr = ToolManager()
