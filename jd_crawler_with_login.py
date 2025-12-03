#!/usr/bin/env python3
"""
京东价格爬虫 - 支持登录版本
第一次运行会打开浏览器让用户手动登录，之后自动使用保存的cookies
使用undetected-chromedriver绕过反爬检测
"""
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import json
import os
import re
from typing import Optional, Dict
import pickle


class JDCrawlerWithLogin:
    """支持登录的京东爬虫"""

    def __init__(self, headless: bool = False, cookies_file: str = "jd_cookies.pkl"):
        """
        初始化爬虫

        Args:
            headless: 是否使用无头模式（登录时必须为False）
            cookies_file: cookies保存文件路径
        """
        self.headless = headless
        self.cookies_file = cookies_file
        self.driver = None
        self.is_logged_in = False
        self._init_driver()

    def _init_driver(self):
        """初始化Chrome驱动 - 使用undetected_chromedriver绕过反爬检测"""
        try:
            options = uc.ChromeOptions()

            # 基本设置
            if self.headless:
                options.add_argument('--headless=new')

            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--window-size=1920,1080')

            # 使用undetected_chromedriver创建浏览器实例
            # 这会自动处理反检测，隐藏Selenium特征
            self.driver = uc.Chrome(
                options=options,
                use_subprocess=True,
                version_main=None  # 自动检测Chrome版本
            )

            self.driver.implicitly_wait(5)

        except Exception as e:
            print(f"初始化驱动失败: {str(e)}")
            raise

    def save_cookies(self):
        """保存cookies到文件"""
        cookies = self.driver.get_cookies()
        with open(self.cookies_file, 'wb') as f:
            pickle.dump(cookies, f)
        print(f"✓ Cookies已保存到 {self.cookies_file}")

    def load_cookies(self) -> bool:
        """
        从文件加载cookies

        Returns:
            是否成功加载
        """
        if not os.path.exists(self.cookies_file):
            return False

        try:
            # 先访问京东首页，然后加载cookies
            self.driver.get("https://www.jd.com")
            time.sleep(2)

            with open(self.cookies_file, 'rb') as f:
                cookies = pickle.load(f)

            for cookie in cookies:
                # 移除可能导致问题的字段
                cookie.pop('sameSite', None)
                cookie.pop('expiry', None)
                try:
                    self.driver.add_cookie(cookie)
                except Exception as e:
                    print(f"添加cookie失败: {e}")
                    continue

            print("✓ Cookies已加载")
            return True

        except Exception as e:
            print(f"✗ 加载cookies失败: {e}")
            return False

    def login(self, wait_time: int = 120):
        """
        登录京东

        Args:
            wait_time: 等待用户登录的最大时间（秒）
        """
        print("\n" + "=" * 60)
        print("京东登录")
        print("=" * 60)

        # 尝试加载已有的cookies
        if self.load_cookies():
            # 验证cookies是否有效
            self.driver.get("https://order.jd.com/center/list.action")
            time.sleep(3)

            if "登录" not in self.driver.title and "login" not in self.driver.current_url.lower():
                print("✓ 使用已保存的cookies登录成功")
                self.is_logged_in = True
                return
            else:
                print("已保存的cookies已失效，需要重新登录")

        # 需要手动登录
        print("\n请在打开的浏览器中登录京东账号：")
        print("1. 建议使用【扫码登录】方式（手机京东APP扫码）")
        print("2. 登录成功后，请等待页面完全加载")
        print("3. 看到京东首页后，回到终端按Enter键继续")
        print(f"\n等待登录（最多{wait_time}秒）...\n")

        # 打开京东登录页
        self.driver.get("https://passport.jd.com/new/login.aspx")

        # 等待用户登录
        input("登录完成后，请按Enter键继续...")

        # 验证是否登录成功
        self.driver.get("https://order.jd.com/center/list.action")
        time.sleep(3)

        if "登录" not in self.driver.title and "login" not in self.driver.current_url.lower():
            print("\n✓ 登录成功！")
            self.is_logged_in = True
            self.save_cookies()
        else:
            print("\n✗ 登录失败或未完成登录")
            self.is_logged_in = False

    def _check_driver_alive(self) -> bool:
        """检查driver是否还活着"""
        try:
            if self.driver:
                _ = self.driver.current_url
                return True
        except:
            return False
        return False

    def _restart_driver(self):
        """重启driver"""
        print("  检测到浏览器已关闭，正在重新启动...")
        try:
            if self.driver:
                self.driver.quit()
        except:
            pass

        self.driver = None
        self._init_driver()

        # 重新加载cookies
        if os.path.exists(self.cookies_file):
            self.load_cookies()
            self.driver.get("https://www.jd.com")
            time.sleep(2)
            print("  ✓ 浏览器已重启并恢复登录状态")

    def get_price(self, url: str, timeout: int = 10) -> Optional[float]:
        """
        获取商品价格

        Args:
            url: 京东商品URL
            timeout: 超时时间

        Returns:
            价格（float）或None
        """
        if not self.is_logged_in:
            print("  ✗ 未登录，无法获取价格")
            return None

        try:
            # 检查浏览器是否还活着
            if not self._check_driver_alive():
                self._restart_driver()

            print(f"  正在访问: {url}")
            self.driver.get(url)
            time.sleep(2)

            # 验证URL是否正确加载
            current_url = self.driver.current_url
            if url not in current_url and current_url not in url:
                print(f"  ⚠️  URL不匹配！")
                print(f"    请求: {url}")
                print(f"    实际: {current_url}")

            time.sleep(2)  # 再等待，确保页面加载完成

            # 等待价格元素加载
            wait = WebDriverWait(self.driver, timeout)

            # 多种价格元素选择器（按优先级排序）
            price_selectors = [
                # 优先：最常见的价格元素
                (By.XPATH, "//span[@class='price J-p-100140584252']"),  # 特定商品ID的价格
                (By.XPATH, "//span[contains(@class,'price') and contains(@class,'J-p-')]"),
                (By.XPATH, "//div[@class='dd']//span[@class='price']"),
                (By.XPATH, "//span[@class='p-price']//span[@class='price']"),
                (By.XPATH, "//div[@class='summary-price']//span[@class='price']"),
                # 备用：其他可能的位置
                (By.CSS_SELECTOR, ".price-tag"),
                (By.CSS_SELECTOR, ".jd-price"),
            ]

            for by, selector in price_selectors:
                try:
                    # 等待元素出现
                    element = wait.until(EC.presence_of_element_located((by, selector)))

                    # 多次尝试获取文本（等待JavaScript填充价格）
                    for attempt in range(10):
                        text = element.text.strip()

                        # 清理文本
                        text = text.replace('¥', '').replace('￥', '').replace(',', '').strip()

                        if text and text not in ['', '登录']:
                            # 提取数字（支持小数）
                            match = re.search(r'(\d+(?:\.\d{1,2})?)', text)
                            if match:
                                price = float(match.group(1))
                                if 1 < price < 100000:  # 合理范围
                                    return price

                        time.sleep(0.6)

                except Exception as e:
                    continue

            # 备用方法：使用JavaScript查找
            js_script = """
            var priceElements = document.querySelectorAll('.price, .p-price, [class*="price"]');
            for (var i = 0; i < priceElements.length; i++) {
                var text = priceElements[i].textContent || priceElements[i].innerText;
                if (text && text.match(/^[¥￥]?\\s*\\d+\\.\\d{1,2}$/)) {
                    var match = text.match(/([\\d\\.]+)/);
                    if (match) {
                        return parseFloat(match[1]);
                    }
                }
            }
            return null;
            """

            price = self.driver.execute_script(js_script)
            if price and 1 < price < 100000:
                return float(price)

            return None

        except Exception as e:
            print(f"  ✗ 获取价格失败: {str(e)}")
            return None

    def close(self):
        """关闭浏览器"""
        if self.driver:
            self.driver.quit()
            self.driver = None

    def __del__(self):
        self.close()


if __name__ == "__main__":
    print("=" * 60)
    print("京东价格爬虫 - 登录测试")
    print("=" * 60)

    # 初始化爬虫（非无头模式，以便手动登录）
    crawler = JDCrawlerWithLogin(headless=False)

    try:
        # 登录
        crawler.login()

        if crawler.is_logged_in:
            # 测试URL
            test_urls = [
                "https://item.jd.com/100140584252.html",
                "https://item.jd.com/100140584254.html",
            ]

            print("\n开始测试价格获取...\n")
            for i, url in enumerate(test_urls, 1):
                print(f"[{i}/{len(test_urls)}] {url}")
                price = crawler.get_price(url)
                if price:
                    print(f"  ✓ 价格: ¥{price}\n")
                else:
                    print(f"  ✗ 获取失败\n")
                time.sleep(2)

            print("测试完成！下次运行将自动使用保存的cookies。")
        else:
            print("\n登录失败，无法继续测试")

    except KeyboardInterrupt:
        print("\n\n测试被中断")
    finally:
        input("\n按Enter键关闭浏览器...")
        crawler.close()
