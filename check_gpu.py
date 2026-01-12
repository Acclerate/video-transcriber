"""
GPU 诊断脚本
检查 PyTorch CUDA 和 FunASR GPU 支持状态
"""

import sys

def check_pytorch_cuda():
    """检查 PyTorch CUDA 支持"""
    print("=" * 60)
    print("1. 检查 PyTorch CUDA 支持")
    print("=" * 60)

    try:
        import torch
        print(f"✓ PyTorch 版本: {torch.__version__}")
        print(f"✓ CUDA 可用: {torch.cuda.is_available()}")

        if torch.cuda.is_available():
            print(f"✓ CUDA 版本: {torch.version.cuda}")
            print(f"✓ GPU 数量: {torch.cuda.device_count()}")
            for i in range(torch.cuda.device_count()):
                print(f"  - GPU {i}: {torch.cuda.get_device_name(i)}")
                print(f"    显存总量: {torch.cuda.get_device_properties(i).total_memory / 1024**3:.2f} GB")
            print(f"✓ 当前设备: {torch.cuda.current_device()}")
            return True
        else:
            print("✗ CUDA 不可用")
            print("\n解决方案:")
            print("  1. 安装带 CUDA 支持的 PyTorch:")
            print("     pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu118")
            print("  2. 或访问: https://pytorch.org/get-started/locally/")
            return False
    except ImportError:
        print("✗ PyTorch 未安装")
        print("\n解决方案: pip install torch torchaudio")
        return False


def check_funasr_gpu():
    """检查 FunASR GPU 支持"""
    print("\n" + "=" * 60)
    print("2. 检查 FunASR GPU 支持")
    print("=" * 60)

    try:
        from funasr import AutoModel
        print("✓ FunASR 已安装")

        import torch
        if torch.cuda.is_available():
            print("✓ CUDA 环境 OK，FunASR 应该可以使用 GPU")
            return True
        else:
            print("✗ CUDA 不可用，FunASR 无法使用 GPU")
            return False
    except ImportError:
        print("✗ FunASR 未安装")
        print("\n解决方案: pip install funasr modelscope")
        return False


def test_gpu_memory():
    """测试 GPU 内存分配"""
    print("\n" + "=" * 60)
    print("3. 测试 GPU 内存分配")
    print("=" * 60)

    try:
        import torch
        if not torch.cuda.is_available():
            print("✗ CUDA 不可用，跳过测试")
            return False

        # 尝试在 GPU 上创建一个张量
        print("尝试在 GPU 上创建张量...")
        device = torch.device("cuda:0")
        x = torch.randn(1000, 1000, device=device)
        print(f"✓ 成功在 GPU 上创建张量: {x.device}")

        # 检查显存使用
        allocated = torch.cuda.memory_allocated(0) / 1024**2
        cached = torch.cuda.memory_reserved(0) / 1024**2
        print(f"✓ 已分配显存: {allocated:.2f} MB")
        print(f"✓ 已缓存显存: {cached:.2f} MB")

        # 清理
        del x
        torch.cuda.empty_cache()
        print("✓ GPU 显存已清理")
        return True
    except Exception as e:
        print(f"✗ GPU 测试失败: {e}")
        return False


def test_sensevoice_gpu():
    """测试 SenseVoice 模型 GPU 使用"""
    print("\n" + "=" * 60)
    print("4. 测试 SenseVoice GPU 使用")
    print("=" * 60)

    try:
        from funasr import AutoModel
        import torch

        if not torch.cuda.is_available():
            print("✗ CUDA 不可用，跳过测试")
            return False

        print("尝试加载 SenseVoice 模型到 GPU...")
        import os
        os.environ['MODELSCOPE_CACHE'] = './models_cache'

        model = AutoModel(
            model="iic/SenseVoiceSmall",
            device="cuda:0",
            cache_dir="./models_cache"
        )

        print(f"✓ 模型加载成功")
        print(f"✓ 使用设备: {getattr(model, 'device', '未知')}")

        # 检查 GPU 显存
        allocated = torch.cuda.memory_allocated(0) / 1024**2
        print(f"✓ 模型占用显存: {allocated:.2f} MB")

        if allocated > 0:
            print("✓ GPU 正在工作！")
        else:
            print("⚠ GPU 显存占用为 0，可能模型在 CPU 上运行")

        return True
    except Exception as e:
        print(f"✗ SenseVoice GPU 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    print("\n" + "=" * 60)
    print("GPU 诊断工具")
    print("=" * 60)

    results = []

    # 运行所有检查
    results.append(("PyTorch CUDA", check_pytorch_cuda()))
    results.append(("FunASR GPU", check_funasr_gpu()))
    results.append(("GPU 内存", test_gpu_memory()))
    results.append(("SenseVoice GPU", test_sensevoice_gpu()))

    # 总结
    print("\n" + "=" * 60)
    print("诊断总结")
    print("=" * 60)

    for name, passed in results:
        status = "✓ 通过" if passed else "✗ 失败"
        print(f"{status} - {name}")

    all_passed = all(r[1] for r in results)
    if all_passed:
        print("\n✓ 所有检查通过，GPU 应该可以正常使用！")
    else:
        print("\n✗ 部分检查失败，请按照上面的提示解决问题")


if __name__ == "__main__":
    main()
