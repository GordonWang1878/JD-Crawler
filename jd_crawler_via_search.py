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
            time.sleep(2.5)  # 等待页面加载（优化后：4s→3s→2.5s）

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

            # 3. 检查是否被重定向到首页（商品不存在）
            if current_url.startswith("https://www.jd.com/?") or current_url == "https://www.jd.com/":
                print(f"  ⚠️  被重定向到首页 - 商品不存在")
                return {'original': 'not_found', 'promo': 'not_found'}

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

    def _extract_price(self) -> Optional[dict]:
        """
        从当前页面提取价格（包括原价和促销价）

        支持多种价格标注：
        - 日常价（原价）
        - 到手价（促销价）
        - 补贴价（促销价）
        - 删除线价格（原价）

        Returns:
            字典格式: {'original': float, 'promo': float} 或 None
        """
        try:
            time.sleep(1.0)  # 等待价格加载（优化后：2s→1.5s→1s）

            prices = {
                'original': None,
                'promo': None
            }

            # 使用 JavaScript 针对京东特定的价格区域提取
            js_script = """
            var results = [];

            // 新方案：使用超精确的选择器，只抓商品主价格
            // 不用通用的.price/.dd（会抓到附加服务、保险等）
            // 不用容器本身（如.p-price），只用子元素
            var priceSelectors = [
                '.p-price .price',              // 主价格区域内的价格
                '.p-price del',                 // 主价格区域内的删除线
                '#summary-price .price',        // 价格汇总内的价格
                '#summary-price del',           // 价格汇总内的删除线
                '.summary-price .price',        // 价格摘要内的价格
                '.summary-price del',           // 价格摘要内的删除线
                // 移除容器本身（.p-price），避免重复抓取
            ];

            var allPriceElements = [];
            for (var s = 0; s < priceSelectors.length; s++) {
                var elems = document.querySelectorAll(priceSelectors[s]);
                for (var e = 0; e < elems.length; e++) {
                    allPriceElements.push(elems[e]);
                }
            }

            for (var i = 0; i < allPriceElements.length; i++) {
                var elem = allPriceElements[i];
                var text = (elem.textContent || elem.innerText || '').trim();

                // 匹配价格：可以有或没有 ¥ 符号，小数点可选
                var priceMatch = text.match(/[¥￥]?\\s*(\\d+(?:\\.\\d{1,2})?)/);

                if (priceMatch && priceMatch[1]) {
                    var price = parseFloat(priceMatch[1]);

                    // 价格在合理范围内
                    if (price >= 10 && price <= 10000) {
                        // 获取完整的上下文
                        var context = text;
                        var parent = elem.parentElement;
                        if (parent) {
                            context = (parent.textContent || '').substring(0, 150);
                        }

                        // 排除明显不是商品价格的元素
                        // 注意：不能用单字"日"，会误杀"日常价"
                        var skipKeywords = ['积分', '优惠券', '满减', '津贴', '红包', '库存', '评价', '已购', '运费', '邮费',
                                          '月日', '时:', '分:', '点:', '前付', 'mAh', 'MAH', '毫安', '容量', '送达',
                                          '功率', 'W大', 'W快', 'W闪', '颜色', '版本', '规格', '限时达', '京准达', '物流'];
                        var shouldSkip = false;

                        // 检查是否包含日期时间格式（如"12月11日"、"19:30"）
                        if (/\d+月/.test(context) || /\d+:\d+/.test(context) || /\d+分钟/.test(context)) {
                            shouldSkip = true;
                        }

                        if (!shouldSkip) {
                            for (var j = 0; j < skipKeywords.length; j++) {
                                if (context.indexOf(skipKeywords[j]) >= 0) {
                                    shouldSkip = true;
                                    break;
                                }
                            }
                        }

                        if (!shouldSkip) {
                            // 检查是否有删除线（标签或CSS样式）
                            var hasStrikethrough = false;

                            // 方法1：检查是否是<del>标签
                            if (elem.tagName === 'DEL') {
                                hasStrikethrough = true;
                            }

                            // 方法2：检查是否在<del>标签内
                            if (!hasStrikethrough && elem.closest && elem.closest('del')) {
                                hasStrikethrough = true;
                            }

                            // 方法3：检查CSS样式
                            if (!hasStrikethrough) {
                                var computedStyle = window.getComputedStyle(elem);
                                if (computedStyle.textDecoration && computedStyle.textDecoration.includes('line-through')) {
                                    hasStrikethrough = true;
                                }
                            }

                            results.push({
                                price: price,
                                text: text,
                                context: context,
                                tagName: elem.tagName,
                                className: elem.className || '',
                                parentClassName: parent ? (parent.className || '') : '',
                                isDel: hasStrikethrough
                            });
                        }
                    }
                }
            }

            return results;
            """

            # 执行 JavaScript 获取所有价格候选
            all_prices = self.driver.execute_script(js_script)

            if not all_prices:
                print(f"  未找到任何价格候选")
                return None

            print(f"  找到 {len(all_prices)} 个价格候选")

            # 调试：显示所有候选价格（含详细信息）
            if len(all_prices) <= 15:
                for idx, item in enumerate(all_prices, 1):
                    context_preview = item['context'][:50] if len(item['context']) > 50 else item['context']
                    del_mark = " [删除线]" if item.get('isDel', False) else ""
                    tag = item.get('tagName', '')
                    cls = item.get('className', '')
                    print(f"    候选{idx}: ¥{item['price']}{del_mark}")
                    print(f"           标签:{tag} 类:{cls}")
                    print(f"           上下文: {context_preview}")

            # 去重：相同价格优先保留有明确标注的（删除线、关键词等）
            unique_prices = {}
            for item in all_prices:
                price = item['price']
                if price not in unique_prices:
                    # 第一次遇到这个价格，直接保存
                    unique_prices[price] = item
                else:
                    # 已存在这个价格，优先保留有删除线或关键词标注的
                    existing = unique_prices[price]
                    # 如果新的有删除线，旧的没有，替换
                    if item.get('isDel', False) and not existing.get('isDel', False):
                        unique_prices[price] = item
                    # 如果新的上下文包含价格关键词，旧的没有，替换
                    elif any(kw in item.get('context', '') for kw in ['日常价', '原价', '到手价', '补贴价', '划线价']):
                        if not any(kw in existing.get('context', '') for kw in ['日常价', '原价', '到手价', '补贴价', '划线价']):
                            unique_prices[price] = item

            all_prices = list(unique_prices.values())

            # 智能识别价格类型
            # 第一步：收集所有匹配关键词的价格
            original_candidates = []  # 原价候选
            promo_candidates = []      # 促销价候选

            for item in all_prices:
                price = item['price']
                context = item['context']
                text = item['text']
                is_del = item['isDel']
                class_name = item.get('className', '')
                parent_class = item.get('parentClassName', '')

                # 原价关键词
                if any(keyword in context for keyword in ['日常价', '市场价', '原价', '划线价']):
                    original_candidates.append((price, '日常价/原价', item))
                # 删除线也是原价
                elif is_del:
                    original_candidates.append((price, '删除线', item))

                # 促销价关键词（检查更精确的上下文）
                if '到手价' in context or '到手价' in text:
                    promo_candidates.append((price, '到手价', item))
                elif '补贴价' in context or '补贴价' in text:
                    promo_candidates.append((price, '补贴价', item))
                elif any(keyword in context for keyword in ['秒杀价', '抢购价', '促销价', '券后']):
                    promo_candidates.append((price, '促销标注', item))

            # 第二步：从候选中选择最佳价格
            # 原价：如果有多个候选，选择较大的
            if original_candidates:
                # 按价格降序排序，取最大的
                original_candidates.sort(key=lambda x: x[0], reverse=True)
                prices['original'] = original_candidates[0][0]
                print(f"  找到原价: ¥{prices['original']} (标注: {original_candidates[0][1]})")

            # 促销价：如果有多个候选，选择较小的（且不能太小）
            if promo_candidates:
                # 过滤掉明显太小的价格（<= 20，可能是优惠金额）
                valid_promo = [c for c in promo_candidates if c[0] > 20]
                if valid_promo:
                    # 按价格升序排序，取最小的
                    valid_promo.sort(key=lambda x: x[0])
                    prices['promo'] = valid_promo[0][0]
                    print(f"  找到促销价: ¥{prices['promo']} (标注: {valid_promo[0][1]})")

            # 第三步：如果没有通过关键词找到，尝试 class
            if not prices['promo']:
                for item in all_prices:
                    price = item['price']
                    class_name = item.get('className', '')
                    parent_class = item.get('parentClassName', '')
                    if 'price' in class_name.lower() or 'price' in parent_class.lower():
                        if not prices['promo'] and price > 20:
                            prices['promo'] = price
                            print(f"  找到促销价: ¥{price} (price class)")
                            break

            # 第四步：如果通过关键词没找全，使用价格大小判断
            if all_prices and (not prices['original'] or not prices['promo']):
                # 按价格排序
                sorted_prices = sorted([item['price'] for item in all_prices])

                # 特殊情况：如果已有促销价但无原价，找比促销价大的候选
                if prices['promo'] and not prices['original']:
                    # 先尝试找有删除线或明确标注的原价
                    larger_items = [item for item in all_prices if item['price'] > prices['promo']]

                    # 优先选择有删除线的
                    del_items = [item for item in larger_items if item.get('isDel', False)]
                    if del_items:
                        # 如果有多个删除线价格，选择最大的
                        del_items.sort(key=lambda x: x['price'], reverse=True)
                        prices['original'] = del_items[0]['price']
                        print(f"  找到原价: ¥{prices['original']} (删除线标注)")
                    else:
                        # 没有删除线，选择比促销价大的最大值（原价通常是最高的）
                        larger_prices = [item['price'] for item in larger_items]
                        if larger_prices:
                            prices['original'] = max(larger_prices)
                            print(f"  找到原价: ¥{prices['original']} (比促销价大的最大值)")
                # 特殊情况：如果已有原价但无促销价，找比原价小的候选
                elif prices['original'] and not prices['promo']:
                    smaller_prices = [p for p in sorted_prices if p < prices['original'] and p > 20]
                    if smaller_prices:
                        # 选择比原价小的最大值作为促销价
                        prices['promo'] = max(smaller_prices)
                        print(f"  找到促销价: ¥{prices['promo']} (比原价小的最大值)")
                    else:
                        prices['promo'] = prices['original']
                        print(f"  无促销，使用原价")
                # 都没有：使用原来的逻辑
                elif len(sorted_prices) <= 5:
                    # 如果只有一个价格
                    if len(sorted_prices) == 1:
                        price = sorted_prices[0]
                        if not prices['promo']:
                            prices['promo'] = price
                            print(f"  找到价格: ¥{price} (仅一个价格)")
                        if not prices['original']:
                            prices['original'] = price
                    # 如果有2-5个价格
                    elif 2 <= len(sorted_prices) <= 5:
                        # 取最小和最大的两个（通常是促销价和原价）
                        min_price = sorted_prices[0]
                        max_price = sorted_prices[-1]

                        # 如果两个价格不同，且差异合理（不超过2倍）
                        if min_price != max_price and max_price <= min_price * 2:
                            if not prices['promo']:
                                prices['promo'] = min_price
                                print(f"  找到促销价: ¥{min_price} (最低价)")
                            if not prices['original']:
                                prices['original'] = max_price
                                print(f"  找到原价: ¥{max_price} (最高价)")
                        # 如果价格差异太大，只用最小价格
                        elif min_price != max_price:
                            if not prices['promo']:
                                prices['promo'] = min_price
                                print(f"  找到价格: ¥{min_price} (价格差异过大，只取最小值)")
                            if not prices['original']:
                                prices['original'] = min_price
                        # 如果只有一个价格值（多个元素显示相同价格）
                        else:
                            if not prices['promo']:
                                prices['promo'] = min_price
                                print(f"  找到价格: ¥{min_price}")
                            if not prices['original']:
                                prices['original'] = min_price
                else:
                    print(f"  ⚠️  价格候选过多({len(sorted_prices)}个)，跳过大小判断")

            # 最终价格验证和处理
            # 1. 处理只找到一个价格的情况
            if prices['promo'] and not prices['original']:
                # 只找到促销价，但商品一定有常规价格
                # 这个价格很可能就是常规价格，只是提取位置判断错误
                print(f"  只找到一个价格(在促销位置)，视为常规价格")
                prices['original'] = prices['promo']
                # 促销价保持不变，表示当前售价
            elif prices['original'] and not prices['promo']:
                # 只找到原价，说明没有促销活动
                print(f"  只找到原价，无促销活动，使用相同价格")
                prices['promo'] = prices['original']

            # 2. 最终价格验证
            if prices['original'] or prices['promo']:
                # 验证价格合理性
                original = prices['original']
                promo = prices['promo']

                # 价格必须在合理范围内 (10-100000)
                if original and (original < 10 or original > 100000):
                    print(f"  ⚠️  原价异常: ¥{original}，忽略")
                    prices['original'] = None

                if promo and (promo < 10 or promo > 100000):
                    print(f"  ⚠️  促销价异常: ¥{promo}，忽略")
                    prices['promo'] = None

                # 如果促销价 > 原价，说明识别错误，交换
                if prices['original'] and prices['promo']:
                    if prices['promo'] > prices['original']:
                        print(f"  ⚠️  促销价(¥{prices['promo']})高于原价(¥{prices['original']})，交换")
                        prices['original'], prices['promo'] = prices['promo'], prices['original']

                # 返回结果
                if prices['promo'] or prices['original']:
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
