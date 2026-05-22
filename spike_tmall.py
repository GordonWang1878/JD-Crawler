#!/usr/bin/env python3
"""
Spike: 天猫 / 淘宝价格抓取可行性验证
- 用 undetected-chromedriver 规避检测
- 首次扫码登录,Cookie 持久化到 taobao_cookies.pkl,后续复用
- 对每个 URL:打开详情页 -> 等待价格元素 -> 提取多个候选价格 -> 打印结果

运行: python3 spike_tmall.py
"""
import warnings
warnings.filterwarnings('ignore', message='urllib3 v2 only supports OpenSSL 1.1.1+')

import os
import re
import sys
import time
import json
import pickle
import random
import argparse
import subprocess
from typing import Optional, List, Dict
from urllib.parse import urlparse, parse_qs

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


COOKIES_FILE = 'taobao_cookies.pkl'  # 兜底备份(主要靠 PROFILE_DIR)
PROFILE_DIR = 'taobao_chrome_profile'  # Chrome 持久化用户配置(cookie+localStorage+缓存)

# 测试 URL — 可通过命令行覆盖
DEFAULT_URLS = [
    'https://detail.tmall.com/item.htm?id=864497080438',
    'https://detail.tmall.com/item.htm?id=634015385434',
    'https://detail.tmall.com/item.htm?id=817030084492',
]


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


def init_driver(headless: bool = False) -> uc.Chrome:
    """每次启动一个全新的 Chrome — 以稳为主,不复用登录态(天猫反爬太狠,
    profile 复用会触发二次确认页,不如直接每次扫码 10 秒来得稳)"""
    options = uc.ChromeOptions()
    if headless:
        options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1366,900')
    options.add_argument('--lang=zh-CN')

    cv = _detect_chrome_version()
    print(f'[init] Chrome v{cv or "?"} — starting undetected-chromedriver ...')
    t0 = time.time()
    driver = uc.Chrome(options=options, version_main=cv)
    driver.implicitly_wait(3)
    print(f'[init] driver ready in {time.time()-t0:.1f}s')
    return driver


def load_cookies(driver: uc.Chrome) -> bool:
    if not os.path.exists(COOKIES_FILE):
        return False
    try:
        driver.get('https://www.taobao.com')
        time.sleep(2)
        with open(COOKIES_FILE, 'rb') as f:
            cookies = pickle.load(f)
        for c in cookies:
            c.pop('sameSite', None)
            c.pop('expiry', None)
            try:
                driver.add_cookie(c)
            except Exception:
                continue
        print(f'[cookie] loaded {len(cookies)} cookies from {COOKIES_FILE}')
        return True
    except Exception as e:
        print(f'[cookie] load failed: {e}')
        return False


def save_cookies(driver: uc.Chrome):
    try:
        cookies = driver.get_cookies()
        with open(COOKIES_FILE, 'wb') as f:
            pickle.dump(cookies, f)
        print(f'[cookie] saved {len(cookies)} cookies -> {COOKIES_FILE}')
    except Exception as e:
        print(f'[cookie] save failed: {e}')


def is_logged_in(driver: uc.Chrome) -> bool:
    """通过访问 i.taobao.com(个人中心)判断登录态 — 未登录会强制跳转到 login.taobao.com"""
    try:
        driver.get('https://i.taobao.com/my_taobao.htm')
        time.sleep(random.uniform(1.5, 2.5))
        url = driver.current_url or ''
        if 'login.taobao' in url or 'login.tmall' in url:
            return False
        # 二次确认:i.taobao.com 仅登录用户可见,有 nick 元素
        try:
            nick = driver.find_element(By.CSS_SELECTOR, '#J_userNick, .site-nav-user, [class*="user-nick"]').text.strip()
            return bool(nick) and '请登录' not in nick
        except Exception:
            pass
        # 兜底:URL 没跳走就视为已登录(更严格的判断已被 URL 检查覆盖)
        return 'i.taobao.com' in url
    except Exception as e:
        print(f'[login] check failed: {e}')
        return False


