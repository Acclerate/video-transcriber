"""
测试 FFmpeg 检测功能
"""

import pytest

from utils.ffmpeg import check_ffmpeg_installed, get_ffmpeg_version, get_ffmpeg_install_command


class TestFFmpegDetection:

    def test_check_ffmpeg_installed_returns_bool(self):
        result = check_ffmpeg_installed()
        assert isinstance(result, bool)

    def test_get_ffmpeg_version(self):
        version = get_ffmpeg_version()
        if check_ffmpeg_installed():
            assert version is not None
            assert isinstance(version, str)
        else:
            assert version is None

    def test_get_ffmpeg_install_command(self):
        cmd = get_ffmpeg_install_command()
        assert isinstance(cmd, str)
        assert len(cmd) > 0

    def test_check_dependencies(self):
        from utils.ffmpeg.checker import check_dependencies
        all_ok, missing = check_dependencies()
        assert isinstance(all_ok, bool)
        assert isinstance(missing, list)
