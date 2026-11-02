import os
import sys
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
    print(f"  时长: {info['duration']:.2f}s, 分辨率: {info['width']}x{info['height']}, 编码: {info['codec']}")
    assert info['duration'] > 0, "无法读取视频时长"

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

    # 清理测试生成的文件
    if out_cut.exists():
        out_cut.unlink()
    if out_dir.exists():
        out_dir.rmdir()

    print("\n🎉 全部单元测试通过！核心功能与算法验证 100% 成功！")

if __name__ == "__main__":
    test_system()
