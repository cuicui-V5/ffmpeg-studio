import os
import random
from dataclasses import dataclass, field
from pathlib import Path

AUDIO_EXTENSIONS = {'.mp3', '.wav', '.aac', '.m4a', '.flac', '.ogg', '.wma', '.opus', '.aiff', '.ac3'}

@dataclass
class BgmConfig:
    """背景音乐配置"""
    enabled: bool = False
    audio_files: list[str] = field(default_factory=list)
    bgm_volume: float = 1.0        # 0.0 ~ 2.0 (1.0 = 100%)
    orig_volume: float = 1.0       # 0.0 ~ 2.0 (1.0 = 100%, 0.0 = mute)
    loop_mode: str = "loop"        # "loop": 无限循环, "once": 播放一次
    play_order: str = "sequence"   # "sequence": 顺序播放, "random": 随机播放

    def is_active(self) -> bool:
        """检查配置是否处于有效启用状态"""
        if not self.enabled:
            return False
        valid_files = [f for f in self.audio_files if os.path.exists(f)]
        return len(valid_files) > 0

class BgmHelper:
    """构建用于 FFmpeg 的音频与背景音乐混合参数"""

    @staticmethod
    def prepare_audio_files(bgm_config: BgmConfig) -> list[str]:
        """获取并根据播放顺序规则整理有效的音频路径列表"""
        valid_files = [str(Path(f).resolve()) for f in bgm_config.audio_files if os.path.exists(f)]
        if not valid_files:
            return []
        
        files = list(valid_files)
        if bgm_config.play_order == "random":
            random.shuffle(files)
        return files

    @staticmethod
    def build_bgm_args(
        bgm_config: BgmConfig,
        has_orig_audio: bool = True,
        video_input_idx: int = 0,
        target_duration: float = 0.0,
        start_bgm_input_idx: int = 1
    ) -> tuple[list[str], str, list[str], list[str]]:
        """
        构建 FFmpeg 背景音乐参数
        返回: (extra_inputs, filter_complex_str, audio_map_args, extra_output_args)
        
        - extra_inputs: 需追加到 FFmpeg 命令中的音频输入参数 (例如 ['-i', f1, '-i', f2])
        - filter_complex_str: 构建好的 filter_complex 表达式
        - audio_map_args: 输出音频映射参数 (例如 ['-map', '[aout]', '-c:a', 'aac', '-b:a', '192k'])
        - extra_output_args: 输出额外参数 (例如 ['-t', 'xx.xxx'])
        """
        if not bgm_config.is_active():
            return [], "", [], []

        files = BgmHelper.prepare_audio_files(bgm_config)
        if not files:
            return [], "", [], []

        extra_inputs: list[str] = []
        for f in files:
            extra_inputs.extend(['-i', f])

        filter_parts: list[str] = []
        n_files = len(files)

        # 1. 对所有背景音乐输入统一标准化为 48000Hz 立体声，避免不同采样率/声道拼接报错
        for idx in range(n_files):
            input_stream = f"[{start_bgm_input_idx + idx}:a]"
            filter_parts.append(f"{input_stream}aformat=sample_rates=48000:channel_layouts=stereo[ba{idx}]")

        # 2. 多音频拼接
        if n_files == 1:
            bgm_stream = "[ba0]"
        else:
            cat_inputs = "".join(f"[ba{idx}]" for idx in range(n_files))
            filter_parts.append(f"{cat_inputs}concat=n={n_files}:v=0:a=1[bgm_cat]")
            bgm_stream = "[bgm_cat]"

        # 3. 循环模式与音量调节、时长精准裁剪
        dur_str = f"{target_duration:.3f}" if target_duration > 0 else None
        vol_str = f"{bgm_config.bgm_volume:.2f}"

        if bgm_config.loop_mode == "loop":
            if dur_str:
                filter_parts.append(f"{bgm_stream}volume={vol_str},aloop=loop=-1:size=2e+09,atrim=0:{dur_str}[bgm]")
            else:
                filter_parts.append(f"{bgm_stream}volume={vol_str},aloop=loop=-1:size=2e+09[bgm]")
        else:
            if dur_str:
                filter_parts.append(f"{bgm_stream}volume={vol_str},apad,atrim=0:{dur_str}[bgm]")
            else:
                filter_parts.append(f"{bgm_stream}volume={vol_str},apad[bgm]")

        # 4. 与原视频原声音轨混音
        if has_orig_audio and bgm_config.orig_volume > 0.0:
            orig_vol_str = f"{bgm_config.orig_volume:.2f}"
            filter_parts.append(
                f"[{video_input_idx}:a]aformat=sample_rates=48000:channel_layouts=stereo,volume={orig_vol_str}[orig]"
            )
            filter_parts.append(
                "[orig][bgm]amix=inputs=2:duration=first:dropout_transition=2:normalize=0[aout]"
            )
        else:
            # 原视频无音轨或原声静音
            filter_parts.append("[bgm]anull[aout]")

        filter_complex_str = ";".join(filter_parts)
        audio_map_args = ['-map', '[aout]', '-c:a', 'aac', '-b:a', '192k']

        extra_output_args = []
        if target_duration > 0:
            extra_output_args = ['-t', dur_str]

        return extra_inputs, filter_complex_str, audio_map_args, extra_output_args
