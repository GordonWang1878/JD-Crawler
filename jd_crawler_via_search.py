#!/usr/bin/env python3
"""
通过搜索访问商品 - 更像真人的行为
不直接访问商品链接，而是先搜索，再点击进入
"""
import warnings
# 抑制 urllib3 的 OpenSSL 警告
warnings.filterwarnings('ignore', message='urllib3 v2 only supports OpenSSL 1.1.1+')

import undetected_chromedriver as uc
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
        self._init_driver()

    def _init_driver(self):
        """初始化浏览器"""
        try:
            options = uc.ChromeOptions()
            if self.headless:
                options.add_argument('--headless=new')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--window-size=1920,1080')

            chrome_version = _detect_chrome_version()
            print(f"  正在初始化浏览器... (Chrome v{chrome_version or '?'})")
            t0 = time.time()
            self.driver = uc.Chrome(
                options=options,
                version_main=chrome_version,
            )
            self.driver.implicitly_wait(5)
            print(f"  ✓ 浏览器启动成功 ({time.time()-t0:.1f}秒)")
        except Exception as e:
            print(f"初始化驱动失败: {str(e)}")
            raise

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
        """
        登录京东账号

        Args:
            auto_login: 如果 cookies 失效，是否自动引导用户登录
        """
        # 1. 尝试使用 cookies 登录
        if self.load_cookies():
            self.driver.get("https://order.jd.com/center/list.action")
            time.sleep(3)
            if "登录" not in self.driver.title and "login" not in self.driver.current_url.lower():
                print("✓ 使用cookies登录成功")
                self.is_logged_in = True
                return

        # 2. Cookies 失效或不存在
        if not auto_login:
            print("✗ 登录失败，cookies无效或不存在")
            return

        # 3. 引导用户手动登录
        print("\n" + "=" * 70)
        print("需要登录京东账号")
        print("=" * 70)
        print("\n浏览器将打开京东登录页面，请按以下步骤操作：")
        print("  1. 在浏览器中登录你的京东账号（推荐扫码登录）")
        print("  2. 登录成功后，返回终端")
        print("  3. 按 Enter 键继续\n")

        try:
            # 打开京东首页
            self.driver.get("https://www.jd.com")
            time.sleep(2)

            # 点击登录按钮
            try:
                login_link = self.driver.find_element(By.CLASS_NAME, "link-login")
                login_link.click()
                time.sleep(2)
            except:
                # 如果找不到登录链接，直接打开登录页
                self.driver.get("https://passport.jd.com/new/login.aspx")
                time.sleep(2)

            # 自动检测登录状态（每5秒检查一次，最多等待3分钟）
            print(">>> 等待登录... (最多等待3分钟)")
            max_wait = 180  # 3分钟
            check_interval = 5  # 每5秒检查一次
            waited = 0

            while waited < max_wait:
                time.sleep(check_interval)
                waited += check_interval

                # 检查登录状态
                try:
                    self.driver.get("https://order.jd.com/center/list.action")
                    time.sleep(2)

                    if "登录" not in self.driver.title and "login" not in self.driver.current_url.lower():
                        print("\n✓ 登录成功！")
                        self.is_logged_in = True

                        # 保存 cookies
                        self._save_cookies()
                        print(f"✓ Cookies 已保存到 {self.cookies_file}")
                        print("  下次运行将自动登录\n")
                        break
                    else:
                        print(f">>> 等待登录中... ({waited}/{max_wait}秒)")
                except Exception as e:
                    print(f">>> 检测登录状态时出错: {e}")
                    continue

            if not self.is_logged_in:
                print(f"\n✗ 登录超时（等待了{max_wait}秒）")

        except Exception as e:
            print(f"\n✗ 登录过程出错: {e}")
            self.is_logged_in = False

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
        """登录后模拟正常浏览行为，降低反爬风险"""
        print("  热身：模拟正常浏览...")
        try:
            # 1. 浏览京东首页
            self.driver.get("https://www.jd.com")
            time.sleep(random.uniform(3, 5))
            self.driver.execute_script("window.scrollTo(0, 600);")
            time.sleep(random.uniform(1, 2))
            self.driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(random.uniform(1, 2))

            # 2. 搜索一个热门关键词
            self.driver.get("https://search.jd.com/Search?keyword=充电宝&enc=utf-8")
            time.sleep(random.uniform(3, 5))
            self.driver.execute_script("window.scrollTo(0, 800);")
            time.sleep(random.uniform(2, 3))
            self.driver.execute_script("window.scrollTo(0, 1500);")
            time.sleep(random.uniform(1, 2))

            # 3. 点进一个商品看看（用热门商品）
            self.driver.get("https://item.jd.com/100015253059.html")
            time.sleep(random.uniform(3, 5))
            self.driver.execute_script("window.scrollTo(0, 500);")
            time.sleep(random.uniform(2, 3))

            # 4. 回到首页
            self.driver.get("https://www.jd.com")
            time.sleep(random.uniform(2, 3))

            print("  ✓ 热身完成")
        except Exception as e:
            print(f"  热身出错（忽略）: {e}")

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
            # 等待页面加载 — 随机化避免被检测
            time.sleep(random.uniform(3.5, 5.0))

            # 模拟人类行为：滚动页面触发懒加载
            try:
                self.driver.execute_script("window.scrollTo(0, 300);")
                time.sleep(0.5)
                self.driver.execute_script("window.scrollTo(0, 0);")
            except:
                pass

            # 检查当前URL - 精确区分不同的失败类型
            current_url = self.driver.current_url

            # 1. 检查是否触发反爬验证（需要重试）
            if "risk_handler" in current_url or "verify" in current_url.lower():
                print(f"  ⚠️  触发反爬验证页面 (可重试)")
                return {'original': 'blocked', 'promo': 'blocked'}

            # 2. 检查是否被重定向到403错误页（反爬拦截）
            if "error" in current_url.lower() and "403" in current_url:
                print(f"  ⚠️  403错误 - 反爬拦截 (可重试)")
                return {'original': 'forbidden', 'promo': 'forbidden'}

            # 3. 被重定向到首页 — 精确区分"商品不存在"和"反爬拦截"
            if current_url.startswith("https://www.jd.com/?") or current_url == "https://www.jd.com/":
                # ?d 是商品不存在/已失效的特征参数（终态，不重试）
                if current_url == "https://www.jd.com/?d":
                    print(f"  ✗ 商品不存在或链接失效")
                    return {'original': 'not_found', 'promo': 'not_found'}
                print(f"  ⚠️  被重定向到首页 (可重试)")
                return {'original': 'blocked', 'promo': 'blocked'}

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
        """重启浏览器并重新登录"""
        print("\n  ⚠️  检测到浏览器会话失效，正在重启...")
        try:
            if self.driver:
                self.driver.quit()
        except:
            pass

        # 重新初始化
        self._init_driver()

        # 重新登录
        print("  重新登录...")
        self.login()

        if self.is_logged_in:
            print("  ✓ 浏览器重启成功！\n")
            return True
        else:
            print("  ✗ 重新登录失败\n")
            return False

    def close(self):
        """关闭浏览器并清理资源"""
        if self.driver:
            try:
                # 先关闭所有窗口
                self.driver.quit()
            except:
                pass
            finally:
                # 确保清理
                self.driver = None

        # 清理可能残留的进程
        try:
            import psutil
            import os
            current_process = psutil.Process(os.getpid())
            children = current_process.children(recursive=True)
            for child in children:
                try:
                    if 'chrome' in child.name().lower():
                        child.terminate()
                except:
                    pass
        except ImportError:
            # psutil 未安装，跳过
            pass
        except:
            pass


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
