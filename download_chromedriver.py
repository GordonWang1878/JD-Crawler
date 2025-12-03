#!/usr/bin/env python3
"""
下载匹配的 ChromeDriver
自动检测 Chrome 版本并下载对应的 ChromeDriver
"""
import subprocess
import re
import os
import zipfile
import requests
from pathlib import Path


def get_chrome_version():
    """获取本地 Chrome 版本"""
    try:
        # macOS
        result = subprocess.run(
            ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', '--version'],
            capture_output=True,
            text=True
        )
        version_str = result.stdout.strip()
        # 提取版本号，例如 "Google Chrome 142.0.7444.176" -> "142"
        match = re.search(r'(\d+)\.', version_str)
        if match:
            return match.group(1)
    except Exception as e:
        print(f"获取 Chrome 版本失败: {e}")
    return None


def download_chromedriver(version):
    """下载指定版本的 ChromeDriver"""
    print(f"\n正在为 Chrome {version} 下载 ChromeDriver...")

    # ChromeDriver 下载地址
    # 对于 Chrome 115+，使用新的 API
    base_url = "https://googlechromelabs.github.io/chrome-for-testing"

    try:
        # 获取版本信息
        api_url = f"{base_url}/latest-versions-per-milestone-with-downloads.json"
        response = requests.get(api_url, timeout=30)
        response.raise_for_status()
        data = response.json()

        # 查找对应版本
        if version not in data.get('milestones', {}):
            print(f"✗ 未找到 Chrome {version} 对应的 ChromeDriver")
            return None

        milestone = data['milestones'][version]
        downloads = milestone.get('downloads', {}).get('chromedriver', [])

        # 查找 macOS 版本
        mac_download = None
        for item in downloads:
            if 'mac-x64' in item['platform'] or 'mac' in item['platform']:
                mac_download = item
                break

        if not mac_download:
            print(f"✗ 未找到 macOS 版本的 ChromeDriver")
            return None

        download_url = mac_download['url']
        print(f"  下载地址: {download_url}")

        # 下载文件
        print(f"  正在下载...")
        response = requests.get(download_url, timeout=300)
        response.raise_for_status()

        # 保存到临时文件
        zip_path = Path("chromedriver.zip")
        with open(zip_path, 'wb') as f:
            f.write(response.content)
        print(f"  ✓ 下载完成")

        # 解压
        print(f"  正在解压...")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(".")

        # 查找 chromedriver 可执行文件
        chromedriver_path = None
        for root, dirs, files in os.walk("."):
            if "chromedriver" in files:
                chromedriver_path = Path(root) / "chromedriver"
                break

        if chromedriver_path and chromedriver_path.exists():
            # 移动到当前目录
            final_path = Path("chromedriver_142")
            if final_path.exists():
                os.remove(final_path)
            os.rename(chromedriver_path, final_path)

            # 添加执行权限
            os.chmod(final_path, 0o755)

            # 清理
            zip_path.unlink()
            # 删除解压后的目录
            import shutil
            for item in Path(".").glob("chromedriver-*"):
                if item.is_dir():
                    shutil.rmtree(item)

            print(f"  ✓ ChromeDriver 已保存到: {final_path.absolute()}")
            return str(final_path.absolute())
        else:
            print(f"  ✗ 解压后未找到 chromedriver")
            return None

    except Exception as e:
        print(f"✗ 下载失败: {e}")
        import traceback
        traceback.print_exc()
        return None


def main():
    print("=" * 60)
    print("ChromeDriver 下载工具")
    print("=" * 60)

    # 获取 Chrome 版本
    version = get_chrome_version()
    if not version:
        print("\n✗ 无法获取 Chrome 版本")
        print("请确保已安装 Google Chrome")
        return

    print(f"\n检测到 Chrome 版本: {version}")

    # 下载 ChromeDriver
    driver_path = download_chromedriver(version)

    if driver_path:
        print("\n" + "=" * 60)
        print("✅ 成功！")
        print("=" * 60)
        print(f"ChromeDriver 已下载到: {driver_path}")
        print("\n现在可以运行爬虫了：")
        print("  python3 debug_price.py")
        print("  python3 main_with_login.py")
    else:
        print("\n" + "=" * 60)
        print("❌ 下载失败")
        print("=" * 60)


if __name__ == "__main__":
    main()
