#!/usr/bin/env python3
"""
清理undetected-chromedriver缓存
当遇到Chrome版本不匹配时运行此脚本
"""
import os
import shutil
from pathlib import Path


def clear_cache():
    """清理undetected-chromedriver的缓存"""
    print("=" * 60)
    print("清理 undetected-chromedriver 缓存")
    print("=" * 60)

    # 可能的缓存位置
    cache_locations = [
        Path.home() / ".local" / "share" / "undetected_chromedriver",
        Path.home() / "Library" / "Application Support" / "undetected_chromedriver",  # macOS
        Path.home() / "AppData" / "Local" / "undetected_chromedriver",  # Windows
    ]

    cleaned = False

    for cache_path in cache_locations:
        if cache_path.exists():
            print(f"\n找到缓存目录: {cache_path}")
            try:
                # 列出内容
                contents = list(cache_path.glob("*"))
                if contents:
                    print(f"  包含 {len(contents)} 个文件/文件夹")
                    for item in contents:
                        print(f"    - {item.name}")

                    # 删除
                    shutil.rmtree(cache_path)
                    print(f"  ✓ 已删除")
                    cleaned = True
                else:
                    print(f"  目录为空")
            except Exception as e:
                print(f"  ✗ 删除失败: {e}")
        else:
            print(f"\n未找到缓存: {cache_path}")

    print("\n" + "=" * 60)
    if cleaned:
        print("✓ 缓存已清理")
        print("现在可以重新运行 debug_price.py 或 main_with_login.py")
        print("undetected-chromedriver 会自动下载匹配的驱动")
    else:
        print("未找到需要清理的缓存")
    print("=" * 60)


if __name__ == "__main__":
    clear_cache()
