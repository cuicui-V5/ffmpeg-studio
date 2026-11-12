import os
import sys
import shutil
import subprocess
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# 将工作区添加到 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.tool_manager import tool_mgr
from core.bgm_helper import BgmConfig, BgmHelper
from core.keyframe_helper import KeyframeHelper
from core.tasks.cutter_task import CutterWorker
from core.tasks.split_task import BatchSplitWorker
from core.tasks.merge_task import MergeItem, MergeWorker
from core.tasks.compress_task import CompressItem, BatchCompressWorker

TEST_DIR = Path("test_bgm_sandbox").resolve()

def setup_test_media():
    TEST_DIR.mkdir(parents=True, exist_ok=True)
    ffmpeg = tool_mgr.get_path("ffmpeg")
    assert ffmpeg and os.path.exists(ffmpeg), "ffmpeg 不存在"

    # 1. 生成 4 秒测试视频 (含 440Hz 伴音，设置 GOP 周期为 30 帧即 1 秒 1 个关键帧，便于分段测试)
    v_path = TEST_DIR / "sample_video_audio.mp4"
    if not v_path.exists():
        subprocess.run([
            ffmpeg, '-y', '-hide_banner',
            '-f', 'lavfi', '-i', 'testsrc=duration=4:size=320x240:rate=30',
            '-f', 'lavfi', '-i', 'sine=frequency=440:duration=4',
            '-c:v', 'libx264', '-g', '30', '-c:a', 'aac', '-b:a', '128k',
            str(v_path)
        ], capture_output=True, check=True)

    # 2. 生成 4 秒纯静音视频 (无音频流)
    v_silent = TEST_DIR / "sample_video_silent.mp4"
    if not v_silent.exists():
        subprocess.run([
            ffmpeg, '-y', '-hide_banner',
            '-f', 'lavfi', '-i', 'testsrc=duration=4:size=320x240:rate=30',
            '-c:v', 'libx264', '-an',
            str(v_silent)
        ], capture_output=True, check=True)

    # 3. 生成 2 首不同采样率的背景音乐
    # bgm1: 1.5 秒 800Hz 44100Hz wav
    bgm1 = TEST_DIR / "bgm1_44k.wav"
    if not bgm1.exists():
        subprocess.run([
            ffmpeg, '-y', '-hide_banner',
            '-f', 'lavfi', '-i', 'sine=frequency=800:sample_rate=44100:duration=1.5',
            str(bgm1)
        ], capture_output=True, check=True)

    # bgm2: 2.0 秒 1200Hz 48000Hz mp3
    bgm2 = TEST_DIR / "bgm2_48k.mp3"
    if not bgm2.exists():
        subprocess.run([
            ffmpeg, '-y', '-hide_banner',
            '-f', 'lavfi', '-i', 'sine=frequency=1200:sample_rate=48000:duration=2.0',
            '-c:a', 'libmp3lame',
            str(bgm2)
        ], capture_output=True, check=True)

    return str(v_path), str(v_silent), [str(bgm1), str(bgm2)]

def test_bgm_helper_logic(audio_files):
    print("\n--- 1. 测试 BgmConfig 与 BgmHelper 逻辑参数构建 ---")
    cfg = BgmConfig(
        enabled=True,
        audio_files=audio_files,
        bgm_volume=0.8,
        orig_volume=0.5,
        loop_mode="loop",
        play_order="sequence"
    )
    assert cfg.is_active(), "is_active() 应为 True"

    # 有原声 + loop 模式
    inputs, fc, audio_map, extra_out = BgmHelper.build_bgm_args(
        cfg, has_orig_audio=True, video_input_idx=0, target_duration=4.0
    )
    assert len(inputs) == 4, f"期望 2 个音频文件 4 个参数，实际: {inputs}"
    assert "concat=n=2:v=0:a=1" in fc, "多音频未检测到 concat 拼接"
    assert "aloop=loop=-1:size=2e+09" in fc, "未包含循环滤镜"
    assert "atrim=0:4.000" in fc, "未包含精确时长截取"
    assert "amix=inputs=2" in fc, "未包含混音滤镜"
    assert "-c:a" in audio_map and "aac" in audio_map, "音频映射编码器应为 aac"
    assert extra_out == ['-t', '4.000'], "未设置目标时长参数"
    print("  [PASS] BgmHelper 双音频多格式循环混音参数构建成功")

    # 无原声 + once 播放一次模式
    cfg_once = BgmConfig(
        enabled=True,
        audio_files=[audio_files[0]],
        bgm_volume=1.0,
        orig_volume=0.0,
        loop_mode="once",
        play_order="sequence"
    )
    inputs_o, fc_o, map_o, extra_o = BgmHelper.build_bgm_args(
        cfg_once, has_orig_audio=False, video_input_idx=0, target_duration=3.5
    )
    assert len(inputs_o) == 2, "单文件输入应为 2 个参数"
    assert "concat" not in fc_o, "单文件不应调用 concat"
    assert "aloop" not in fc_o, "播放一次不应包含 aloop"
    assert "apad" in fc_o, "播放一次应包含 apad 补零对齐"
    assert "amix" not in fc_o, "无原声时不应调用 amix"
    assert "anull" in fc_o, "应包含 anull 单音轨输出"
    print("  [PASS] BgmHelper 单音频单次播放参数构建成功")

