import os
import subprocess
import av
from pathlib import Path
from PySide6.QtCore import QThread, Signal
from core.tool_manager import tool_mgr
from core.keyframe_helper import KeyframeHelper

class CutterWorker(QThread):
    """
    极速视频裁切线程
    支持关键帧智能吸附对齐（杜绝黑屏/花屏，无需慢速重编码）
    """
    finished = Signal(bool, str, str)  # (success, message, output_path)
    log_emitted = Signal(str)

    def __init__(
        self,
        file_path: str,
        start_sec: float,
        end_sec: float,
        auto_snap: bool = True,
        output_dir: str = ""
    ):
        super().__init__()
        self.file_path = Path(file_path).resolve()
        self.raw_start = max(0.0, start_sec)
        self.raw_end = end_sec
        self.auto_snap = auto_snap
        self.output_dir = Path(output_dir) if output_dir else self.file_path.parent / "output_cut"
        
        self.snapped_start = self.raw_start
        self.snapped_end = self.raw_end
        self.output_path = None
        self._proc = None

    def cancel(self):
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.terminate()
                self._proc.kill()
            except Exception:
                pass

    def run(self):
        tool_ffmpeg = tool_mgr.get_path("ffmpeg")
        if not tool_ffmpeg:
            self.finished.emit(False, "未找到 ffmpeg 可执行文件", "")
            return

        # 1. 关键帧毫秒级瞬间吸附对齐 (基于索引定位，耗时 < 2ms)
        if self.auto_snap:
            self.log_emitted.emit("⚡ 正在执行关键帧智能对齐 (杜绝黑屏)...")
            try:
                with av.open(str(self.file_path)) as container:
                    stream = container.streams.video[0]
                    s_snap, s_diff = KeyframeHelper.find_keyframe_instant(container, stream, self.raw_start, mode="floor")
                    e_snap, e_diff = KeyframeHelper.find_keyframe_instant(container, stream, self.raw_end, mode="ceil")
                    self.snapped_start = s_snap
                    self.snapped_end = e_snap
                    self.log_emitted.emit(
                        f"⚡ 关键帧对齐完成（杜绝黑屏）:\n"
                        f"   起点: {KeyframeHelper.format_time(self.raw_start)} -> {KeyframeHelper.format_time(self.snapped_start)} (偏移 {s_diff:+.2f}s)\n"
                        f"   终点: {KeyframeHelper.format_time(self.raw_end)} -> {KeyframeHelper.format_time(self.snapped_end)} (偏移 {e_diff:+.2f}s)"
                    )
            except Exception as e:
                self.log_emitted.emit(f"⚠️ 快速关键帧对齐异常，按原时间截取: {e}")

        # 2. 校验时间
        if self.snapped_end <= self.snapped_start:
            self.finished.emit(False, "裁剪结束时间必须大于起始时间！", "")
            return

        # 3. 准备输出路径
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.output_path = self.output_dir / f"{self.file_path.stem}_cut{self.file_path.suffix}"

        # 4. 构建 FFmpeg 命令进行极速无损流复制
        cmd = [
            tool_ffmpeg, '-y', '-hide_banner',
            '-ss', str(self.snapped_start),
            '-to', str(self.snapped_end),
            '-i', str(self.file_path),
            '-c', 'copy',
            str(self.output_path)
        ]

        self.log_emitted.emit(f"🚀 开始极速裁切 (流复制模式)...")
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        try:
            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                errors='ignore',
                creationflags=creationflags
            )
            out, _ = self._proc.communicate()
            if self._proc.returncode == 0:
                self.log_emitted.emit(f"✅ 裁切成功！输出文件:\n{self.output_path}")
                self.finished.emit(True, "视频裁切成功！", str(self.output_path))
            else:
                self.log_emitted.emit(f"❌ FFmpeg 裁切失败:\n{out}")
                self.finished.emit(False, f"裁切失败 (代码: {self._proc.returncode})", "")
        except Exception as e:
            self.finished.emit(False, f"异常: {e}", "")
