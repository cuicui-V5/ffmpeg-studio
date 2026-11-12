import os
import sys
import subprocess
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# 添加当前目录到 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.tool_manager import tool_mgr
from core.hardware import HardwareDetector
from core.keyframe_helper import KeyframeHelper
from core.tasks.compress_task import CompressItem
from core.tasks.cutter_task import CutterWorker
from core.tasks.split_task import SplitPlan
from core.tasks.merge_task import MergeItem, MergeWorker, validate_merge_consistency

def test_system():
    print("=== 1. 测试工具与硬件加速检测 ===")
    status = tool_mgr.get_status_dict()
    for k, v in status.items():
        print(f"  [{k}] 可用: {v['available']}, 路径: {v['path']}")
    assert status['ffmpeg']['available'], "FFmpeg 必须可用"
    assert status['exiftool']['available'], "ExifTool 必须可用"

    best_enc = HardwareDetector.get_best_hevc_encoder()
    print(f"  最佳 HEVC 编码器: {best_enc}")

    test_video = str(Path("..") / "DJI_20260804201039_0023_D.MP4")
    if not os.path.exists(test_video):
        print("未找到测试视频，跳过后续媒体测试")
        return

    print("\n=== 2. 测试视频元信息与关键帧吸附 ===")
    info = KeyframeHelper.get_video_info(test_video)
    print(f"  时长: {info['duration']:.2f}s, 分辨率: {info['width']}x{info['height']}, 编码: {info['codec']}, 像素格式: {info['pix_fmt']}, 音频: {info['audio_codec']}")
    assert info['duration'] > 0, "无法读取视频时长"
    assert info['pix_fmt'] != "", "未能提取到像素格式"

    kfs = KeyframeHelper.get_keyframes(test_video)
    print(f"  关键帧数量: {len(kfs)} 个")
    assert len(kfs) > 0, "未能提取到关键帧"

    # 测试吸附
    snap_s, diff_s = KeyframeHelper.snap_to_keyframe(10.4, kfs, mode="floor")
    snap_e, diff_e = KeyframeHelper.snap_to_keyframe(16.7, kfs, mode="ceil")
    print(f"  输入区间 10.4s - 16.7s -> 吸附后: {snap_s}s - {snap_e}s")

    print("\n=== 3. 测试关键帧对齐极速流复制裁切 (杜绝黑屏) ===")
    out_dir = Path("test_output")
    out_dir.mkdir(exist_ok=True)
    worker = CutterWorker(
        test_video,
        start_sec=10.4,
        end_sec=16.7,
        auto_snap=True,
        output_dir=str(out_dir)
    )
    worker.run() # 同步执行 run
    out_cut = out_dir / f"DJI_20260804201039_0023_D_cut.MP4"
    assert out_cut.exists() and out_cut.stat().st_size > 0, "裁切文件生成失败"
    print(f"  裁切成功！输出文件大小: {out_cut.stat().st_size / (1024*1024):.2f} MB")

    print("\n=== 4. 测试元数据分析 (Exif / 日期) ===")
    item = CompressItem(test_video)
    item.probe_media_info()
    item.probe_metadata()
    print(f"  探测日期: {item.final_date} (来源: {item.date_source})")
    print(f"  探测 GPS: {item.final_lat}, {item.final_lon} (来源: {item.gps_source})")
    assert item.final_date is not None, "应该提取到 DJI 视频拍摄日期"

    print("\n=== 5. 测试平台分段方案预估 ===")
    qq_plan = SplitPlan(test_video, 1024*1024*1024, 585.0)
    print(f"  QQ 规则 (1GB/585s): 需要分段={qq_plan.needs_split}, 段数={qq_plan.part_count}")
    wechat_plan = SplitPlan(test_video, 50*1024*1024, 30.0)
    print(f"  微信朋友圈规则 (50MB/30s): 需要分段={wechat_plan.needs_split}, 段数={wechat_plan.part_count}")
    assert wechat_plan.needs_split, "50MB 规则应该触发分段"

    print("\n=== 6. 测试视频无损合并与参数一致性校验 ===")
    # 6.1 校验逻辑测试 - 一致样本
    m1 = MergeItem(Path("v1.mp4"), "v1.mp4", duration=10, width=1920, height=1080, codec="hevc", pix_fmt="yuv420p", fps=50.0, audio_codec="aac", sample_rate=48000, channels=2)
    m2 = MergeItem(Path("v2.mp4"), "v2.mp4", duration=15, width=1920, height=1080, codec="hevc", pix_fmt="yuv420p", fps=50.0, audio_codec="aac", sample_rate=48000, channels=2)
    ok, summary, warns = validate_merge_consistency([m1, m2])
    print(f"  一致性测试 (相同参数): ok={ok}, summary={summary[:30]}...")
    assert ok and len(warns) == 0, "相同参数应判定为完全一致"

    # 6.2 校验逻辑测试 - 分辨率与编码不一致样本
    m3_diff = MergeItem(Path("v3.mp4"), "v3.mp4", duration=12, width=1280, height=720, codec="h264", pix_fmt="yuv420p", fps=30.0, audio_codec="aac", sample_rate=44100, channels=2)
    ok_diff, summary_diff, warns_diff = validate_merge_consistency([m1, m3_diff])
    print(f"  一致性测试 (差异参数): ok={ok_diff}, 警告数量={len(warns_diff)}")
    assert not ok_diff and len(warns_diff) >= 3, "差异参数应精准报出多项不匹配警告"

    # 6.3 真实视频片段极速流复制合并测试
    clip1 = out_dir / "clip1.mp4"
    clip2 = out_dir / "clip2.mp4"
    merged_file = out_dir / "test_merged_output.mp4"

    creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    ffmpeg = tool_mgr.get_path("ffmpeg")
    # 切割两段极小片段进行合并实测
    subprocess.run([ffmpeg, '-y', '-ss', '0', '-to', '2', '-i', test_video, '-c', 'copy', str(clip1)], capture_output=True, creationflags=creationflags)
    subprocess.run([ffmpeg, '-y', '-ss', '4', '-to', '6', '-i', test_video, '-c', 'copy', str(clip2)], capture_output=True, creationflags=creationflags)
    assert clip1.exists() and clip2.exists(), "切片测试文件准备失败"

    merge_worker = MergeWorker([clip1, clip2], merged_file, total_duration=4.0)
    merge_worker.run() # 同步执行

    assert merged_file.exists() and merged_file.stat().st_size > 0, "合并输出文件不存在或为空"
    merged_info = KeyframeHelper.get_video_info(str(merged_file))
    print(f"  真实合并验证成功！输出时长: {merged_info['duration']:.2f}s, 大小: {merged_file.stat().st_size / (1024*1024):.2f} MB")
    assert merged_info['duration'] >= 3.5, "合并时长应接近 4 秒"

    # 6.4 预裁剪 + 无损合并流水线测试
    crop_merge_file = out_dir / "test_crop_merged_output.mp4"
    cm1 = MergeItem(
        filepath=Path(test_video), filename=Path(test_video).name,
        duration=merged_info['duration'], size=1024*1024, width=1920, height=1080,
        codec="hevc", pix_fmt="yuv420p", fps=50.0, audio_codec="aac", sample_rate=48000, channels=2,
        is_cropped=True, crop_start=1.0, crop_end=3.0, snapped_start=1.0, snapped_end=3.0
    )
    cm2 = MergeItem(
        filepath=Path(test_video), filename=Path(test_video).name,
        duration=merged_info['duration'], size=1024*1024, width=1920, height=1080,
        codec="hevc", pix_fmt="yuv420p", fps=50.0, audio_codec="aac", sample_rate=48000, channels=2,
        is_cropped=True, crop_start=5.0, crop_end=8.0, snapped_start=5.0, snapped_end=8.0
    )
    crop_worker = MergeWorker([cm1, cm2], crop_merge_file)
    crop_worker.run()
    assert crop_merge_file.exists() and crop_merge_file.stat().st_size > 0, "预裁剪合并文件未成功生成"
    cm_info = KeyframeHelper.get_video_info(str(crop_merge_file))
    print(f"  预裁剪+无损合并验证成功！输出时长: {cm_info['duration']:.2f}s, 大小: {crop_merge_file.stat().st_size / (1024*1024):.2f} MB")
    assert cm_info['duration'] >= 4.0, "预裁剪合并时长应接近 5 秒"

    # 清理所有测试生成的文件
    for f in [out_cut, clip1, clip2, merged_file, crop_merge_file]:
        if f.exists():
            f.unlink()
    if out_dir.exists():
        try:
            out_dir.rmdir()
        except Exception:
            pass

    print("\n🎉 全部单元测试通过！核心功能与算法验证 100% 成功！")

    # 执行 BGM 功能测试
    import test_bgm_feature
    test_bgm_feature.main()

if __name__ == "__main__":
    test_system()
    import test_bgm_feature
    test_bgm_feature.main()
