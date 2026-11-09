import os
import re
import uuid
import subprocess
from pathlib import Path
from dataclasses import dataclass, field
from PySide6.QtCore import QThread, Signal

from core.tool_manager import tool_mgr

EXTENSIONS = {'.mp4', '.mov', '.mkv', '.avi', '.flv', '.m4v', '.ts', '.webm'}

@dataclass
class MergeItem:
    filepath: Path
    filename: str
    duration: float = 0.0
    size: int = 0
    width: int = 0
    height: int = 0
    codec: str = "unknown"
    pix_fmt: str = ""
    fps: float = 0.0
    audio_codec: str = "none"
    sample_rate: int = 0
    channels: int = 0
    is_valid: bool = True
    error_msg: str = ""
    is_consistent: bool = True
    mismatched_reasons: list[str] = field(default_factory=list)

def validate_merge_consistency(items: list[MergeItem]) -> tuple[bool, str, list[str]]:
    """
    校验待合并视频的编码、分辨率、像素格式、帧率及音频参数是否完全一致。
    返回: (all_consistent: bool, summary_status: str, detailed_warnings: list[str])
    """
    if not items:
        return False, "请添加视频文件进行无损合并", []
    if len(items) == 1:
        return False, "请至少添加 2 个视频文件进行无损合并", ["当前仅有 1 个视频文件，无需合并"]

    ref = items[0]
    all_consistent = True
    warnings = []

    # 第一项作为基准
    ref.is_consistent = True
    ref.mismatched_reasons = []

    for idx in range(1, len(items)):
        item = items[idx]
        item.mismatched_reasons = []

        # 1. 视频编码校验
        if item.codec != ref.codec:
            msg = f"编码不一致: {item.codec}，基准: {ref.codec}"
            item.mismatched_reasons.append(msg)
            warnings.append(f"第 {idx+1} 个文件 {item.filename}: {msg}")

        # 2. 分辨率校验 (流复制最敏感核心参数)
        if item.width != ref.width or item.height != ref.height:
            msg = f"分辨率不一致: {item.width}x{item.height}，基准: {ref.width}x{ref.height}"
            item.mismatched_reasons.append(msg)
            warnings.append(f"第 {idx+1} 个文件 {item.filename}: {msg}")

        # 3. 像素格式校验
        if item.pix_fmt and ref.pix_fmt and item.pix_fmt != ref.pix_fmt:
            msg = f"像素格式不一致: {item.pix_fmt}，基准: {ref.pix_fmt}"
            item.mismatched_reasons.append(msg)
            warnings.append(f"第 {idx+1} 个文件 {item.filename}: {msg}")

        # 4. 帧率校验
        if abs(item.fps - ref.fps) >= 0.5:
            msg = f"帧率差异较大: {item.fps:.1f} fps，基准: {ref.fps:.1f} fps"
            item.mismatched_reasons.append(msg)
            warnings.append(f"第 {idx+1} 个文件 {item.filename}: {msg}")

        # 5. 音频流校验
        if item.audio_codec != ref.audio_codec:
            msg = f"音频编码不一致: {item.audio_codec}，基准: {ref.audio_codec}"
            item.mismatched_reasons.append(msg)
            warnings.append(f"第 {idx+1} 个文件 {item.filename}: {msg}")
        elif item.audio_codec != "none":
            if item.sample_rate != ref.sample_rate:
                msg = f"音频采样率不一致: {item.sample_rate}Hz，基准: {ref.sample_rate}Hz"
                item.mismatched_reasons.append(msg)
                warnings.append(f"第 {idx+1} 个文件 {item.filename}: {msg}")
            if item.channels != ref.channels:
                msg = f"音频声道数不一致: {item.channels}声道，基准: {ref.channels}声道"
                item.mismatched_reasons.append(msg)
                warnings.append(f"第 {idx+1} 个文件 {item.filename}: {msg}")

        if item.mismatched_reasons:
            item.is_consistent = False
            all_consistent = False
        else:
            item.is_consistent = True

    if all_consistent:
        summary = (
            f"参数一致：所有 {len(items)} 个视频的编码、分辨率、帧率及音频参数完全匹配，"
            f"支持无损合并。"
        )
    else:
        summary = f"参数差异：检测到 {len(warnings)} 项参数不一致，无损合并可能导致画面异常或音画不同步。"

    return all_consistent, summary, warnings