def login_flow(driver: uc.Chrome):
    """引导手机扫码登录"""
    print('\n' + '=' * 60)
    print('需要登录淘宝/天猫账号')
    print('=' * 60)
    print('  浏览器将打开淘宝登录页,请使用【手机淘宝 App】扫码登录')
    print('  登录后请勿关闭浏览器,程序会自动检测登录态')
    print('=' * 60 + '\n')

    driver.get('https://login.taobao.com/member/login.jhtml')
    deadline = time.time() + 180  # 3 分钟超时
    while time.time() < deadline:
        time.sleep(2)
        cur = driver.current_url
        if 'login' not in cur:
            print('[login] detected redirect away from login page')
            time.sleep(2)
            if is_logged_in(driver):
                print('[login] ✓ logged in')
                return True
    print('[login] ✗ timeout — please retry')
    return False


def _safe_get(d, *path, default=None):
    """安全嵌套 dict 访问"""
    cur = d
    for p in path:
        if not isinstance(cur, dict) or p not in cur:
            return default
        cur = cur[p]
    return cur


def extract_from_ssr(driver: uc.Chrome) -> Optional[dict]:
    """从 window.__ICE_APP_CONTEXT__ 提取结构化商品数据(主路径)"""
    js = "return window.__ICE_APP_CONTEXT__ || null;"
    try:
        ctx = driver.execute_script(js)
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

    out = {
        'title': _safe_get(title_vo, 'title', 'title')
                 or _safe_get(res, 'item', 'title'),
        'sales': _safe_get(title_vo, 'salesDesc'),
        'shop': _safe_get(store_vo, 'shopName')
                or _safe_get(res, 'seller', 'shopName'),
        'original_price': {
            'text': _safe_get(price_vo, 'price', 'priceText'),
            'desc': _safe_get(price_vo, 'price', 'priceDesc'),
            'title': _safe_get(price_vo, 'price', 'priceTitle'),
        },
        'promo_price': {
            'text': _safe_get(price_vo, 'extraPrice', 'priceText'),
            'desc': _safe_get(price_vo, 'extraPrice', 'priceDesc'),
            'title': _safe_get(price_vo, 'extraPrice', 'priceTitle'),
        },
    }
    # 没有 priceText 视为无效
    if not out['original_price']['text'] and not out['promo_price']['text']:
        return {'_error': 'priceVO empty in SSR context'}
    return out


def extract_from_dom(driver: uc.Chrome) -> List[dict]:
    """DOM 兜底:抓含 ¥ 的文本节点"""
    js = r"""
    const out = [];
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, null);
    let n;
    while ((n = walker.nextNode()) && out.length < 20) {
        const t = (n.nodeValue || '').trim();
        if (t && (t.includes('¥') || t.includes('￥'))) {
            const parent = n.parentElement;
            const cls = parent ? (parent.className || '') : '';
            out.push({ text: t, cls: String(cls).slice(0, 60) });
        }
    }
    return out;
    """
    try:
        return driver.execute_script(js) or []
    except Exception:
        return []


def parse_item_id(url: str) -> Optional[str]:
    try:
        qs = parse_qs(urlparse(url).query)
        if 'id' in qs and qs['id']:
            return qs['id'][0]
    except Exception:
        pass
    m = re.search(r'[?&]id=(\d+)', url)
    return m.group(1) if m else None


def _try_extract(driver: uc.Chrome, wait_for_ssr: bool = True) -> Optional[dict]:
    """等待 SSR context 出现并提取"""
    if wait_for_ssr:
        try:
            WebDriverWait(driver, 12).until(
                lambda d: d.execute_script(
                    'return !!(window.__ICE_APP_CONTEXT__ && '
                    'window.__ICE_APP_CONTEXT__.loaderData);'
                )
            )
        except Exception:
            return None
    time.sleep(random.uniform(0.8, 1.5))
    return extract_from_ssr(driver)


