#!/usr/bin/env python3
"""京东价格爬虫 — Patchright 版.

为什么用 Patchright:
- 2026 年 5 月京东升级了反爬,直接识别 selenium/chromedriver,attach 模式也失效
- Patchright 是 Playwright 的反检测 fork,从底层修补:
  * navigator.webdriver / Runtime.enable 等 CDP 命令的暴露点
  * chromedriver 启动参数的指纹
  * 自动注入的 JS 函数(cdc_xxx)
- 用 launch_persistent_context 直接接管 profile 目录,不走 CDP attach

对外接口与 JDCrawlerViaSearch 保持一致:
    __init__, login, get_price_via_search, warmup, random_walk,
    is_session_valid, restart_browser, close, is_logged_in (property)
    + switch_to_next_profile, current_profile_id, available_profiles
"""
import warnings
warnings.filterwarnings('ignore', message='urllib3 v2 only supports OpenSSL 1.1.1+')

import os
import re
import time
import random
from typing import Optional, List

from patchright.sync_api import sync_playwright, BrowserContext, Page

import jd_profile_pool


CDP_PORT = jd_profile_pool.CDP_PORT  # 兼容 app.py 旧 import,实际 patchright 不用 9222


def _is_chrome_running_on_cdp_port(port: int = CDP_PORT) -> bool:
    """兼容旧 app.py 预检调用 — patchright 自己管 chromium,这个总返回 True"""
    return True


def _profile_pool_empty_msg() -> str:
    return (
        "\n" + "=" * 60 + "\n"
        "❌ JD profile 池为空!\n\n"
        "请先在终端运行(只需一次,每个 profile 扫码登录京东):\n"
        "    bash prepare_jd_profile_pool_patchright.sh 3\n"
        + "=" * 60 + "\n"
    )


