"""
跨 chunk 漂移校正测试
测试 utils/audio/chunking.py 中 merge_results 的漂移校正逻辑
"""

import pytest

from utils.audio.chunking import AudioChunker


def _make_chunk_result(text, start_time, end_time, char_ts=None, vad_segs=None):
    return {
        "text": text,
        "segments": [],
        "language": "zh",
        "confidence": 0.95,
        "processing_time": 1.0,
        "start_time": start_time,
        "end_time": end_time,
        "char_timestamps": char_ts or [],
        "vad_segments": vad_segs or [],
    }


class TestMergeResultsNoDrift:

    def test_single_chunk_passthrough(self):
        chunker = AudioChunker()
        chunk = _make_chunk_result("你好世界", 0.0, 300.0)
        result = chunker.merge_results([chunk], overlap_seconds=1.0)
        assert result["text"] == "你好世界"

    def test_two_chunks_correct_boundary(self):
        """两个 chunk 边界精确对齐，无需校正"""
        chunker = AudioChunker()
        chunk_a = _make_chunk_result(
            "你好",
            0.0, 300.0,
            char_ts=[{"word": "你", "start": 0.0, "end": 0.3}, {"word": "好", "start": 0.3, "end": 0.6}],
        )
        chunk_b = _make_chunk_result(
            "世界",
            299.0, 500.0,
            char_ts=[{"word": "世", "start": 300.0, "end": 300.3}, {"word": "界", "start": 300.3, "end": 300.6}],
        )

        result = chunker.merge_results([chunk_a, chunk_b], overlap_seconds=1.0)

        assert len(result["char_timestamps"]) >= 3  # 去重后保留


class TestCorrectBoundaryDrift:

    def test_detects_and_corrects_drift(self):
        """检测到跨 chunk 漂移并校正"""
        chunker = AudioChunker()

        # chunk 0 结束在 300s，char_ts 最后在 298s
        chunk_a = _make_chunk_result(
            "你好",
            0.0, 300.0,
            char_ts=[
                {"word": "你", "start": 0.0, "end": 0.3},
                {"word": "好", "start": 297.0, "end": 298.0},
            ],
        )
        # chunk 1 的 char_ts 由于漂移偏移了 2s（应该从 300s 开始，实际从 302s 开始）
        chunk_b = _make_chunk_result(
            "世界",
            299.0, 500.0,
            char_ts=[
                {"word": "世", "start": 302.0, "end": 302.3},
                {"word": "界", "start": 302.3, "end": 302.6},
            ],
        )

        result = chunker.merge_results([chunk_a, chunk_b], overlap_seconds=1.0)

        # 校正后，chunk_b 的时间戳应该向左偏移
        ts_after_300 = [ts for ts in result["char_timestamps"] if ts["start"] >= 300.0]
        if ts_after_300:
            # 校正后应接近 300s 而不是 302s
            assert ts_after_300[0]["start"] < 302.0

    def test_no_drift_no_correction(self):
        """无漂移时不做校正"""
        chunker = AudioChunker()

        chunk_a = _make_chunk_result(
            "你好",
            0.0, 300.0,
            char_ts=[{"word": "你", "start": 0.0, "end": 0.5}],
        )
        # 第二个 chunk 的时间戳精确对齐边界，end 在 300.2（偏差 < 0.3s 阈值）
        chunk_b = _make_chunk_result(
            "世界",
            299.0, 500.0,
            char_ts=[{"word": "世", "start": 300.0, "end": 300.2}],
        )

        result = chunker.merge_results([chunk_a, chunk_b], overlap_seconds=1.0)

        ts = result["char_timestamps"]
        # 无漂移校正，时间戳保持不变
        assert any(abs(t["start"] - 300.0) < 0.01 for t in ts)

    def test_empty_timestamps_no_error(self):
        """空 char_timestamps 不报错"""
        chunker = AudioChunker()
        chunk_a = _make_chunk_result("你好", 0.0, 300.0)
        chunk_b = _make_chunk_result("世界", 299.0, 500.0)

        result = chunker.merge_results([chunk_a, chunk_b], overlap_seconds=1.0)
        assert result["char_timestamps"] == []