def test_cutter_with_bgm(video_path, audio_files):
    print("\n--- 2. 测试视频裁剪结合 BGM (流复制保持极速) ---")
    out_dir = TEST_DIR / "cut_out"
    out_dir.mkdir(exist_ok=True)

    bgm_cfg = BgmConfig(
        enabled=True,
        audio_files=audio_files,
        bgm_volume=0.9,
        orig_volume=0.6,
        loop_mode="loop",
        play_order="sequence"
    )

    worker = CutterWorker(
        file_path=video_path,
        start_sec=1.0,
        end_sec=3.0,
        auto_snap=False,
        output_dir=str(out_dir),
        bgm_config=bgm_cfg
    )

    result_holder = []
    worker.finished.connect(lambda ok, msg, path: result_holder.append((ok, msg, path)))
    worker.run() # 同步执行

    assert result_holder and result_holder[0][0], f"裁剪执行失败: {result_holder}"
    out_path = Path(result_holder[0][2])
    assert out_path.exists() and out_path.stat().st_size > 0, "裁剪输出文件不存在"

    # 验证流信息：视频流编码必须为 h264，音频流必须为 aac
    meta = KeyframeHelper.get_video_info(str(out_path))
    assert meta["codec"] == "h264", f"视频流编码被改变: {meta['codec']}"
    assert meta["audio_codec"] == "aac", f"音频未成功转码为 aac: {meta['audio_codec']}"
    print(f"  [PASS] 裁剪成功！视频时长: {meta['duration']:.2f}s, 大小: {meta['size']} 字节")

def test_merge_with_bgm(video_path, audio_files):
    print("\n--- 3. 测试视频合并结合 BGM ---")
    out_dir = TEST_DIR / "merge_out"
    out_dir.mkdir(exist_ok=True)
    out_file = out_dir / "merged_with_bgm.mp4"

    info = KeyframeHelper.get_video_info(video_path)
    m1 = MergeItem(
        filepath=Path(video_path),
        filename=Path(video_path).name,
        duration=info["duration"],
        size=info["size"],
        width=info["width"],
        height=info["height"],
        codec=info["codec"],
        pix_fmt=info["pix_fmt"],
        fps=info["fps"],
        audio_codec=info["audio_codec"]
    )
    m2 = MergeItem(
        filepath=Path(video_path),
        filename=Path(video_path).name,
        duration=info["duration"],
        size=info["size"],
        width=info["width"],
        height=info["height"],
        codec=info["codec"],
        pix_fmt=info["pix_fmt"],
        fps=info["fps"],
        audio_codec=info["audio_codec"]
    )

    bgm_cfg = BgmConfig(
        enabled=True,
        audio_files=audio_files,
        bgm_volume=0.7,
        orig_volume=0.4,
        loop_mode="loop",
        play_order="random"
    )

    worker = MergeWorker(
        items=[m1, m2],
        output_path=out_file,
        total_duration=8.0,
        bgm_config=bgm_cfg
    )

    result_holder = []
    worker.finished.connect(lambda ok, msg, path: result_holder.append((ok, msg, path)))
    worker.run()

    assert result_holder and result_holder[0][0], f"合并失败: {result_holder}"
    assert out_file.exists() and out_file.stat().st_size > 0, "合并输出文件不存在"

    meta = KeyframeHelper.get_video_info(str(out_file))
    assert meta["codec"] == "h264", f"合并后视频编码异常: {meta['codec']}"
    assert meta["audio_codec"] == "aac", f"合并后音频未转码为 aac: {meta['audio_codec']}"
    assert abs(meta["duration"] - 8.0) < 0.5, f"合并时长异常: {meta['duration']}s"
    print(f"  [PASS] 合并成功！总时长: {meta['duration']:.2f}s, 大小: {meta['size']} 字节")

def test_split_with_bgm(video_path, audio_files):
    print("\n--- 4. 测试视频分段结合 BGM ---")
    out_dir = TEST_DIR / "split_out"
    out_dir.mkdir(exist_ok=True)

    bgm_cfg = BgmConfig(
        enabled=True,
        audio_files=audio_files,
        bgm_volume=0.8,
        orig_volume=1.0,
        loop_mode="loop"
    )

    # 4秒视频，设置最大时长 2.5 秒触发切分为 2 段
    worker = BatchSplitWorker(
        files=[video_path],
        max_size=1024 * 1024 * 1024,
        max_duration=2.5,
        output_dir=str(out_dir),
        bgm_config=bgm_cfg
    )

    finished_called = []
    worker.all_finished.connect(lambda: finished_called.append(True))
    worker.run()

    assert finished_called, "分段任务未能正常触发 all_finished"
    parts = list(out_dir.glob("sample_video_audio_part*.mp4"))
    assert len(parts) >= 2, f"期望切分至少 2 段，实际切分: {parts}"
    for p in parts:
        meta = KeyframeHelper.get_video_info(str(p))
        assert meta["codec"] == "h264", f"分段视频流编码异常: {meta['codec']}"
        assert meta["audio_codec"] == "aac", f"分段音频未转码 aac: {meta['audio_codec']}"
    print(f"  [PASS] 分段成功！共切分 {len(parts)} 个文件")

