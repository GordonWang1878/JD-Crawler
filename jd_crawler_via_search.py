#!/usr/bin/env python3
"""
通过搜索访问商品 - 更像真人的行为
不直接访问商品链接，而是先搜索，再点击进入
"""
import warnings
# 抑制 urllib3 的 OpenSSL 警告
warnings.filterwarnings('ignore', message='urllib3 v2 only supports OpenSSL 1.1.1+')

from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
import subprocess
import time
import random
import re
import os
import pickle
from typing import Optional

import jd_profile_pool

# CDP attach 模式 + profile 池自动轮转
# - 每个 profile 是一个独立 Chrome user-data-dir,在京东那里是独立"身份"
# - 启动时 spawn profile_1 的 Chrome,连续 3 次失败时自动切到 profile_2/3/...
CDP_PORT = jd_profile_pool.CDP_PORT
CDP_ADDR = f'127.0.0.1:{CDP_PORT}'


def _is_chrome_running_on_cdp_port(port: int = CDP_PORT) -> bool:
    """兼容旧调用 — 现在转发到 profile_pool.is_cdp_port_listening"""
    return jd_profile_pool.is_cdp_port_listening(port)


def _profile_pool_empty_msg() -> str:
    return (
        f"\n{'='*60}\n"
        f"❌ JD profile 池为空!\n\n"
        f"请先在终端运行(只需一次):\n"
        f"    bash prepare_jd_profile_pool.sh 3\n\n"
        f"按提示依次给每个 profile 扫码登录京东.\n"
        f"准备完成后再到 web UI 点'开始爬取'.\n"
        f"{'='*60}\n"
    )


def _detect_chrome_version() -> Optional[int]:
    """自动检测本机 Chrome 主版本号"""
    paths = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
    ]
    for path in paths:
        if os.path.exists(path):
            try:
                out = subprocess.check_output([path, "--version"], stderr=subprocess.DEVNULL, text=True)
                match = re.search(r"(\d+)\.", out)
                if match:
                    return int(match.group(1))
            except Exception:
                continue
    return None


