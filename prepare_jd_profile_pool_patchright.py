#!/usr/bin/env python3
"""用 patchright 启动 chromium 让用户依次扫码登录每个 profile.

用法:
    python3 prepare_jd_profile_pool_patchright.py        # 默认准备 3 个
    python3 prepare_jd_profile_pool_patchright.py 5      # 准备 5 个
"""
import os
import sys
import time
from patchright.sync_api import sync_playwright

import jd_profile_pool


def main():
    n = 3
    if len(sys.argv) > 1:
        try:
            n = int(sys.argv[1])
        except ValueError:
            print(f"参数无效: {sys.argv[1]}")
            return 1

    os.makedirs(jd_profile_pool.POOL_DIR, exist_ok=True)

    print("=" * 60)
    print(f"  准备 JD profile 池(patchright) — 共 {n} 个")
    print("=" * 60)
    print()
    print("操作步骤:")
    print("  - 每个 profile 会启动一次 patchright Chromium")
    print("  - 在窗口里扫码登录京东(同一账号可登录所有 profile)")
    print("  - 登录完成后回到终端按回车,Chromium 自动关闭进入下一个")
    print()
    input("准备好了吗?按回车开始...")

    with sync_playwright() as p:
        for i in range(1, n + 1):
            profile_dir = jd_profile_pool.profile_dir(i)
            os.makedirs(profile_dir, exist_ok=True)

            # 已经扫码过的跳过
            if os.path.exists(os.path.join(profile_dir, 'Default')):
                print(f"\n✓ profile_{i} 已存在(含 Default 子目录),跳过")
                continue

            print()
            print("=" * 60)
            print(f"  准备 profile_{i} / {n}")
            print("=" * 60)
            print(f"  路径: {profile_dir}")
            print()

            context = p.chromium.launch_persistent_context(
                user_data_dir=profile_dir,
                headless=False,
                channel="chromium",
                no_viewport=True,
                args=[
                    '--no-first-run',
                    '--no-default-browser-check',
                    '--disable-blink-features=AutomationControlled',
                    '--lang=zh-CN',
                ],
            )
            page = context.pages[0] if context.pages else context.new_page()
            try:
                page.goto("https://passport.jd.com/new/login.aspx", timeout=30000)
            except Exception as e:
                print(f"  打开登录页失败: {e}")

            print(f"  Chromium 已启动,请在窗口中扫码登录京东.")
            input("  登录完成后,在终端按回车关闭这个 chromium...")

            try:
                context.close()
            except Exception:
                pass

            print(f"  ✓ profile_{i} 准备完成")
            time.sleep(1)

    print()
    print("=" * 60)
    print(f"  ✓ 全部 {n} 个 profile 准备完成")
    print("=" * 60)
    print("  现在到 web UI 点'开始爬取',crawler 自动 spawn profile_1.")
    print("  风控触发时会自动轮转到 profile_2 → profile_3 ...")
    return 0


if __name__ == '__main__':
    sys.exit(main())
