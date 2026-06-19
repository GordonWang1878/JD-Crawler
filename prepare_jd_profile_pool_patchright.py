#!/usr/bin/env python3
"""用 patchright 启动 chromium 让用户依次扫码登录每个 profile.

⚠️ 关键:每个 profile 必须扫一个【不同的京东账号】。
   京东的 PC 频控页(403)是【账号级】封控 —— 同一账号换 profile/换浏览器都绕不开。
   profile 池靠"被封就轮换到下一个 profile"工作,只有当每个 profile 是不同账号时,
   轮换才能真正换到一个没被封的身份。全用同一个账号扫 = 池子形同虚设。
   (实测见 JD_反爬演进史.md Phase 9。当前单 IP 下不同账号正常,暂不需要代理。)

用法:
    python3 prepare_jd_profile_pool_patchright.py        # 默认准备 3 个(= 3 个不同账号)
    python3 prepare_jd_profile_pool_patchright.py 5      # 准备 5 个(= 5 个不同账号)

重扫某个 profile:先删掉它的目录(rm -rf jd_chrome_profile_pool/profile_2),
再跑本脚本 —— 已含 Default 子目录的 profile 会被跳过,不会重复提示。
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
    print(f"  - ⚠️ 每个 profile 扫【不同的京东账号】,共需 {n} 个账号(账号级风控,同账号轮换无效)")
    print("  - 登录完成后回到终端按回车,Chromium 自动关闭进入下一个")
    print()
    input(f"准备好 {n} 个不同的京东账号了吗?按回车开始...")

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

            print(f"  Chromium 已启动,请用【第 {i} 个京东账号(与前面都不同)】扫码登录.")
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
    print("  现在到 web UI 点'开始爬取',crawler 自动 spawn profile_1。")
    print("  某账号被频控时,连续 3 次失败会自动轮转到下一个 profile(= 下一个账号)。")
    return 0


if __name__ == '__main__':
    sys.exit(main())
