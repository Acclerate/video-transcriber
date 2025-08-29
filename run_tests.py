#!/usr/bin/env python3
"""
测试运行脚本
提供不同类型和级别的测试运行选项
"""

import os
import sys
import argparse
import subprocess
from pathlib import Path


def run_tests(test_type="all", coverage=True, verbose=True, markers=None):
    """运行测试"""
    
    # 基础pytest命令
    cmd = ["python", "-m", "pytest"]
    
    # 添加详细输出
    if verbose:
        cmd.append("-v")
    
    # 添加覆盖率
    if coverage:
        cmd.extend([
            "--cov=core",
            "--cov=api", 
            "--cov=utils",
            "--cov-report=term-missing",
            "--cov-report=html:coverage_html_report"
        ])
    
    # 添加标记过滤
    if markers:
        cmd.extend(["-m", markers])
    
    # 根据测试类型选择测试文件
    if test_type == "unit":
        cmd.append("tests/test_core_*.py")
    elif test_type == "integration":
        cmd.append("tests/test_api.py")
    elif test_type == "fast":
        cmd.extend(["-m", "not slow and not network"])
    elif test_type == "slow":
        cmd.extend(["-m", "slow"])
    elif test_type == "network":
        cmd.extend(["-m", "network"])
    elif test_type == "gpu":
        cmd.extend(["-m", "gpu"])
    else:  # all
        cmd.append("tests/")
    
    print(f"运行命令: {' '.join(cmd)}")
    
    # 设置环境变量
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).parent)
    
    # 执行测试
    try:
        result = subprocess.run(cmd, env=env, check=False)
        return result.returncode
    except KeyboardInterrupt:
        print("\n测试被用户中断")
        return 1
    except Exception as e:
        print(f"测试运行失败: {e}")
        return 1


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="Video Transcriber 测试运行器")
    
    parser.add_argument(
        "--type", 
        choices=["all", "unit", "integration", "fast", "slow", "network", "gpu"],
        default="all",
        help="测试类型"
    )
    
    parser.add_argument(
        "--no-coverage",
        action="store_true",
        help="禁用覆盖率报告"
    )
    
    parser.add_argument(
        "--quiet",
        action="store_true", 
        help="静默模式"
    )
    
    parser.add_argument(
        "--markers",
        help="pytest标记过滤器"
    )
    
    parser.add_argument(
        "--install-deps",
        action="store_true",
        help="安装测试依赖"
    )
    
    args = parser.parse_args()
    
    # 安装测试依赖
    if args.install_deps:
        print("安装测试依赖...")
        subprocess.run([
            "pip", "install", "-r", "requirements.txt",
            "pytest", "pytest-cov", "pytest-asyncio", "pytest-mock"
        ])
    
    # 运行测试
    return run_tests(
        test_type=args.type,
        coverage=not args.no_coverage,
        verbose=not args.quiet,
        markers=args.markers
    )


if __name__ == "__main__":
    sys.exit(main())