class JDCrawlerViaSearch:
    """京东爬虫(patchright 版).类名沿用以兼容 app.py."""

    def __init__(self, headless: bool = False, cookies_file: str = "jd_cookies.pkl"):
        # cookies_file 参数保留是为了兼容 app.py 调用,实际不用 — patchright 用 profile 目录管理
        self.headless = headless
        self.cookies_file = cookies_file
        self.is_logged_in = False
        # Patchright 上下文
        self._playwright = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        # profile 池状态
        self.available_profiles = jd_profile_pool.list_available_profiles()
        self.current_profile_id: Optional[int] = None
        if not self.available_profiles:
            raise RuntimeError(_profile_pool_empty_msg())
        # 启动第一个 profile
        self._launch_profile(self.available_profiles[0])

    # ============ Patchright 启停 ============

    def _launch_profile(self, profile_id: int):
        """用 patchright 的 launch_persistent_context 启动指定 profile."""
        profile_dir = jd_profile_pool.profile_dir(profile_id)
        if not os.path.isdir(profile_dir):
            raise RuntimeError(f"profile_{profile_id} 不存在: {profile_dir}")

        print(f"  [patchright] 启动 profile_{profile_id} ({profile_dir})...")
        t0 = time.time()

        if self._playwright is None:
            self._playwright = sync_playwright().start()

        # launch_persistent_context 直接接管 user-data-dir,等价于
        # "用这个 profile 目录启动一个 chromium 实例",且 patchright 已经修补反检测
        self._context = self._playwright.chromium.launch_persistent_context(
            user_data_dir=profile_dir,
            headless=self.headless,
            # patchright 推荐的 stealth 设置:
            channel="chromium",  # 用 patchright 自带的 Chromium for Testing
            no_viewport=True,
            args=[
                '--no-first-run',
                '--no-default-browser-check',
                '--disable-blink-features=AutomationControlled',
                '--lang=zh-CN',
            ],
        )

        # 用 context 自带的 page(或新建一个)
        pages = self._context.pages
        self._page = pages[0] if pages else self._context.new_page()
        self.current_profile_id = profile_id
        print(f"  [patchright] ✓ profile_{profile_id} 已启动 ({time.time()-t0:.1f}秒)")

    def _close_context(self):
        """关闭当前 context(profile),保留 playwright 进程."""
        if self._page:
            try:
                self._page.close()
            except Exception:
                pass
            self._page = None
        if self._context:
            try:
                self._context.close()
            except Exception:
                pass
            self._context = None
        # 短暂等让 OS 释放 profile lock
        time.sleep(2)

    # ============ Login ============

    def login(self, auto_login: bool = True):
        """检测当前 profile 是否已登录京东.profile 已扫码的话直接 True."""
        if self._is_logged_in_now():
            print("  ✓ profile_{} 已登录京东".format(self.current_profile_id))
            self.is_logged_in = True
            return

        # 未登录 — 提示用户
        print("\n" + "=" * 60)
        print(f"  profile_{self.current_profile_id} 未检测到登录态")
        print("=" * 60)
        print("请在 chromium 窗口中扫码登录京东,然后等待自动检测.")

        if not auto_login:
            self.is_logged_in = False
            return

        max_wait = 180
        check_interval = 3
        waited = 0
        while waited < max_wait:
            time.sleep(check_interval)
            waited += check_interval
            if self._is_logged_in_now():
                print(f"\n  ✓ 检测到登录成功 (等了 {waited} 秒)")
                self.is_logged_in = True
                return
            if waited % 15 == 0:
                print(f">>> 等待登录中... ({waited}/{max_wait}秒)")

        print(f"\n  ✗ 登录超时(等了 {max_wait} 秒)")
        self.is_logged_in = False

    def _is_logged_in_now(self) -> bool:
        """访问需要登录的页面,判断是否已登录."""
        try:
            self._page.goto("https://order.jd.com/center/list.action",
                            wait_until="domcontentloaded", timeout=15000)
            time.sleep(1.5)
            cur = (self._page.url or '').lower()
            title = self._page.title() or ''
            return '登录' not in title and 'login' not in cur and 'passport' not in cur
        except Exception as e:
            print(f"  登录态检测失败: {e}")
            return False

    # ============ Warmup ============

    def warmup(self):
        """登录后浏览首页 + 滚动,模拟正常用户."""
        print("  热身：浏览首页...")
        try:
            self._page.goto("https://www.jd.com", wait_until="domcontentloaded", timeout=15000)
            time.sleep(random.uniform(3, 5))
            self._smooth_scroll(0.3)
            time.sleep(random.uniform(1, 2))
            self._smooth_scroll(0.7)
            time.sleep(random.uniform(1, 2))
            self._smooth_scroll(0.0)
            time.sleep(random.uniform(2, 3))
            print("  ✓ 热身完成")
        except Exception as e:
            print(f"  热身出错(忽略): {e}")

    def _smooth_scroll(self, ratio: float):
        """平滑滚动到页面高度的 ratio 位置(0.0=顶, 1.0=底)."""
        try:
            self._page.evaluate(
                f"""() => {{
                    const h = document.body.scrollHeight;
                    window.scrollTo({{top: h * {ratio}, behavior: 'smooth'}});
                }}"""
            )
        except Exception:
            pass

    # ============ Random Walk ============

    def random_walk(self) -> str:
        """随机游走 — 在主商品爬取之间插入"伪浏览"."""
        candidates = [
            ('首页', 'https://www.jd.com'),
            ('购物车', 'https://cart.jd.com/cart_index/'),
            ('我的京东', 'https://home.jd.com/'),
        ]
        label, target = random.choice(candidates)
        try:
            self._page.goto(target, wait_until="domcontentloaded", timeout=15000)
            time.sleep(random.uniform(3.0, 5.0))
            self._smooth_scroll(0.4)
            time.sleep(random.uniform(2.0, 3.5))
            self._smooth_scroll(0.0)
            time.sleep(random.uniform(1.0, 2.0))
        except Exception as e:
            print(f"  随机游走出错(忽略): {e}")
        return label

    # ============ Get Price (核心) ============

    def get_price_via_search(self, product_id: str) -> Optional[dict]:
        """访问商品页提取价格."""
        if not self.is_logged_in:
            print("  ✗ 未登录")
            return None

        product_url = f"https://item.jd.com/{product_id}.html"

        try:
            print(f"  访问商品页 {product_id}...")
            self._page.goto(product_url, wait_until="domcontentloaded", timeout=20000)

            # 模拟真人浏览:等加载 → 平滑滚动到底 → 停留 → 滚回中部
            time.sleep(random.uniform(2.0, 3.5))
            steps = random.randint(4, 5)
            for i in range(1, steps + 1):
                self._smooth_scroll(i / steps)
                time.sleep(random.uniform(1.2, 2.0))
            time.sleep(random.uniform(2.0, 3.5))
            self._smooth_scroll(random.uniform(0.3, 0.5))
            time.sleep(random.uniform(0.8, 1.5))

            current_url = self._page.url

            def _diag():
                try:
                    src_len = len(self._page.content() or '')
                except Exception:
                    src_len = -1
                try:
                    title = (self._page.title() or '')[:50]
                except Exception:
                    title = '?'
                return f'url="{current_url[:90]}" title="{title}" src_len={src_len}'

            # 风控判定
            if "risk_handler" in current_url or "verify" in current_url.lower():
                print(f"  ⚠️ 触发反爬验证页 | {_diag()}")
                return {'original': 'blocked', 'promo': 'blocked', '_diag': _diag()}

            if "error" in current_url.lower() and "403" in current_url:
                print(f"  ⚠️ 403 错误 | {_diag()}")
                return {'original': 'forbidden', 'promo': 'forbidden', '_diag': _diag()}

            if current_url.startswith("https://www.jd.com/?") or current_url == "https://www.jd.com/":
                if current_url == "https://www.jd.com/?d":
                    print(f"  ✗ 商品不存在")
                    return {'original': 'not_found', 'promo': 'not_found'}
                print(f"  ⚠️ 被重定向到首页 | {_diag()}")
                return {'original': 'blocked', 'promo': 'blocked', '_diag': _diag()}

            # 检查下架
            try:
                page_text = self._page.content()
            except Exception:
                page_text = ''
            unavailable_keywords = [
                "该商品已下柜", "商品已下架", "该商品已下架",
                "抱歉，该商品已下柜", "欢迎挑选其他商品", "很抱歉，该商品已售馨或下架",
            ]
            for keyword in unavailable_keywords:
                if keyword in page_text:
                    print(f"  ⚠️ 商品已下架")
                    return {'original': 'unavailable', 'promo': 'unavailable'}

            # 提取价格
            return self._extract_price()

        except Exception as e:
            print(f"  ✗ 错误: {e}")
            return None

    def _extract_price(self) -> Optional[dict]:
        """从商品页提取价格 — 完整移植 selenium 老版的多选择器逻辑.
        京东 2025/2026 新版页面:
        - .product-price--value: 当前售价(促销价)
        - .product-price--gray: 灰色划线原价
        - 备用容器若干
        """
        try:
            time.sleep(1.0)
            prices = {'original': None, 'promo': None}

            js_script = r"""
            () => {
                var result = {main: null, gray: null, fallback: null};

                // 1. 主价格: product-price--value (当前售价/促销价)
                var mainEl = document.querySelector('.product-price--value');
                if (mainEl) {
                    var m = mainEl.textContent.trim().match(/([\.\d]+)/);
                    if (m) result.main = parseFloat(m[1]);
                }

                // 2. 灰色价格: product-price--gray (原价/日常价)
                var grayEl = document.querySelector('.product-price--gray');
                if (grayEl) {
                    var g = grayEl.textContent.trim().match(/[¥￥]\s*([\.\d]+)/);
                    if (g) result.gray = parseFloat(g[1]);
                }

                // 3. 备用: calculator-product-info 内的 product-price
                if (!result.main) {
                    var calcEl = document.querySelector('.calculator-product-info .product-price');
                    if (calcEl) {
                        var c = calcEl.textContent.trim().match(/[¥￥]\s*([\.\d]+)/);
                        if (c) result.fallback = parseFloat(c[1]);
                    }
                }

                // 4. 再备用: 页面上第一个 product-price 容器
                if (!result.main && !result.fallback) {
                    var ppEl = document.querySelector('.product-price');
                    if (ppEl) {
                        var p = ppEl.textContent.match(/[¥￥]\s*([\.\d]+)/);
                        if (p) result.fallback = parseFloat(p[1]);
                    }
                }

                // 5. 旧版兼容: .p-price .price
                if (!result.main && !result.fallback) {
                    var oldEl = document.querySelector('.p-price .price');
                    if (oldEl) {
                        var o = oldEl.textContent.trim().match(/([\.\d]+)/);
                        if (o) result.fallback = parseFloat(o[1]);
                    }
                }

                return result;
            }
            """
            data = self._page.evaluate(js_script)
            if not data:
                print("  未找到价格元素")
                return None

            main_price = data.get('main')
            gray_price = data.get('gray')
            fallback_price = data.get('fallback')

            print(f"  价格数据: 主价={main_price}, 灰色={gray_price}, 备用={fallback_price}")

            current_price = main_price or fallback_price

            if current_price:
                if gray_price and gray_price > current_price:
                    prices['original'] = gray_price
                    prices['promo'] = current_price
                    print(f"  ✓ 原价: ¥{gray_price}, 当前价: ¥{current_price}")
                else:
                    prices['original'] = current_price
                    prices['promo'] = current_price
                    print(f"  ✓ 价格: ¥{current_price} (无促销)")
                return prices
            elif gray_price:
                prices['original'] = gray_price
                prices['promo'] = gray_price
                print(f"  ✓ 仅灰色价格: ¥{gray_price}")
                return prices

            print("  未找到有效价格")
            return None

        except Exception as e:
            print(f"  提取价格失败: {e}")
            import traceback
            traceback.print_exc()
            return None

    # ============ Session 管理 ============

    def is_session_valid(self) -> bool:
        """检查 context/page 是否还活着."""
        if not self._page or not self._context:
            return False
        try:
            _ = self._page.url
            return True
        except Exception:
            return False

    def restart_browser(self) -> bool:
        """重启当前 profile 的 chromium."""
        print("\n  ⚠️ 重启 chromium...")
        cur = self.current_profile_id
        self._close_context()
        try:
            self._launch_profile(cur)
            self.login(auto_login=False)
            if self.is_logged_in:
                print("  ✓ 重启成功\n")
                return True
        except Exception as e:
            print(f"  ✗ 重启失败: {e}")
        return False

    def switch_to_next_profile(self) -> Optional[int]:
        """切换到下一个 profile."""
        if not self.available_profiles:
            return None

        if self.current_profile_id is None:
            next_id = self.available_profiles[0]
        else:
            try:
                cur_idx = self.available_profiles.index(self.current_profile_id)
                next_idx = cur_idx + 1
                if next_idx >= len(self.available_profiles):
                    print(f"  ✗ profile 池耗尽")
                    return None
                next_id = self.available_profiles[next_idx]
            except ValueError:
                next_id = self.available_profiles[0]

        print(f"  切换到 profile_{next_id}...")
        self._close_context()
        try:
            self._launch_profile(next_id)
        except Exception as e:
            print(f"  ✗ 切换失败: {e}")
            return None

        # 检测登录态(profile 已扫码,应该自动登录)
        self.login(auto_login=False)
        if not self.is_logged_in:
            print(f"  ⚠ profile_{next_id} 未登录")
            return None
        return next_id

    def close(self):
        """关闭所有资源."""
        self._close_context()
        if self._playwright:
            try:
                self._playwright.stop()
            except Exception:
                pass
            self._playwright = None

    # 兼容旧 selenium API:让 app.py 里 `crawler.driver.xxx` 的调用继续工作
    @property
    def driver(self):
        return _DriverShim(self._page)


class _DriverShim:
    """模拟 selenium driver 的最少 API,让 app.py 旧代码无需大改."""

    def __init__(self, page: Page):
        self._page = page

    @property
    def current_url(self) -> str:
        try:
            return self._page.url or ''
        except Exception:
            return ''

    @property
    def title(self) -> str:
        try:
            return self._page.title() or ''
        except Exception:
            return ''

    def get(self, url: str):
        """selenium driver.get(url) → patchright page.goto(url)"""
        try:
            self._page.goto(url, wait_until="domcontentloaded", timeout=15000)
        except Exception as e:
            print(f"  driver.get 失败: {e}")

    def execute_script(self, script: str):
        """selenium execute_script → patchright page.evaluate.
        注意 selenium 的 script 是 'window.xxx;',patchright 需要 'arrow fn' 形式.
        我们用包装兼容大部分简单脚本.
        """
        try:
            # 简单脚本(如 'window.scrollTo(0, 500);')包成 arrow fn
            wrapped = f"() => {{ {script} }}"
            return self._page.evaluate(wrapped)
        except Exception:
            try:
                # 如果包装失败,试 raw 调用
                return self._page.evaluate(script)
            except Exception as e:
                print(f"  execute_script 失败: {e}")
                return None
