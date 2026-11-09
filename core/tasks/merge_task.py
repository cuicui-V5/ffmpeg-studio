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
    # 裁剪支持
    is_cropped: bool = False
    crop_start: float = 0.0
    crop_end: float = 0.0
    snapped_start: float = 0.0
    snapped_end: float = 0.0

    @property
    def effective_duration(self) -> float:
        if self.is_cropped and self.snapped_end > self.snapped_start:
            return self.snapped_end - self.snapped_start
        return self.duration

    @property
    def effective_size(self) -> int:
        if self.is_cropped and self.duration > 0:
            ratio = self.effective_duration / self.duration
            return int(self.size * min(1.0, max(0.01, ratio)))
        return self.size

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
    """后台无损合并执行线程 (支持先预裁剪后无损合并)"""
    progress_changed = Signal(float, str, str)  # (percent: 0-100, speed, eta_str)
    log_emitted = Signal(str)
    finished = Signal(bool, str, str)           # (success, message, output_path)

    def __init__(self, items, output_path: Path, total_duration: float = 0.0, parent=None):
        super().__init__(parent)
        # 兼容 list[MergeItem] 或 list[Path]
        if items and isinstance(items[0], Path):
            self.items = [MergeItem(filepath=p, filename=p.name, duration=total_duration / len(items)) for p in items]
        else:
            self.items = list(items)

        self.output_path = Path(output_path)
        self.total_duration = total_duration if total_duration > 0 else sum(it.effective_duration for it in self.items)
        self._proc = None
        self._is_cancelled = False
        self._list_file = None
        self._temp_dir = None

    def cancel(self):
        self._is_cancelled = True
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.terminate()
                self._proc.kill()
            except Exception:
                pass
        self._cleanup_temp_files()
        if self.output_path and self.output_path.exists():
            try:
                self.output_path.unlink()
            except Exception:
                pass

    def _cleanup_temp_files(self):
        if self._list_file and os.path.exists(self._list_file):
            try:
                os.remove(self._list_file)
            except Exception:
                pass
            self._list_file = None

        if self._temp_dir and os.path.exists(self._temp_dir):
            try:
                import shutil
                shutil.rmtree(self._temp_dir, ignore_errors=True)
            except Exception:
                pass
            self._temp_dir = None

    def run(self):
        self._is_cancelled = False
        tool_ffmpeg = tool_mgr.get_path("ffmpeg")
        if not tool_ffmpeg:
            self.finished.emit(False, "未找到 ffmpeg 可执行文件，无法合并", "")
            return

        if len(self.items) < 2:
            self.finished.emit(False, "待合并的视频数量少于 2 个", "")
            return

        out_folder = self.output_path.parent
        out_folder.mkdir(parents=True, exist_ok=True)
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0

        # 1. 预裁剪处理（如果有被标记裁剪的视频）
        cropped_items = [(idx, item) for idx, item in enumerate(self.items) if item.is_cropped]
        concat_input_paths: list[Path] = []

        if cropped_items:
            self._temp_dir = out_folder / f".tmp_cut_{uuid.uuid4().hex[:8]}"
            self._temp_dir.mkdir(parents=True, exist_ok=True)
            self.log_emitted.emit(f"检测到 {len(cropped_items)} 个需要预裁剪的片段，开始极速流复制预裁剪...")

            total_cropped = len(cropped_items)
            for crop_i, (idx, item) in enumerate(cropped_items):
                if self._is_cancelled:
                    self._cleanup_temp_files()
                    self.finished.emit(False, "任务已被用户取消", "")
                    return

                percent = (crop_i / max(1, total_cropped)) * 30.0  # 预裁剪阶段占前 30% 进度
                self.progress_changed.emit(
                    percent, "极速流复制",
                    f"预裁剪片段 {crop_i + 1}/{total_cropped}"
                )
                temp_cut_file = self._temp_dir / f"cut_{idx:03d}_{item.filepath.name}"

                cmd_cut = [
                    tool_ffmpeg, '-y', '-hide_banner',
                    '-ss', str(item.snapped_start),
                    '-to', str(item.snapped_end),
                    '-i', str(item.filepath),
                    '-c', 'copy',
                    '-avoid_negative_ts', 'make_zero',
                    str(temp_cut_file)
                ]
                self.log_emitted.emit(f"[预裁剪] {item.filename} ({item.snapped_start:.2f}s -> {item.snapped_end:.2f}s)")

                try:
                    self._proc = subprocess.Popen(
                        cmd_cut,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        errors='ignore',
                        creationflags=creationflags
                    )
                    self._proc.communicate()
                    if self._proc.returncode != 0:
                        self._cleanup_temp_files()
                        self.finished.emit(False, f"预裁剪片段 {item.filename} 失败", "")
                        return
                except Exception as e:
                    self._cleanup_temp_files()
                    self.finished.emit(False, f"预裁剪异常: {e}", "")
                    return

        # 组装最终 concat 列表
        for idx, item in enumerate(self.items):
            if item.is_cropped:
                concat_input_paths.append(self._temp_dir / f"cut_{idx:03d}_{item.filepath.name}")
            else:
                concat_input_paths.append(item.filepath)

        # 2. 生成标准的 FFmpeg Concat 列表文件
        self._list_file = out_folder / f"concat_list_{uuid.uuid4().hex[:8]}.txt"
        try:
            with open(self._list_file, "w", encoding="utf-8") as f:
                for p in concat_input_paths:
                    clean_str = str(p.resolve()).replace('\\', '/').replace("'", "'\\''")
                    f.write(f"file '{clean_str}'\n")
        except Exception as e:
            self._cleanup_temp_files()
            self.finished.emit(False, f"创建合并列表文件失败: {e}", "")
            return

        # 3. 构建 FFmpeg 极速流复制无损合并命令
        cmd = [
            tool_ffmpeg, '-y', '-hide_banner',
            '-f', 'concat', '-safe', '0',
            '-i', str(self._list_file),
            '-c', 'copy',
            str(self.output_path)
        ]

        total_effective_duration = sum(item.effective_duration for item in self.items)
        self.log_emitted.emit(f"开始无损合并: {len(self.items)} 个视频片段")
        self.log_emitted.emit(f"[EXEC] {' '.join(cmd)}\n")

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

            start_percent = 30.0 if cropped_items else 0.0

            for line in self._proc.stdout:
                if self._is_cancelled:
                    break

                line_str = line.strip()
                if line_str:
                    self.log_emitted.emit(line_str)

                time_m = out_time_pattern.search(line_str)
                spd_m = speed_pattern.search(line_str)

                cur_speed = f"{spd_m.group(1)}x" if spd_m else "--"

                if time_m and total_effective_duration > 0:
                    h, m, s = float(time_m.group(1)), float(time_m.group(2)), float(time_m.group(3))
                    cur_sec = h * 3600 + m * 60 + s
                    ratio = min(0.99, max(0.0, cur_sec / total_effective_duration))
                    percent = start_percent + ratio * (100.0 - start_percent)

                    eta_str = "--:--"
                    spd_val = float(spd_m.group(1)) if spd_m else 0.0
                    rem_sec = max(0.0, total_effective_duration - cur_sec)
                    if spd_val > 0.1:
                        eta_sec = rem_sec / spd_val
                        eta_str = f"{int(eta_sec // 60):02d}:{int(eta_sec % 60):02d}"

                    self.progress_changed.emit(percent, cur_speed, eta_str)

            self._proc.wait()

            # 清理临时列表与裁剪文件
            self._cleanup_temp_files()

            if self._is_cancelled:
                self.finished.emit(False, "任务已被用户取消", "")
                return

            if self._proc.returncode == 0:
                self.progress_changed.emit(100.0, "--", "00:00")
                self.finished.emit(True, "视频无损合并完成", str(self.output_path))
            else:
                self.finished.emit(False, f"合并失败: 错误代码 {self._proc.returncode}", "")

        except Exception as e:
            self._cleanup_temp_files()
            self.finished.emit(False, f"执行异常: {e}", "")
