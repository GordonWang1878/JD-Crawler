#!/usr/bin/env python3
"""
京东价格爬虫 - 最终版本
从页面的多个位置提取价格，包括促销标签、图片alt文本等
"""
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
import time
import random
import re
from typing import Optional
import requests


class JDPriceCrawler:
    """京东价格爬虫"""

    def __init__(self, use_selenium: bool = False, headless: bool = True):
        """
        初始化爬虫

        Args:
            use_selenium: 是否使用Selenium（更可靠但更慢）
            headless: Selenium无头模式
        """
        self.use_selenium = use_selenium
        self.headless = headless
        self.driver = None

        if not use_selenium:
            self.session = requests.Session()
            try:
                requests.packages.urllib3.disable_warnings()
            except:
                pass
            self.session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'zh-CN,zh;q=0.9',
            })

    def _init_driver(self):
        """初始化Selenium驱动"""
        if self.driver:
            return

        chrome_options = Options()
        if self.headless:
            chrome_options.add_argument('--headless=new')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument(
            'user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        )

        service = ChromeService(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=chrome_options)
        self.driver.implicitly_wait(5)

    def extract_sku_id(self, url: str) -> Optional[str]:
        """从URL提取SKU ID"""
        match = re.search(r'/(\d+)\.html', url)
        if match:
            return match.group(1)
        return None

    def get_price_selenium(self, url: str) -> Optional[float]:
        """使用Selenium获取价格"""
        try:
            if not self.driver:
                self._init_driver()

            self.driver.get(url)
            time.sleep(3)  # 等待页面加载

            # 策略1: 从整个页面源代码中搜索价格相关的数字
            page_source = self.driver.page_source

            # 搜索促销价格、特价等标签
            price_patterns = [
                r'price["\']?\s*[:=]\s*["\']?(\d+\.?\d{0,2})["\']?',
                r'[\u4ef7\u683c]\s*[:：]\s*[¥￥]?\s*(\d+\.?\d{0,2})',  # 价格:
                r'[¥￥]\s*(\d+\.?\d{0,2})',
                r'(\d{2,5}\.\d{1,2})',  # 两位以上整数.小数
            ]

            found_prices = []
            for pattern in price_patterns:
                matches = re.finditer(pattern, page_source)
                for match in matches:
                    try:
                        price = float(match.group(1))
                        if 10 < price < 50000:  # 合理的价格范围
                            found_prices.append(price)
                    except:
                        continue

            if found_prices:
                # 返回最常见的价格
                from collections import Counter
                price_counts = Counter(found_prices)
                most_common_price = price_counts.most_common(1)[0][0]
                return most_common_price

            return None

        except Exception as e:
            print(f"Selenium获取价格失败: {str(e)}")
            return None

    def get_price_requests(self, url: str) -> Optional[float]:
        """使用requests获取价格"""
        try:
            response = self.session.get(url, timeout=10, verify=False)
            if response.status_code != 200:
                return None

            html = response.text

            # 从HTML中搜索价格
            price_patterns = [
                r'price["\']?\s*[:=]\s*["\']?(\d+\.?\d{0,2})["\']?',
                r'[¥￥]\s*(\d+\.?\d{0,2})',
                r'(\d{2,5}\.\d{1,2})',
            ]

            found_prices = []
            for pattern in price_patterns:
                matches = re.finditer(pattern, html)
                for match in matches:
                    try:
                        price = float(match.group(1))
                        if 10 < price < 50000:
                            found_prices.append(price)
                    except:
                        continue

            if found_prices:
                from collections import Counter
                price_counts = Counter(found_prices)
                most_common_price = price_counts.most_common(1)[0][0]
                return most_common_price

            return None

        except Exception as e:
            print(f"Requests获取价格失败: {str(e)}")
            return None

    def get_price(self, url: str) -> Optional[float]:
        """
        获取价格（自动选择方法）

        Args:
            url: 京东商品URL

        Returns:
            价格（float）或None
        """
        if self.use_selenium:
            return self.get_price_selenium(url)
        else:
            # 先尝试requests（快速），如果失败则尝试selenium
            price = self.get_price_requests(url)
            if price:
                return price

            # requests失败，尝试selenium
            print("Requests方法失败，尝试Selenium...")
            self.use_selenium = True
            return self.get_price_selenium(url)

    def get_price_with_retry(self, url: str, max_retries: int = 2) -> Optional[float]:
        """带重试的价格获取"""
        for attempt in range(max_retries):
            price = self.get_price(url)
            if price is not None:
                return price

            if attempt < max_retries - 1:
                delay = 2 + random.uniform(0, 1)
                print(f"重试 {attempt + 1}/{max_retries - 1}，等待 {delay:.1f} 秒...")
                time.sleep(delay)

        return None

    def close(self):
        """关闭资源"""
        if self.driver:
            self.driver.quit()
            self.driver = None
        if hasattr(self, 'session'):
            self.session.close()

    def __del__(self):
        """析构函数"""
        self.close()


if __name__ == "__main__":
    # 测试代码
    print("初始化爬虫...")
    crawler = JDPriceCrawler(use_selenium=False)

    try:
        test_url = "https://item.jd.com/100140584252.html"
        print(f"测试URL: {test_url}\n")

        price = crawler.get_price_with_retry(test_url)
        if price:
            print(f"\n✓ 成功获取价格: ¥{price}")
        else:
            print("\n✗ 获取价格失败")

    finally:
        crawler.close()
