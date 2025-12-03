#!/usr/bin/env python3
"""
通过搜索访问商品 - 更像真人的行为
不直接访问商品链接，而是先搜索，再点击进入
"""
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
import time
import re
import os
import pickle
from typing import Optional


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

            print(f"  正在初始化浏览器...")
            self.driver = uc.Chrome(
                options=options,
                version_main=142,
                use_subprocess=False,
            )
            self.driver.implicitly_wait(5)
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

    def login(self):
        """登录"""
        if self.load_cookies():
            self.driver.get("https://order.jd.com/center/list.action")
            time.sleep(3)
            if "登录" not in self.driver.title and "login" not in self.driver.current_url.lower():
                print("✓ 使用cookies登录成功")
                self.is_logged_in = True
                return
        print("✗ 登录失败")

    def get_price_via_search(self, product_id: str) -> Optional[float]:
        """
        通过搜索获取价格

        Args:
            product_id: 商品ID，例如 "100140584252"
        """
        if not self.is_logged_in:
            print("  ✗ 未登录")
            return None

        try:
            # 访问京东首页
            print(f"  访问京东首页...")
            self.driver.get("https://www.jd.com")
            time.sleep(2)

            # 模拟人类浏览
            self.driver.execute_script("window.scrollTo(0, 300);")
            time.sleep(1)

            # 在搜索框搜索商品ID
            print(f"  搜索商品ID: {product_id}")
            search_box = self.driver.find_element(By.ID, "key")
            search_box.clear()
            time.sleep(0.5)

            # 模拟人类打字，一个字符一个字符输入
            for char in product_id:
                search_box.send_keys(char)
                time.sleep(0.1)

            time.sleep(0.5)
            search_box.send_keys(Keys.RETURN)

            print(f"  等待搜索结果...")
            time.sleep(3)

            # 检查是否被重定向到403页面
            current_url = self.driver.current_url
            if "403" in current_url or "www.jd.com/?from" in current_url:
                print(f"  ⚠️  仍然被检测到")
                return None

            # 查找商品链接（搜索结果中的第一个）
            try:
                # 等待搜索结果加载
                wait = WebDriverWait(self.driver, 10)
                # 查找商品链接
                product_links = self.driver.find_elements(By.CSS_SELECTOR, f"a[href*='{product_id}']")

                if product_links:
                    print(f"  找到商品链接，点击进入...")

                    # 先关闭可能的弹窗或遮挡物
                    try:
                        # 尝试关闭图片放大层
                        self.driver.execute_script("document.querySelectorAll('.zoomed-image').forEach(el => el.style.display='none');")
                        time.sleep(0.5)
                    except:
                        pass

                    # 找到商品详情页的链接（必须是 item.jd.com/{product_id}.html 格式）
                    target_link = None
                    target_href = None

                    # 首先尝试直接查找标准的商品页链接
                    standard_url = f"https://item.jd.com/{product_id}.html"

                    for link in product_links:
                        href = link.get_attribute('href')
                        if not href:
                            continue

                        # 必须是 item.jd.com/{product_id}.html 格式
                        if f'item.jd.com/{product_id}.html' in href:
                            target_link = link
                            target_href = href
                            break

                    # 如果没找到，直接构造标准URL
                    if not target_href:
                        print(f"  未找到标准商品链接，使用构造的URL")
                        target_href = standard_url

                    if target_href:
                        print(f"  导航到商品页: {target_href}")
                        self.driver.get(target_href)
                        time.sleep(3)

                        # 检查是否被重定向到403
                        current_url = self.driver.current_url
                        if "403" in current_url or "www.jd.com/?from" in current_url:
                            print(f"  ⚠️  点击后被重定向到403")
                            return None

                        # 提取价格
                        price = self._extract_price()
                        return price
                    else:
                        print(f"  ✗ 未找到合适的商品链接")
                        return None
                else:
                    print(f"  ✗ 未找到商品链接")
                    return None
            except Exception as e:
                print(f"  ✗ 查找商品链接失败: {e}")
                import traceback
                traceback.print_exc()
                return None

        except Exception as e:
            print(f"  ✗ 错误: {e}")
            return None

    def _extract_price(self) -> Optional[float]:
        """从当前页面提取价格"""
        try:
            wait = WebDriverWait(self.driver, 10)

            # 价格选择器
            price_selectors = [
                (By.XPATH, "//span[contains(@class,'price') and contains(@class,'J-p-')]"),
                (By.XPATH, "//div[@class='dd']//span[@class='price']"),
                (By.CSS_SELECTOR, ".price-tag"),
            ]

            for by, selector in price_selectors:
                try:
                    element = wait.until(EC.presence_of_element_located((by, selector)))
                    for _ in range(10):
                        text = element.text.strip()
                        text = text.replace('¥', '').replace('￥', '').replace(',', '').strip()
                        if text and text not in ['', '登录']:
                            match = re.search(r'(\d+(?:\.\d{1,2})?)', text)
                            if match:
                                price = float(match.group(1))
                                if 1 < price < 100000:
                                    return price
                        time.sleep(0.6)
                except:
                    continue

            return None
        except Exception as e:
            print(f"  提取价格失败: {e}")
            return None

    def close(self):
        """关闭浏览器"""
        if self.driver:
            self.driver.quit()


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
            price = crawler.get_price_via_search(product_id)

            if price:
                print(f"\n✅ 成功！价格: ¥{price}")
            else:
                print(f"\n✗ 获取失败")

            input("\n按Enter关闭浏览器...")
    except KeyboardInterrupt:
        print("\n中断")
    finally:
        crawler.close()
