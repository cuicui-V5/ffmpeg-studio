import os
import math
import shutil
import subprocess
from pathlib import Path
from PySide6.QtCore import QThread, Signal
from core.tool_manager import tool_mgr
from core.keyframe_helper import KeyframeHelper
from core.bgm_helper import BgmConfig, BgmHelper

# 预设配置
PRESETS = {
    "QQ文件限制": {
        "max_size": 1 * 1024 * 1024 * 1024,
        "max_duration": 585.0
    },
    "微信朋友圈限制": {
        "max_size": 25 * 1024 * 1024,
        "max_duration": 30.0
    },
    "微信聊天限制": {
        "max_size": 100 * 1024 * 1024,
        "max_duration": 300.0
    },
    "自定义限制": {
        "max_size": 500 * 1024 * 1024,
        "max_duration": 600.0
    }
}

class SplitPlan:
    """分段切片方案估算"""
    def __init__(self, file_path: str, max_size_bytes: int, max_duration_sec: float, safety_factor: float = 0.95):
        self.file_path = Path(file_path).resolve()
        self.filename = self.file_path.name
        self.max_size = max_size_bytes
        self.max_duration = max_duration_sec
        self.safety_factor = safety_factor
        
        info = KeyframeHelper.get_video_info(str(self.file_path))
        self.duration = info.get("duration", 0.0)
        self.size = info.get("size", 0)
        
        self.needs_split = False
        self.split_time = 0.0
        self.part_count = 1
        self.avg_part_size = self.size

        self._calculate()

    def _calculate(self):
        if self.duration <= 0 or self.size <= 0:
            return

        if self.size < self.max_size and self.duration < self.max_duration:
            self.needs_split = False
            self.part_count = 1
            self.split_time = self.duration
            self.avg_part_size = self.size
        else:
            self.needs_split = True
            avg_byte_rate = self.size / self.duration
            time_limit_by_size = (self.max_size / avg_byte_rate) * self.safety_factor
            
            self.split_time = min(self.max_duration, time_limit_by_size)
            if self.split_time >= self.max_duration:
                self.split_time = self.max_duration * 0.99
                
            self.part_count = max(2, math.ceil(self.duration / self.split_time))
            self.avg_part_size = int(self.size / self.part_count)

