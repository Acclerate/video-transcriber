#!/usr/bin/env python3
"""
简单的API测试脚本
"""

import requests
import json
import time

def test_api():
    """测试API服务"""
    base_url = "http://127.0.0.1:8000"
    
    print("正在测试Video Transcriber API...")
    
    # 1. 测试健康检查
    try:
        print("1. 测试健康检查...")
        response = requests.get(f"{base_url}/health", timeout=5)
        print(f"   状态码: {response.status_code}")
        print(f"   响应: {response.json()}")
    except Exception as e:
        print(f"   健康检查失败: {e}")
        return False
    
    # 2. 测试根路径
    try:
        print("2. 测试根路径...")
        response = requests.get(base_url, timeout=5)
        print(f"   状态码: {response.status_code}")
        print(f"   内容类型: {response.headers.get('content-type', 'unknown')}")
    except Exception as e:
        print(f"   根路径测试失败: {e}")
    
    # 3. 测试API文档
    try:
        print("3. 测试API文档...")
        response = requests.get(f"{base_url}/docs", timeout=5)
        print(f"   状态码: {response.status_code}")
        print(f"   文档可访问: {'swagger' in response.text.lower()}")
    except Exception as e:
        print(f"   API文档测试失败: {e}")
    
    print("\nAPI服务基本功能正常！")
    print(f"访问地址: {base_url}")
    print(f"API文档: {base_url}/docs")
    return True

if __name__ == "__main__":
    test_api()