class JDCrawlerViaSearch:
    """通过搜索访问商品的京东爬虫"""

    def __init__(self, headless: bool = False, cookies_file: str = "jd_cookies.pkl"):
        self.headless = headless
        self.cookies_file = cookies_file
        self.driver = None
        self.is_logged_in = False
        # profile 池状态(可选 — 也支持"用户手动启动 Chrome,crawler 仅 attach"模式)
        self.available_profiles = jd_profile_pool.list_available_profiles()
        self.current_profile_id: Optional[int] = None
        self._init_driver()

    def _init_driver(self):
        """CDP attach 模式 — 连接到 9222 端口上的 Chrome.

        两种工作模式:
        1. profile 池模式(自动轮转): pool 里有 profile_1..N,crawler 自动 spawn + 风控时切换
        2. 单 Chrome 模式: 用户手动启动 Chrome(比如 launch_chrome_real_profile.sh),
                           crawler 只 attach,不轮转
        """
        if _is_chrome_running_on_cdp_port(CDP_PORT):
            # 端口已有 Chrome 在跑 — 直接 attach,不管 profile 池
            if self.available_profiles:
                if self.current_profile_id is None:
                    self.current_profile_id = self.available_profiles[0]
                print(f"  CDP 端口已有 Chrome 在跑,直接 attach (假定 profile_{self.current_profile_id})")
            else:
                # 单 Chrome 模式:profile 池为空,但端口有 Chrome
                print(f"  CDP 端口已有 Chrome 在跑,直接 attach (单 Chrome 模式,无 profile 轮转)")
        elif self.available_profiles:
            # profile 池模式:自动 spawn profile_1
            first_profile = self.available_profiles[0]
            print(f"  CDP 端口空闲,自动启动 profile_{first_profile}...")
            jd_profile_pool.ensure_chrome_running(first_profile)
            self.current_profile_id = first_profile
        else:
            # 端口空闲 且 profile 池为空 — 用户需要先手动启动 Chrome
            raise RuntimeError(
                f"\n{'='*60}\n"
                f"❌ CDP 端口 {CDP_PORT} 没有 Chrome 在跑,且 profile 池为空.\n\n"
                f"请二选一:\n"
                f"  方案 B(用日常 Chrome profile,推荐当前测试):\n"
                f"    1. 完全关闭日常 Chrome (Command+Q)\n"
                f"    2. 运行: bash launch_chrome_real_profile.sh\n"
                f"  方案 profile 池(隔离的独立 profile):\n"
                f"    bash prepare_jd_profile_pool.sh 3\n"
                f"{'='*60}\n"
            )

        print(f"  连接到 Chrome (CDP {CDP_ADDR})...")
        t0 = time.time()
        try:
            opts = ChromeOptions()
            opts.add_experimental_option("debuggerAddress", CDP_ADDR)
            self.driver = webdriver.Chrome(options=opts, service=ChromeService())
            self.driver.implicitly_wait(5)
            print(f"  ✓ 已连接到 Chrome ({time.time()-t0:.1f}秒)")
        except Exception as e:
            print(f"  ✗ CDP attach 失败: {e}")
            raise

    def switch_to_next_profile(self) -> Optional[int]:
        """切换到下一个 profile.
        返回新 profile id,如果没有更多 profile 可用 / profile 池为空 返回 None.
        """
        if not self.available_profiles:
            # 单 Chrome 模式:无 profile 池,无法轮转
            return None
        if self.current_profile_id is None:
            next_id = self.available_profiles[0]
        else:
            # 找下一个 id
            try:
                cur_idx = self.available_profiles.index(self.current_profile_id)
                next_idx = cur_idx + 1
                if next_idx >= len(self.available_profiles):
                    print(f"  ✗ profile 池已耗尽(用到 profile_{self.current_profile_id})")
                    return None
                next_id = self.available_profiles[next_idx]
            except ValueError:
                next_id = self.available_profiles[0]

        # 解除 selenium 引用
        self.driver = None
        self.is_logged_in = False

        # 切 profile
        try:
            jd_profile_pool.switch_to_profile(next_id)
        except Exception as e:
            print(f"  ✗ 切换 profile 失败: {e}")
            return None

        self.current_profile_id = next_id

        # 重新 attach
        try:
            opts = ChromeOptions()
            opts.add_experimental_option("debuggerAddress", CDP_ADDR)
            self.driver = webdriver.Chrome(options=opts, service=ChromeService())
            self.driver.implicitly_wait(5)
            print(f"  ✓ attach 到 profile_{next_id}")
        except Exception as e:
            print(f"  ✗ attach 失败: {e}")
            return None

        # 检测登录态(profile 已扫码,应该自动登录)
        self.login(auto_login=False)
        if not self.is_logged_in:
            print(f"  ⚠ profile_{next_id} 未检测到登录态")
            return None

        return next_id

    def load_cookies(self) -> bool:
        """加载cookies"""
        if not os.path.exists(self.cookies_file):
            return False
        try:
            self.driver.get("https://www.jd.com")
            time.sleep(2)
            with open(self.cookies_file, 'rb') as f:
                cookies = pickle.load(f)
            for cookie in cookies:
                cookie.pop('sameSite', None)
                cookie.pop('expiry', None)
                try:
                    self.driver.add_cookie(cookie)
                except:
                    continue
            return True
        except Exception as e:
            print(f"✗ 加载cookies失败: {e}")
            return False

    def login(self, auto_login: bool = True):
        """CDP attach 模式:Chrome 是用户启动的,登录态由用户在 Chrome 里手动管理.
        本方法只做'检测登录态' — 不主动打开登录页(避免打扰用户的 Chrome 操作).

        Args:
            auto_login: 检测到未登录时,是否等待用户在 Chrome 里手动登录(最多 3 分钟)
        """
        # 1. 检测当前是否已登录 — 访问需要登录的页面,看是否被踢到 login
        if self._is_logged_in_now():
            print("✓ Chrome 已登录京东")
            self.is_logged_in = True
            return

        # 2. 未登录 — 提示用户在 Chrome 里手动扫码
        print("\n" + "=" * 60)
        print("Chrome 中未检测到京东登录态")
        print("=" * 60)
        print("请在已打开的 Chrome 窗口中扫码登录京东.")
        print("登录成功后,本程序会自动检测到并继续爬取.")
        print("=" * 60)

        if not auto_login:
            self.is_logged_in = False
            return

        # 3. 等待用户在 Chrome 中完成登录(最多 3 分钟)
        max_wait = 180
        check_interval = 3
        waited = 0
        while waited < max_wait:
            time.sleep(check_interval)
            waited += check_interval
            if self._is_logged_in_now():
                print(f"\n✓ 检测到登录成功 (等待了 {waited} 秒)")
                self.is_logged_in = True
                return
            if waited % 15 == 0:
                print(f">>> 等待登录中... ({waited}/{max_wait}秒)")

        print(f"\n✗ 登录超时(等待了 {max_wait} 秒).请确认 Chrome 已登录后重试.")
        self.is_logged_in = False

    def _is_logged_in_now(self) -> bool:
        """快速检测当前 Chrome 是否已登录京东."""
        try:
            self.driver.get("https://order.jd.com/center/list.action")
            time.sleep(2)
            cur = (self.driver.current_url or '').lower()
            title = self.driver.title or ''
            return '登录' not in title and 'login' not in cur and 'passport' not in cur
        except Exception:
            return False

    def _save_cookies(self):
        """保存cookies到文件"""
        try:
            cookies = self.driver.get_cookies()
            with open(self.cookies_file, 'wb') as f:
                pickle.dump(cookies, f)
            return True
        except Exception as e:
            print(f"✗ 保存cookies失败: {e}")
            return False

    def warmup(self):
        """登录后简单浏览首页 — 不做搜索、不访问具体商品,
        避免在搜索域累积风控分(京东新版风控会因为高频搜索同一词触发"搜索操作过于频繁")."""
        print("  热身：浏览首页...")
        try:
            # 仅访问首页 + 滚动模拟人类行为
            self.driver.get("https://www.jd.com")
            time.sleep(random.uniform(3, 5))
            self.driver.execute_script("window.scrollTo(0, 600);")
            time.sleep(random.uniform(1, 2))
            self.driver.execute_script("window.scrollTo(0, 1200);")
            time.sleep(random.uniform(1, 2))
            self.driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(random.uniform(2, 3))

            print("  ✓ 热身完成")
        except Exception as e:
            print(f"  热身出错（忽略）: {e}")

    def random_walk(self) -> str:
        """随机游走:在主商品爬取之间插入一次"伪浏览",制造行为多样性
        访问首页/购物车/我的京东之一,滚动一下,模拟真人在商品页之间切换的行为.
        返回此次访问的页面描述,用于日志.
        """
        # 池子里只放"已登录用户访问不会触发风控"的页面 — 不要触碰 search.jd.com
        candidates = [
            ('首页', 'https://www.jd.com'),
            ('购物车', 'https://cart.jd.com/cart_index/'),
            ('我的京东', 'https://home.jd.com/'),
        ]
        label, target = random.choice(candidates)
        try:
            self.driver.get(target)
            time.sleep(random.uniform(3.0, 5.0))
            # 滚动一下模拟阅读
            self.driver.execute_script("window.scrollTo({top: 600, behavior: 'smooth'});")
            time.sleep(random.uniform(2.0, 3.5))
            self.driver.execute_script("window.scrollTo({top: 0, behavior: 'smooth'});")
            time.sleep(random.uniform(1.0, 2.0))
        except Exception as e:
            print(f"  随机游走出错(忽略): {e}")
        return label

    def get_price_via_search(self, product_id: str) -> Optional[float]:
        """
        获取商品价格（直接访问，避免搜索触发验证）

        Args:
            product_id: 商品ID，例如 "100140584252"
        """
        if not self.is_logged_in:
            print("  ✗ 未登录")
            return None

        try:
            # 直接构造商品URL
            product_url = f"https://item.jd.com/{product_id}.html"

            print(f"  直接访问商品页...")
            self.driver.get(product_url)

            # 模拟真人浏览:平滑滚动到底 + 中间停留 + 滚回中部
            # 总耗时 10-15 秒,显著降低"机器人式快进快出"的可疑度
            try:
                # 1. 等待页面加载
                time.sleep(random.uniform(2.0, 3.5))

                # 2. 平滑滚动到底,分 4-5 段,每段间停顿(模拟阅读)
                try:
                    scroll_height = self.driver.execute_script("return document.body.scrollHeight;") or 3000
                except Exception:
                    scroll_height = 3000
                steps = random.randint(4, 5)
                for i in range(1, steps + 1):
                    target_y = int(scroll_height * i / steps)
                    self.driver.execute_script(
                        f"window.scrollTo({{top: {target_y}, behavior: 'smooth'}});"
                    )
                    time.sleep(random.uniform(1.2, 2.0))

                # 3. 底部停留(模拟看评论/详情参数)
                time.sleep(random.uniform(2.0, 3.5))

                # 4. 滚回中部(模拟上下浏览查找信息)
                mid_y = int(scroll_height * random.uniform(0.3, 0.5))
                self.driver.execute_script(
                    f"window.scrollTo({{top: {mid_y}, behavior: 'smooth'}});"
                )
                time.sleep(random.uniform(0.8, 1.5))
            except Exception as e:
                # 滚动失败不阻断主流程
                print(f"  (滚动模拟出错,忽略: {e})")

            # 检查当前URL - 精确区分不同的失败类型
            current_url = self.driver.current_url

            def _diag():
                try:
                    src_len = len(self.driver.page_source or '')
                except Exception:
                    src_len = -1
                title = (self.driver.title or '')[:50]
                return (f'url="{current_url[:90]}" title="{title}" '
                        f'src_len={src_len}')

            # 1. 检查是否触发反爬验证（需要重试）
            if "risk_handler" in current_url or "verify" in current_url.lower():
                print(f"  ⚠️  触发反爬验证页面 (可重试) | {_diag()}")
                return {'original': 'blocked', 'promo': 'blocked', '_diag': _diag()}

            # 2. 检查是否被重定向到403错误页（反爬拦截）
            if "error" in current_url.lower() and "403" in current_url:
                print(f"  ⚠️  403错误 - 反爬拦截 (可重试) | {_diag()}")
                return {'original': 'forbidden', 'promo': 'forbidden', '_diag': _diag()}

            # 3. 被重定向到首页 — 精确区分"商品不存在"和"反爬拦截"
            if current_url.startswith("https://www.jd.com/?") or current_url == "https://www.jd.com/":
                # ?d 是商品不存在/已失效的特征参数（终态，不重试）
                if current_url == "https://www.jd.com/?d":
                    print(f"  ✗ 商品不存在或链接失效")
                    return {'original': 'not_found', 'promo': 'not_found'}
                print(f"  ⚠️  被重定向到首页 (可重试) | {_diag()}")
                return {'original': 'blocked', 'promo': 'blocked', '_diag': _diag()}

            # 检查商品是否已下架
            page_text = self.driver.page_source
            unavailable_keywords = [
                "该商品已下柜",
                "商品已下架",
                "该商品已下架",
                "抱歉，该商品已下柜",
                "欢迎挑选其他商品",
                "很抱歉，该商品已售馨或下架"
            ]

            for keyword in unavailable_keywords:
                if keyword in page_text:
                    print(f"  ⚠️  商品已下架")
                    return {'original': 'unavailable', 'promo': 'unavailable'}

            # 检查是否被重定向到验证页面
            if "risk_handler" in current_url or "验证" in self.driver.title:
                print(f"  ⚠️  触发验证页面")
                print(f"     请在浏览器中手动完成验证，然后等待...")
                # 等待用户手动验证
                time.sleep(15)
                # 重新访问商品页
                self.driver.get(product_url)
                time.sleep(4)

            # 提取价格
            prices = self._extract_price()
            return prices

        except Exception as e:
            print(f"  ✗ 错误: {e}")
            return None

    def _debug_page_prices(self):
        """诊断页面上的价格相关元素"""
        try:
            debug_js = """
            var info = {url: window.location.href, title: document.title};

            // 搜索所有包含 ¥ 或价格数字的元素
            var allElements = document.querySelectorAll('*');
            var priceElements = [];
            for (var i = 0; i < allElements.length; i++) {
                var el = allElements[i];
                // 只检查叶子节点或直接包含价格文本的元素
                var text = '';
                for (var j = 0; j < el.childNodes.length; j++) {
                    if (el.childNodes[j].nodeType === 3) {
                        text += el.childNodes[j].textContent;
                    }
                }
                text = text.trim();
                if (text && /[¥￥]\\s*\\d+|^\\d+\\.\\d{2}$/.test(text)) {
                    priceElements.push({
                        tag: el.tagName,
                        class: el.className || '',
                        id: el.id || '',
                        text: text.substring(0, 80),
                        parentClass: el.parentElement ? (el.parentElement.className || '') : '',
                        parentId: el.parentElement ? (el.parentElement.id || '') : ''
                    });
                }
            }
            info.priceElements = priceElements.slice(0, 20);

            // 检查已知的价格容器是否存在
            var knownSelectors = [
                '.p-price', '.p-price .price', '#summary-price',
                '.summary-price', '.price-plus', '.J-p-price',
                '.dd .price', '.price-box', '.itemInfo-wrap .price',
                '[class*="price"]', '[class*="Price"]'
            ];
            info.selectorResults = {};
            for (var k = 0; k < knownSelectors.length; k++) {
                var sel = knownSelectors[k];
                var found = document.querySelectorAll(sel);
                if (found.length > 0) {
                    var texts = [];
                    for (var m = 0; m < Math.min(found.length, 3); m++) {
                        texts.push(found[m].textContent.trim().substring(0, 100));
                    }
                    info.selectorResults[sel] = {count: found.length, texts: texts};
                }
            }

            return info;
            """
            result = self.driver.execute_script(debug_js)
            print(f"  [诊断] URL: {result.get('url', '?')}")
            print(f"  [诊断] Title: {result.get('title', '?')}")

            selectors = result.get('selectorResults', {})
            if selectors:
                print(f"  [诊断] 匹配的选择器:")
                for sel, data in selectors.items():
                    print(f"    {sel}: {data['count']}个, 内容: {data['texts']}")
            else:
                print(f"  [诊断] ⚠️ 没有匹配任何已知价格选择器!")

            price_els = result.get('priceElements', [])
            if price_els:
                print(f"  [诊断] 找到{len(price_els)}个含价格文本的元素:")
                for pe in price_els[:10]:
                    print(f"    <{pe['tag']} class='{pe['class']}' id='{pe['id']}'> {pe['text']}")
                    print(f"      父级: class='{pe['parentClass']}' id='{pe['parentId']}'")
            else:
                print(f"  [诊断] ⚠️ 页面上没找到任何含 ¥ 的元素!")

        except Exception as e:
            print(f"  [诊断] 出错: {e}")

    def _extract_price(self) -> Optional[dict]:
        """
        从当前页面提取价格（适配京东2025/2026新版页面）

        Returns:
            字典格式: {'original': float, 'promo': float} 或 None
        """
        try:
            time.sleep(1.0)

            prices = {
                'original': None,
                'promo': None
            }

            # 适配京东新版页面结构（2025/2026）
            # 主价格: .product-price--value (当前售价)
            # 灰色原价: .product-price--gray 内的 ¥ 文本
            # 备用: .calculator-product-info .product-price
            js_script = """
            var result = {main: null, gray: null, fallback: null};

            // 1. 主价格: product-price--value (当前售价/促销价)
            var mainEl = document.querySelector('.product-price--value');
            if (mainEl) {
                var m = mainEl.textContent.trim().match(/([\\.\\d]+)/);
                if (m) result.main = parseFloat(m[1]);
            }

            // 2. 灰色价格: product-price--gray (原价/日常价)
            var grayEl = document.querySelector('.product-price--gray');
            if (grayEl) {
                var g = grayEl.textContent.trim().match(/[¥￥]\\s*([\\.\\d]+)/);
                if (g) result.gray = parseFloat(g[1]);
            }

            // 3. 备用: calculator-product-info 内的 product-price
            if (!result.main) {
                var calcEl = document.querySelector('.calculator-product-info .product-price');
                if (calcEl) {
                    var c = calcEl.textContent.trim().match(/[¥￥]\\s*([\\.\\d]+)/);
                    if (c) result.fallback = parseFloat(c[1]);
                }
            }

            // 4. 再备用: 页面上第一个 product-price 容器
            if (!result.main && !result.fallback) {
                var ppEl = document.querySelector('.product-price');
                if (ppEl) {
                    var p = ppEl.textContent.match(/[¥￥]\\s*([\\.\\d]+)/);
                    if (p) result.fallback = parseFloat(p[1]);
                }
            }

            // 5. 旧版兼容: .p-price .price
            if (!result.main && !result.fallback) {
                var oldEl = document.querySelector('.p-price .price');
                if (oldEl) {
                    var o = oldEl.textContent.trim().match(/([\\.\\d]+)/);
                    if (o) result.fallback = parseFloat(o[1]);
                }
            }

            return result;
            """

            data = self.driver.execute_script(js_script)

            if not data:
                print(f"  未找到任何价格元素")
                return None

            main_price = data.get('main')
            gray_price = data.get('gray')
            fallback_price = data.get('fallback')

            print(f"  价格数据: 主价={main_price}, 灰色={gray_price}, 备用={fallback_price}")

            # 确定当前售价
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

            print(f"  未找到有效价格")
            return None

        except Exception as e:
            print(f"  提取价格失败: {e}")
            import traceback
            traceback.print_exc()
            return None

    def is_session_valid(self) -> bool:
        """检查浏览器会话是否有效"""
        try:
            # 尝试获取当前URL来检测会话
            _ = self.driver.current_url
            return True
        except:
            return False

    def restart_browser(self):
        """CDP attach 模式 — 重连到已运行的 Chrome(不关闭 Chrome 进程,那是用户的)."""
        print("\n  ⚠️  会话失效,重连 CDP...")
        # 不调 quit — driver.quit() 在 attach 模式下可能会关闭 Chrome 标签页,
        # 直接重新 init_driver 即可建立新的 selenium 会话连到同一 Chrome
        self.driver = None

        try:
            self._init_driver()
        except Exception as e:
            print(f"  ✗ 重连失败: {e}")
            return False

        # 检测登录态(Chrome profile 已持久化登录,通常无需扫码)
        self.login(auto_login=False)
        if self.is_logged_in:
            print("  ✓ 重连成功(登录态已自动恢复)\n")
            return True
        else:
            print("  ✗ 重连后未检测到登录态,请在 Chrome 中检查\n")
            return False

    def close(self):
        """关闭浏览器并清理资源 — attach 模式只断开 selenium 连接,
        不调 driver.quit()(那会试图关闭 Chrome,但 Chrome 是用户启动的,应该保持)."""
        if self.driver:
            # CDP attach 模式:不调 quit,避免误关用户的 Chrome.
            # 只解除 selenium 对它的引用,让 GC 清理 websocket 连接.
            self.driver = None
        # 不杀 chrome 子进程 — 那些是用户启动的 Chrome,需要保留


