#!/usr/bin/env python3
"""
天猫 / 淘宝 价格爬虫
- 用 undetected-chromedriver 规避检测
- 每次启动扫码登录(以稳为主,不复用 cookie)
- 主路径:从 window.__ICE_APP_CONTEXT__ 提取 SSR 数据
- DOM 兜底:抓含 ¥ 的文本节点

接口对齐 JDCrawlerViaSearch:
    __init__ / login / is_session_valid / restart_browser / close
    + get_price(item_id) -> dict
"""
import warnings
warnings.filterwarnings('ignore', message='urllib3 v2 only supports OpenSSL 1.1.1+')

import os
import re
import time
import random
import subprocess
from typing import Optional
from urllib.parse import urlparse, parse_qs

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait


def _detect_chrome_version() -> Optional[int]:
    paths = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
    ]
    for p in paths:
        if os.path.exists(p):
            try:
                out = subprocess.check_output([p, "--version"], stderr=subprocess.DEVNULL, text=True)
                m = re.search(r"(\d+)\.", out)
                if m:
                    return int(m.group(1))
            except Exception:
                continue
    return None


def parse_tmall_item_id(url: str) -> Optional[str]:
    """从天猫/淘宝商品 URL 提取 item_id(`?id=xxx` 那段数字)"""
    if not url:
        return None
    try:
        qs = parse_qs(urlparse(url).query)
        if 'id' in qs and qs['id']:
            return qs['id'][0]
    except Exception:
        pass
    m = re.search(r'[?&]id=(\d+)', url)
    return m.group(1) if m else None


def _safe_get(d, *path, default=None):
    cur = d
    for p in path:
        if not isinstance(cur, dict) or p not in cur:
            return default
        cur = cur[p]
    return cur