def crawl_one(driver: uc.Chrome, url: str) -> dict:
    item_id = parse_item_id(url)
    print(f'\n--- crawling: {url}')
    print(f'    item_id: {item_id}')

    try:
        driver.get(url)
    except Exception as e:
        return {'url': url, 'error': f'navigation failed: {e}'}

    ssr = _try_extract(driver, wait_for_ssr=True)
    cur = driver.current_url or ''
    title = driver.title or ''

    # 检测登录跳转 -> 刷新重试一次
    if (not ssr or ssr.get('_error')) and ('login.taobao' in cur or '登录' in title):
        print(f'    ! login redirect detected, refreshing...')
        time.sleep(random.uniform(2.0, 4.0))
        try:
            driver.get(url)  # 直接重新 get,而不是 refresh(避免保留 login_jump 参数)
            ssr = _try_extract(driver, wait_for_ssr=True)
            cur = driver.current_url or ''
            title = driver.title or ''
        except Exception as e:
            print(f'    ! retry failed: {e}')

    # 检测拦截 / 滑块
    blocked_keys = ['验证', '滑块', '安全', 'Punish']
    if any(k in title for k in blocked_keys) or 'punish' in cur or 'security' in cur:
        print(f'    ! BLOCKED: title="{title}" url={cur[:80]}')
        return {'url': url, 'item_id': item_id, 'status': 'blocked',
                'title': title, 'landing_url': cur}

    result = {
        'url': url,
        'item_id': item_id,
        'title': title,
        'landing_url': cur,
    }

    if ssr and not ssr.get('_error'):
        result['status'] = 'ok'
        result['ssr'] = ssr
        # 打印精简价格
        op = ssr.get('original_price', {})
        pp = ssr.get('promo_price', {})
        op_str = f"¥{op.get('text', '?')}{op.get('desc') or ''}" if op.get('text') else '-'
        pp_str = f"¥{pp.get('text', '?')}{pp.get('desc') or ''}" if pp.get('text') else '-'
        print(f'    ✓ {ssr.get("title", "")[:50]}')
        print(f'      {op.get("title", "原价")}: {op_str}  |  {pp.get("title", "促销")}: {pp_str}')
        print(f'      店铺: {ssr.get("shop")}  销量: {ssr.get("sales")}')
    else:
        result['status'] = 'no_price'
        result['ssr_error'] = ssr.get('_error') if ssr else 'no ssr context'
        result['dom_yen_nodes'] = extract_from_dom(driver)
        print(f'    ✗ extract failed: {result["ssr_error"]}')

    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('urls', nargs='*', help='天猫/淘宝商品 URL(可多个)')
    parser.add_argument('--headless', action='store_true', help='headless 模式(不推荐,登录需要 GUI)')
    parser.add_argument('--no-login', action='store_true', help='跳过登录检查,直接爬(用于测试匿名访问)')
    args = parser.parse_args()

    urls = args.urls or DEFAULT_URLS
    print(f'\n[spike] will crawl {len(urls)} url(s)\n')

    driver = init_driver(headless=args.headless)

    try:
        if not args.no_login:
            print('[login] 天猫反爬强制每次扫码,请准备好手机淘宝 App')
            ok = login_flow(driver)
            if not ok:
                print('[spike] aborting: login required')
                return 1

        results = []
        for url in urls:
            r = crawl_one(driver, url)
            results.append(r)
            time.sleep(random.uniform(4.0, 7.0))

        # 打印精简结果
        print('\n' + '=' * 60)
        print('SUMMARY')
        print('=' * 60)
        ok_count = sum(1 for r in results if r.get('status') == 'ok')
        print(f'  Success: {ok_count}/{len(results)}\n')
        for r in results:
            status = r.get('status', '?')
            print(f'[{status:8s}] item_id={r.get("item_id")}')
            if r.get('ssr'):
                s = r['ssr']
                op = s.get('original_price', {})
                pp = s.get('promo_price', {})
                print(f'           标题: {(s.get("title") or "")[:60]}')
                print(f'           店铺: {s.get("shop")}')
                op_t = f'¥{op["text"]}{op.get("desc") or ""}' if op.get('text') else '-'
                pp_t = f'¥{pp["text"]}{pp.get("desc") or ""}' if pp.get('text') else '-'
                print(f'           {op.get("title") or "原价"}: {op_t}  |  {pp.get("title") or "券后"}: {pp_t}')
            elif r.get('ssr_error'):
                print(f'           reason: {r["ssr_error"]}')
            print()

        # 完整结果写盘,便于排查
        out_path = 'spike_tmall_result.json'
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f'\n[spike] full results -> {out_path}')

    finally:
        input('\n按回车关闭浏览器...')
        try:
            driver.quit()
        except Exception:
            pass
    return 0


if __name__ == '__main__':
    sys.exit(main())
