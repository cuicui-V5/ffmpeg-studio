import os
import re
import subprocess
import time
from pathlib import Path
from PySide6.QtCore import QThread, Signal

class CommandWorker(QThread):
    """
    通用后台子进程执行线程
    实时解析 FFmpeg 的进度、速度、FPS 与剩余时间
    """
    # 信号定义
    progress_changed = Signal(float, float, str, str)  # (percent: 0-100, fps, speed, eta_str)
    log_received = Signal(str)                         # 实时日志输出
    task_finished = Signal(bool, str)                  # (是否成功, 结果描述)

    def __init__(self, cmd: list[str], total_duration: float = 0.0, output_file: str = ""):
        super().__init__()
        self.cmd = cmd
        self.total_duration = total_duration
        self.output_file = output_file
        self.process = None
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True
        if self.process and self.process.poll() is None:
            try:
                self.process.terminate()
                self.process.kill()
            except Exception:
                pass
        # 清理未完成的文件
        if self.output_file and os.path.exists(self.output_file):
            try:
                os.remove(self.output_file)
            except Exception:
                pass

    def run(self):
        self._is_cancelled = False
        full_cmd_str = " ".join(f'"{c}"' if " " in c else c for c in self.cmd)
        self.log_received.emit(f"[EXEC] {full_cmd_str}\n")

        # 启动进程 (Windows 下使用 CREATE_NO_WINDOW 杜绝任何黑框弹窗)
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        try:
            self.process = subprocess.Popen(
                self.cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                errors="ignore",
                bufsize=1,
                creationflags=creationflags
            )
        except Exception as e:
            self.task_finished.emit(False, f"启动进程失败: {e}")
            return

        out_time_pattern = re.compile(r'time=(\d{2}):(\d{2}):(\d{2}\.\d+)')
        fps_pattern = re.compile(r'fps=\s*([\d\.]+)')
        speed_pattern = re.compile(r'speed=\s*([\d\.]+)x')

        start_time = time.time()
        
        while True:
            if self._is_cancelled:
                self.task_finished.emit(False, "任务已被用户取消")
                return

            line = self.process.stdout.readline()
            if not line and self.process.poll() is not None:
                break

            if not line:
                continue

            cleaned_line = line.strip()
            if cleaned_line:
                self.log_received.emit(cleaned_line)

            # 解析进度
            time_match = out_time_pattern.search(cleaned_line)
            fps_match = fps_pattern.search(cleaned_line)
            speed_match = speed_pattern.search(cleaned_line)

            cur_fps = float(fps_match.group(1)) if fps_match else 0.0
            cur_speed = f"{speed_match.group(1)}x" if speed_match else ""

            if time_match and self.total_duration > 0:
                h, m, s = float(time_match.group(1)), float(time_match.group(2)), float(time_match.group(3))
                cur_sec = h * 3600 + m * 60 + s
                percent = min(100.0, max(0.0, (cur_sec / self.total_duration) * 100))

                # 计算 ETA
                eta_str = "--:--"
                speed_val = float(speed_match.group(1)) if speed_match else 0.0
                rem_sec = max(0.0, self.total_duration - cur_sec)
                if speed_val > 0.01:
                    eta_sec = rem_sec / speed_val
                    eta_str = f"{int(eta_sec // 60):02d}:{int(eta_sec % 60):02d}"

                self.progress_changed.emit(percent, cur_fps, cur_speed, eta_str)

        ret_code = self.process.poll()
        if self._is_cancelled:
            self.task_finished.emit(False, "任务已被用户取消")
        elif ret_code == 0:
            self.progress_changed.emit(100.0, 0.0, "", "00:00")
            self.task_finished.emit(True, "任务执行完成")
        else:
            self.task_finished.emit(False, f"执行异常退出 (代码: {ret_code})")