class MergeWorker(QThread):
    """后台无损合并执行线程 (基于 FFmpeg Concat Demuxer)"""
    progress_changed = Signal(float, str, str)  # (percent: 0-100, speed, eta_str)
    log_emitted = Signal(str)
    finished = Signal(bool, str, str)           # (success, message, output_path)

    def __init__(self, file_paths: list[Path], output_path: Path, total_duration: float, parent=None):
        super().__init__(parent)
        self.file_paths = file_paths
        self.output_path = output_path
        self.total_duration = total_duration
        self._proc = None
        self._is_cancelled = False
        self._list_file = None

    def cancel(self):
        self._is_cancelled = True
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.terminate()
                self._proc.kill()
            except Exception:
                pass
        self._cleanup_temp_file()
        if self.output_path and self.output_path.exists():
            try:
                self.output_path.unlink()
            except Exception:
                pass

    def _cleanup_temp_file(self):
        if self._list_file and os.path.exists(self._list_file):
            try:
                os.remove(self._list_file)
            except Exception:
                pass
            self._list_file = None

    def run(self):
        self._is_cancelled = False
        tool_ffmpeg = tool_mgr.get_path("ffmpeg")
        if not tool_ffmpeg:
            self.finished.emit(False, "未找到 ffmpeg 可执行文件，无法合并", "")
            return

        if len(self.file_paths) < 2:
            self.finished.emit(False, "待合并的视频数量少于 2 个", "")
            return

        out_folder = self.output_path.parent
        out_folder.mkdir(parents=True, exist_ok=True)

        # 1. 生成标准的 FFmpeg Concat 列表文件
        self._list_file = out_folder / f"concat_list_{uuid.uuid4().hex[:8]}.txt"
        try:
            with open(self._list_file, "w", encoding="utf-8") as f:
                for p in self.file_paths:
                    # 将路径转为正斜杠并对单引号转义
                    clean_str = str(p.resolve()).replace('\\', '/').replace("'", "'\\''")
                    f.write(f"file '{clean_str}'\n")
        except Exception as e:
            self.finished.emit(False, f"创建合并列表文件失败: {e}", "")
            return

        # 2. 构建 FFmpeg 极速流复制无损合并命令
        cmd = [
            tool_ffmpeg, '-y', '-hide_banner',
            '-f', 'concat', '-safe', '0',
            '-i', str(self._list_file),
            '-c', 'copy',
            str(self.output_path)
        ]

        self.log_emitted.emit(f"开始无损合并: {len(self.file_paths)} 个视频片段")
        self.log_emitted.emit(f"[EXEC] {' '.join(cmd)}\n")

        creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        try:
            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                errors='ignore',
                bufsize=1,
                creationflags=creationflags
            )

            out_time_pattern = re.compile(r'time=(\d{2}):(\d{2}):(\d{2}\.\d+)')
            speed_pattern = re.compile(r'speed=\s*([\d\.]+)x')

            for line in self._proc.stdout:
                if self._is_cancelled:
                    break

                line_str = line.strip()
                if line_str:
                    self.log_emitted.emit(line_str)

                time_m = out_time_pattern.search(line_str)
                spd_m = speed_pattern.search(line_str)

                cur_speed = f"{spd_m.group(1)}x" if spd_m else "--"

                if time_m and self.total_duration > 0:
                    h, m, s = float(time_m.group(1)), float(time_m.group(2)), float(time_m.group(3))
                    cur_sec = h * 3600 + m * 60 + s
                    percent = min(99.0, max(0.0, (cur_sec / self.total_duration) * 100.0))

                    eta_str = "--:--"
                    spd_val = float(spd_m.group(1)) if spd_m else 0.0
                    rem_sec = max(0.0, self.total_duration - cur_sec)
                    if spd_val > 0.1:
                        eta_sec = rem_sec / spd_val
                        eta_str = f"{int(eta_sec // 60):02d}:{int(eta_sec % 60):02d}"

                    self.progress_changed.emit(percent, cur_speed, eta_str)

            self._proc.wait()

            # 清理临时列表文件
            self._cleanup_temp_file()

            if self._is_cancelled:
                self.finished.emit(False, "任务已被用户取消", "")
                return

            if self._proc.returncode == 0:
                self.progress_changed.emit(100.0, "--", "00:00")
                self.finished.emit(True, "视频无损合并完成", str(self.output_path))
            else:
                self.finished.emit(False, f"合并失败: 错误代码 {self._proc.returncode}", "")

        except Exception as e:
            self._cleanup_temp_file()
            self.finished.emit(False, f"执行异常: {e}", "")
