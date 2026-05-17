import re
from pathlib import Path
from typing import List, Optional

from models.schemas import CharTimestamp


class SubtitleSplitHarness:
    def __init__(self):
        source = Path("core/sensevoice_transcriber.py").read_text(encoding="utf-8")
        namespace = {"CharTimestamp": CharTimestamp, "List": List, "Optional": Optional, "re": re}
        exec(_extract_method_source(source, "_is_safe_subtitle_boundary"), namespace)
        exec(_extract_method_source(source, "_subtitle_split_points_from_text"), namespace)
        exec(_extract_method_source(source, "_best_subtitle_split_index"), namespace)
        self._is_safe_subtitle_boundary = namespace["_is_safe_subtitle_boundary"].__get__(self)
        self._subtitle_split_points_from_text = namespace["_subtitle_split_points_from_text"].__get__(self)
        self._best_subtitle_split_index = namespace["_best_subtitle_split_index"].__get__(self)
        self.silence_ranges = []


def _extract_method_source(source: str, method_name: str) -> str:
    marker = f"    def {method_name}"
    start = source.index(marker)
    next_method = source.index("\n    def ", start + len(marker))
    lines = source[start:next_method].splitlines()
    return "\n".join(line[4:] for line in lines)


def test_forced_subtitle_split_does_not_split_ascii_word():
    transcriber = SubtitleSplitHarness()
    text = "大家知道MYCIRCLE语句"
    items = [
        CharTimestamp(word=ch, start=index * 0.5, end=(index + 1) * 0.5)
        for index, ch in enumerate(text)
    ]

    split_index = transcriber._best_subtitle_split_index(
        items,
        min_chars=2,
        max_chars=8,
        force_split=True,
        max_duration=4.0,
    )

    assert split_index > 0
    assert transcriber._is_safe_subtitle_boundary(text, split_index)