class TmallCrawler:
    """天猫/淘宝商品价格爬虫"""

    def __init__(self, headless: bool = False):
        self.headless = headless
        self.driver = None
        self.is_logged_in = False
        self._init_driver()

    def _init_driver(self):
        try:
            options = uc.ChromeOptions()
            if self.headless:
                options.add_argument('--headless=new')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--window-size=1366,900')
            options.add_argument('--lang=zh-CN')

            cv = _detect_chrome_version()
            print(f'  [Tmall] 初始化浏览器... (Chrome v{cv or "?"})')
            t0 = time.time()
            self.driver = uc.Chrome(options=options, version_main=cv)
            self.driver.implicitly_wait(3)
            print(f'  [Tmall] ✓ 浏览器启动成功 ({time.time()-t0:.1f}秒)')
        except Exception as e:
            print(f'  [Tmall] 初始化驱动失败: {e}')
            raise

    def _check_login_state(self) -> bool:
        """访问 i.taobao.com 判断登录态 — 未登录会强制跳转 login.taobao.com"""
        try:
            self.driver.get('https://i.taobao.com/my_taobao.htm')
            time.sleep(random.uniform(1.5, 2.5))
            url = self.driver.current_url or ''
            if 'login.taobao' in url or 'login.tmall' in url:
                return False
            try:
                nick = self.driver.find_element(
                    By.CSS_SELECTOR,
                    '#J_userNick, .site-nav-user, [class*="user-nick"]'
                ).text.strip()
                return bool(nick) and '请登录' not in nick
            except Exception:
                pass
            return 'i.taobao.com' in url
        except Exception as e:
            print(f'  [Tmall] 登录态检查失败: {e}')
            return False

    def _detect_slider(self) -> bool:
        """检测是否弹了滑块/异常流量验证"""
        try:
            src = self.driver.page_source
            return any(k in src for k in [
                'slide to verify', '滑动验证', 'unusual traffic',
                'punish', '_!!nc_iconfont', 'nc-container'
            ])
        except Exception:
            return False

    def login(self, timeout: int = 240, slider_callback=None) -> bool:
        """打开淘宝登录页,引导扫码(必要时先手动过滑块).

        Args:
            timeout: 总超时(秒) — 滑块+扫码总时间
            slider_callback: 检测到滑块时调用一次(用于前端提示)
        """
        print('\n' + '=' * 60)
        print('  [Tmall] 需要扫码登录淘宝/天猫账号')
        print('=' * 60)
        print('  浏览器将打开淘宝登录页,请用【手机淘宝 App】扫码登录')
        print('  如果先看到"滑动验证"页,请用鼠标拖动滑块完成验证,再扫码')
        print('=' * 60)

        try:
            self.driver.get('https://login.taobao.com/member/login.jhtml')
        except Exception as e:
            print(f'  [Tmall] 打开登录页失败: {e}')
            self.is_logged_in = False
            return False

        deadline = time.time() + timeout
        slider_notified = False
        while time.time() < deadline:
            time.sleep(2)
            try:
                cur = self.driver.current_url
            except Exception:
                continue

            # 检测滑块 — 只提醒一次,不阻断流程(用户拖完滑块后页面会自然回到登录态)
            if not slider_notified and self._detect_slider():
                msg = '⚠️ 检测到滑动验证,请在浏览器窗口中用鼠标拖动滑块完成验证(然后再扫码)'
                print(f'  [Tmall] {msg}')
                if slider_callback:
                    try:
                        slider_callback(msg)
                    except Exception:
                        pass
                slider_notified = True

            if 'login' not in cur:
                time.sleep(2)
                if self._check_login_state():
                    print('  [Tmall] ✓ 登录成功')
                    self.is_logged_in = True
                    return True

        print('  [Tmall] ✗ 登录超时')
        self.is_logged_in = False
        return False

    def _extract_from_ssr(self) -> Optional[dict]:
        """从 window.__ICE_APP_CONTEXT__ 提取价格 + 商品信息"""
        try:
            ctx = self.driver.execute_script("return window.__ICE_APP_CONTEXT__ || null;")
        except Exception as e:
            return {'_error': f'execute_script failed: {e}'}

        if not ctx:
            return None

        res = _safe_get(ctx, 'loaderData', 'home', 'data', 'res')
        if not res:
            return {'_error': 'no loaderData.home.data.res'}

        comp = _safe_get(res, 'componentsVO', default={})
        price_vo = _safe_get(comp, 'priceVO', default={})
        title_vo = _safe_get(comp, 'titleVO', default={})
        store_vo = _safe_get(comp, 'storeCardVO', default={})

        op_text = _safe_get(price_vo, 'price', 'priceText')
        op_desc = _safe_get(price_vo, 'price', 'priceDesc') or ''
        op_title = _safe_get(price_vo, 'price', 'priceTitle') or '原价'
        pp_text = _safe_get(price_vo, 'extraPrice', 'priceText')
        pp_desc = _safe_get(price_vo, 'extraPrice', 'priceDesc') or ''
        pp_title = _safe_get(price_vo, 'extraPrice', 'priceTitle') or '券后'

        if not op_text and not pp_text:
            return {'_error': 'priceVO empty in SSR context'}

        return {
            'original': f'{op_text}{op_desc}' if op_text else None,
            'promo': f'{pp_text}{pp_desc}' if pp_text else None,
            'original_label': op_title,
            'promo_label': pp_title,
            'title': _safe_get(title_vo, 'title', 'title') or _safe_get(res, 'item', 'title'),
            'shop': _safe_get(store_vo, 'shopName') or _safe_get(res, 'seller', 'shopName'),
            'sales': _safe_get(title_vo, 'salesDesc'),
        }

    def _wait_for_ssr(self, timeout: int = 12) -> bool:
        """等待 SSR context 注入到 window"""
        try:
            WebDriverWait(self.driver, timeout).until(
                lambda d: d.execute_script(
                    'return !!(window.__ICE_APP_CONTEXT__ && '
                    'window.__ICE_APP_CONTEXT__.loaderData);'
                )
            )
            return True
        except Exception:
            return False

    def _diagnose(self) -> str:
        """抽取失败时收集诊断信息"""
        try:
            cur = (self.driver.current_url or '')[:90]
            title = (self.driver.title or '')[:60]
            src = self.driver.page_source or ''
            src_len = len(src)
            has_slider = self._detect_slider()
            has_login = 'login.taobao' in cur or 'login.tmall' in cur
            has_ice = '__ICE_APP_CONTEXT__' in src
            return (f'url="{cur}" title="{title}" '
                    f'src_len={src_len} slider={has_slider} '
                    f'login_redirect={has_login} ice_ctx_in_html={has_ice}')
        except Exception as e:
            return f'diagnose_error: {e}'

    def get_price(self, item_id: str) -> Optional[dict]:
        """
        访问商品页提取价格,返回与 JD 对齐的 dict.

        Returns:
            成功: {'original','promo','title','shop','original_label','promo_label'}
            失败: 含 status 标记的占位 dict(blocked/not_found/slider) 或 (None,None,_diag)
        """
        if not self.is_logged_in:
            print('  [Tmall] ✗ 未登录')
            return None

        if not item_id:
            return None

        # item.taobao.com 对淘宝(C 店,9 位 id)和天猫(12 位 id)商品都通用 —
        # 天猫商品会自动 302 到 detail.tmall.com,SSR 数据一致.
        # 而 detail.tmall.com 只认天猫商品,淘宝 C 店 id 会被路由到 error 页.
        url = f'https://item.taobao.com/item.htm?id={item_id}'

        try:
            # 1) 确保当前在淘宝域名下(从首页跳转更像真人导航)
            try:
                cur_url = self.driver.current_url or ''
            except Exception:
                cur_url = ''
            if 'taobao.com' not in cur_url and 'tmall.com' not in cur_url:
                self.driver.get('https://www.taobao.com')
                time.sleep(random.uniform(1.2, 2.0))

            # 2) 用 JS location.href 跳转 — 跟用户点击站内链接的 navigation 路径更接近
            #    比 driver.get 更难被识别为自动化
            self.driver.execute_script(f"window.location.href = {repr(url)};")
        except Exception as e:
            print(f'  [Tmall] 导航失败: {e}')
            return None

        ssr_ok = self._wait_for_ssr(timeout=12)
        time.sleep(random.uniform(0.8, 1.5))
        ssr = self._extract_from_ssr() if ssr_ok else None

        cur = self.driver.current_url or ''
        title = self.driver.title or ''

        # 登录跳转 -> 重试一次
        if (not ssr or ssr.get('_error')) and ('login.taobao' in cur or '登录' in title):
            print(f'  [Tmall] 检测到登录跳转,重试...')
            time.sleep(random.uniform(2.0, 4.0))
            try:
                self.driver.get(url)
                ssr_ok = self._wait_for_ssr(timeout=12)
                time.sleep(random.uniform(0.8, 1.5))
                ssr = self._extract_from_ssr() if ssr_ok else None
                cur = self.driver.current_url or ''
                title = self.driver.title or ''
            except Exception as e:
                print(f'  [Tmall] 重试失败: {e}')

        # 拦截页 (title 含验证/滑块/Punish, 或 URL 跳到 punish/security)
        blocked_keys = ['验证', '滑块', '安全', 'Punish']
        if any(k in title for k in blocked_keys) or 'punish' in cur or 'security' in cur:
            print(f'  [Tmall] ⚠️ 被拦截: {title[:30]}')
            return {'original': 'blocked', 'promo': 'blocked', '_diag': self._diagnose()}

        # 隐式滑块(modal 形式,title 不变但页面 source 有 nc-container)
        if self._detect_slider():
            print(f'  [Tmall] ⚠️ 检测到滑块拦截(隐式)')
            return {'original': 'slider', 'promo': 'slider', '_diag': self._diagnose()}

        # SSR 抽取成功
        if ssr and not ssr.get('_error'):
            print(f'  [Tmall] ✓ {ssr.get("original_label")}: ¥{ssr.get("original")} | '
                  f'{ssr.get("promo_label")}: ¥{ssr.get("promo")}')
            return ssr

        # 商品下架
        try:
            psrc = self.driver.page_source
        except Exception:
            psrc = ''
        if '商品不存在' in psrc or 'item is invalid' in psrc.lower():
            return {'original': 'not_found', 'promo': 'not_found'}

        # 兜底:抽取失败 + 诊断
        diag = self._diagnose()
        print(f'  [Tmall] ⚠️ 抽取失败 | {diag}')
        return {'original': None, 'promo': None, '_diag': diag}

    def is_session_valid(self) -> bool:
        try:
            _ = self.driver.current_url
            return True
        except Exception:
            return False

    def restart_browser(self) -> bool:
        print('\n  [Tmall] ⚠️ 浏览器会话失效,重启中...')
        try:
            if self.driver:
                self.driver.quit()
        except Exception:
            pass
        self.driver = None
        self.is_logged_in = False
        self._init_driver()
        ok = self.login()
        if ok:
            print('  [Tmall] ✓ 重启 + 重新登录成功\n')
        else:
            print('  [Tmall] ✗ 重新登录失败\n')
        return ok

    def close(self):
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            finally:
                self.driver = None
        # 清理残留 chrome 子进程
        try:
            import psutil
            current_process = psutil.Process(os.getpid())
            for child in current_process.children(recursive=True):
                try:
                    if 'chrome' in child.name().lower():
                        child.terminate()
                except Exception:
                    pass
        except ImportError:
            pass
        except Exception:
            pass