from ui.components.bgm_widget import BgmWidget
from PySide6.QtWidgets import QApplication

def test_bgm_widget_ui(audio_files):
    print("\n--- 6. 测试 BgmWidget UI 控件交互与配置读取 ---")
    app = QApplication.instance() or QApplication(sys.argv)
    widget = BgmWidget()
    
    # 初始默认状态
    assert not widget.isChecked(), "初始状态应为未勾选"
    cfg = widget.get_config()
    assert not cfg.enabled, "初始 enabled 应为 False"
    assert cfg.bgm_volume == 1.0, "初始 bgm_volume 应为 1.0"
    assert cfg.orig_volume == 1.0, "初始 orig_volume 应为 1.0"
    assert cfg.loop_mode == "loop", "初始 loop_mode 应为 loop"
    assert cfg.play_order == "sequence", "初始 play_order 应为 sequence"

    # 模拟用户设置与拖入音频
    widget.setChecked(True)
    widget._add_audio_paths(audio_files)
    widget.slider_bgm.setValue(150)
    widget.slider_orig.setValue(0) # 静音
    widget.combo_loop.setCurrentIndex(1) # 播放一次
    widget.combo_order.setCurrentIndex(1) # 随机播放

    new_cfg = widget.get_config()
    assert new_cfg.enabled, "启用状态应为 True"
    assert len(new_cfg.audio_files) == len(audio_files), "音频文件列表数量不匹配"
    assert new_cfg.bgm_volume == 1.5, f"音量应为 1.5，实际: {new_cfg.bgm_volume}"
    assert new_cfg.orig_volume == 0.0, f"原声音量应为 0.0，实际: {new_cfg.orig_volume}"
    assert new_cfg.loop_mode == "once", "循环模式应为 once"
    assert new_cfg.play_order == "random", "播放顺序应为 random"
    assert widget.lbl_orig_val.text() == "静音", "原声音量为 0 时标签应展示为静音"

    # 测试 set_config 反向应用
    apply_cfg = BgmConfig(
        enabled=True,
        audio_files=[audio_files[0]],
        bgm_volume=0.8,
        orig_volume=0.7,
        loop_mode="loop",
        play_order="sequence"
    )
    widget.set_config(apply_cfg)
    assert widget.slider_bgm.value() == 80
    assert widget.slider_orig.value() == 70
    assert widget.combo_loop.currentIndex() == 0
    assert widget.combo_order.currentIndex() == 0
    assert widget.audio_list.count() == 1
    print("  [PASS] BgmWidget UI 控件交互、参数双向绑定及配置提取均正常！")

def test_compress_with_bgm(video_path, audio_files):
    print("\n--- 5. 测试批量压制结合 BGM ---")
    out_dir = TEST_DIR / "compress_out"
    out_dir.mkdir(exist_ok=True)

    item = CompressItem(video_path)
    item.output_dir = out_dir
    item.output_path = out_dir / "compressed_bgm.mp4"
    item.duration = 4.0

    bgm_cfg = BgmConfig(
        enabled=True,
        audio_files=audio_files,
        bgm_volume=0.75,
        orig_volume=0.5,
        loop_mode="loop"
    )

    worker = BatchCompressWorker(
        items=[item],
        encoder="libx264",
        cq=28,
        bgm_config=bgm_cfg
    )

    finished_called = []
    worker.all_finished.connect(lambda: finished_called.append(True))
    worker.run()

    assert finished_called, "压制任务未能触发 all_finished"
    assert item.status == "已完成", f"压制状态异常: {item.status}"
    assert item.output_path.exists() and item.output_path.stat().st_size > 0, "压制输出文件不存在"

    meta = KeyframeHelper.get_video_info(str(item.output_path))
    assert meta["codec"] == "h264", f"编码异常: {meta['codec']}"
    assert meta["audio_codec"] == "aac", f"音频编码异常: {meta['audio_codec']}"
    print(f"  [PASS] 压制成功！分辨率: {meta['width']}x{meta['height']}, 大小: {meta['size']} 字节")

def main():
    print("========================================")
    print("       全面背景音乐功能自动化测试       ")
    print("========================================")
    v_audio, v_silent, audios = setup_test_media()
    try:
        test_bgm_helper_logic(audios)
        test_cutter_with_bgm(v_audio, audios)
        test_merge_with_bgm(v_audio, audios)
        test_split_with_bgm(v_audio, audios)
        test_compress_with_bgm(v_audio, audios)
        test_bgm_widget_ui(audios)
        print("\n========================================")
        print("🎉 全部 6 项 BGM 核心功能、UI 控件与四大选项卡集成测试 100% 通过！")
        print("========================================")
    finally:
        # 清理沙盒测试目录
        shutil.rmtree(TEST_DIR, ignore_errors=True)

if __name__ == "__main__":
    main()