class BatchSplitWorker(QThread):
    """批量分段执行后台线程"""
    item_updated = Signal(int, str, float)  # (index, status_text, progress_pct)
    file_progress = Signal(str, float, str) # (filename, pct, status_desc)
    overall_progress = Signal(int, int)     # (done_count, total_count)
    log_emitted = Signal(str)
    all_finished = Signal()

    def __init__(
        self,
        files: list[str],
        max_size: int,
        max_duration: float,
        output_dir: str = "",
        bgm_config: BgmConfig | None = None
    ):
        super().__init__()
        self.files = files
        self.max_size = max_size
        self.max_duration = max_duration
        self.custom_output_dir = Path(output_dir) if output_dir else None
        self.bgm_config = bgm_config or BgmConfig()
        self._is_cancelled = False
        self._proc = None

    def cancel(self):
        self._is_cancelled = True
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.terminate()
                self._proc.kill()
            except Exception:
                pass

    def run(self):
        tool_ffmpeg = tool_mgr.get_path("ffmpeg")
        total = len(self.files)
        self.overall_progress.emit(0, total)

        for idx, file_str in enumerate(self.files):
            if self._is_cancelled:
                self.item_updated.emit(idx, "已取消", 0.0)
                break

            plan = SplitPlan(file_str, self.max_size, self.max_duration)
            self.log_emitted.emit(f"\n============================\n[{idx+1}/{total}] 准备处理: {plan.filename}")

            # 输出目录：默认源文件同级 output_split
            if self.custom_output_dir:
                out_folder = self.custom_output_dir
            else:
                out_folder = plan.file_path.parent / "output_split"
            out_folder.mkdir(parents=True, exist_ok=True)

            if not plan.needs_split:
                target_file = out_folder / plan.filename
                if self.bgm_config.is_active():
                    self.item_updated.emit(idx, "混音导出中", 30.0)
                    self.file_progress.emit(plan.filename, 30.0, "符合大小限制，正在无损复制视频并混音背景音乐...")
                    self.log_emitted.emit(f"  > 视频体量符合要求，无需切片，正在应用背景音乐混音（视频极速流复制）...")

                    info = KeyframeHelper.get_video_info(str(plan.file_path))
                    has_orig_audio = (info.get("audio_codec", "none") != "none")
                    extra_inputs, filter_complex_str, audio_map_args, extra_output_args = BgmHelper.build_bgm_args(
                        self.bgm_config,
                        has_orig_audio=has_orig_audio,
                        video_input_idx=0,
                        target_duration=plan.duration,
                        start_bgm_input_idx=1
                    )
                    cmd = [
                        tool_ffmpeg, '-y', '-hide_banner',
                        '-i', str(plan.file_path),
                        *extra_inputs,
                        '-filter_complex', filter_complex_str,
                        '-map', '0:v',
                        *audio_map_args,
                        '-c:v', 'copy',
                        *extra_output_args,
                        str(target_file)
                    ]
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
                        if self._is_cancelled:
                            self.item_updated.emit(idx, "已取消", 0.0)
                            break
                        if self._proc.returncode == 0:
                            self.item_updated.emit(idx, "已完成", 100.0)
                            self.file_progress.emit(plan.filename, 100.0, "处理完成")
                            self.log_emitted.emit(f"  处理完成: {target_file.name}")
                        else:
                            self.item_updated.emit(idx, "处理失败", 0.0)
                            self.file_progress.emit(plan.filename, 0.0, f"处理失败: {out}")
                            self.log_emitted.emit(f"  处理失败: {out}")
                    except Exception as e:
                        self.item_updated.emit(idx, f"异常: {e}", 0.0)
                        self.file_progress.emit(plan.filename, 0.0, f"异常: {e}")
                else:
                    self.item_updated.emit(idx, "符合限制 (直接复制)", 50.0)
                    self.file_progress.emit(plan.filename, 50.0, "符合限制，直接复制中...")
                    self.log_emitted.emit(f"  > 视频体量符合要求，无需切片，直接复制中...")
                    try:
                        shutil.copy2(plan.file_path, target_file)
                        self.item_updated.emit(idx, "已完成", 100.0)
                        self.file_progress.emit(plan.filename, 100.0, "复制完成")
                        self.log_emitted.emit(f"  复制完成: {target_file.name}")
                    except Exception as e:
                        self.item_updated.emit(idx, f"复制失败: {e}", 0.0)
                        self.file_progress.emit(plan.filename, 0.0, f"复制失败: {e}")
            else:
                self.item_updated.emit(idx, f"分段中", 10.0)
                self.file_progress.emit(plan.filename, 20.0, f"正在分段处理...")
                self.log_emitted.emit(f"  触发分段处理: 每段限时 {plan.split_time:.2f}s，预计切分 {plan.part_count} 段")
                
                output_pattern = str(out_folder / f"{plan.file_path.stem}_part%03d{plan.file_path.suffix}")
                
                if self.bgm_config.is_active():
                    info = KeyframeHelper.get_video_info(str(plan.file_path))
                    has_orig_audio = (info.get("audio_codec", "none") != "none")
                    extra_inputs, filter_complex_str, audio_map_args, _ = BgmHelper.build_bgm_args(
                        self.bgm_config,
                        has_orig_audio=has_orig_audio,
                        video_input_idx=0,
                        target_duration=plan.duration,
                        start_bgm_input_idx=1
                    )
                    cmd = [
                        tool_ffmpeg, '-y', '-hide_banner',
                        '-i', str(plan.file_path),
                        *extra_inputs,
                        '-filter_complex', filter_complex_str,
                        '-map', '0:v',
                        *audio_map_args,
                        '-c:v', 'copy',
                        '-f', 'segment',
                        '-segment_time', str(plan.split_time),
                        '-reset_timestamps', '1',
                        output_pattern
                    ]
                else:
                    cmd = [
                        tool_ffmpeg, '-y', '-hide_banner',
                        '-i', str(plan.file_path),
                        '-c', 'copy',
                        '-f', 'segment',
                        '-segment_time', str(plan.split_time),
                        '-reset_timestamps', '1',
                        output_pattern
                    ]

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

                    if self._is_cancelled:
                        self.item_updated.emit(idx, "已取消", 0.0)
                        self.file_progress.emit(plan.filename, 0.0, "任务已取消")
                        break

                    if self._proc.returncode == 0:
                        self.item_updated.emit(idx, "已完成", 100.0)
                        self.file_progress.emit(plan.filename, 100.0, f"切片完成，生成 {plan.part_count} 个文件")
                        self.log_emitted.emit(f"  切片完成，文件已存入: {out_folder}")
                    else:
                        self.item_updated.emit(idx, "切片失败", 0.0)
                        self.file_progress.emit(plan.filename, 0.0, "切片失败")
                        self.log_emitted.emit(f"  切片失败: {out}")
                except Exception as e:
                    self.item_updated.emit(idx, f"异常: {e}", 0.0)
                    self.file_progress.emit(plan.filename, 0.0, f"异常: {e}")
                    self.log_emitted.emit(f"  异常: {e}")

            self.overall_progress.emit(idx + 1, total)

        self.all_finished.emit()