if __name__ == "__main__":
    print("=" * 70)
    print("通过搜索访问商品测试")
    print("=" * 70)

    crawler = JDCrawlerViaSearch(headless=False)

    try:
        crawler.login()
        if crawler.is_logged_in:
            # 测试
            product_id = "100140584252"
            print(f"\n测试商品ID: {product_id}")
            print(f"预期: 原价 ¥79.90, 促销价 ¥67.91")
            print()

            prices = crawler.get_price_via_search(product_id)

            if prices:
                print(f"\n" + "=" * 70)
                print("✅ 提取成功！")
                print("=" * 70)
                if prices.get('original'):
                    print(f"  原价: ¥{prices['original']}")
                if prices.get('promo'):
                    print(f"  促销价: ¥{prices['promo']}")

                # 验证
                if prices.get('original') == 79.90 and prices.get('promo') == 67.91:
                    print("\n🎉 完美！两个价格都正确！")
                elif prices.get('promo') == 67.91:
                    print("\n✅ 促销价正确！")
                elif prices.get('original') == 79.90:
                    print("\n✅ 原价正确！")
                else:
                    print("\n⚠️  价格与预期不符")

            else:
                print(f"\n✗ 获取失败")

            input("\n按Enter关闭浏览器...")
    except KeyboardInterrupt:
        print("\n中断")
    finally:
        crawler.close()
