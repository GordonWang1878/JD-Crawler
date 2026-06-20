#!/usr/bin/env python3
"""Web 端 JD 账号池配置 —— 替代终端的 prepare_jd_profile_pool_patchright.py。

启一个可见的 patchright chromium 让用户扫码,后台轮询登录态(不阻塞在 input()),
全程通过传入的 emit 回调把状态推到前端。同时提供 冷却/恢复、移除、验证登录、列表。

设计要点:
- 与批量爬虫的 crawler_instance 完全隔离:每次扫码/验证用独立线程 + 独立 sync_playwright。
- 全局只允许一个配置操作在进行(_state['busy']),且调用方需保证「爬取中」不触发配置。
- profile 与账号 1:1:扫码成功时把昵称写进 profile_N/.jd_account.json 旁车文件,
  列表直接读旁车、无需每次启浏览器。
"""
import os
import re
import json
import time
import threading
from typing import Optional, Callable

from patchright.sync_api import sync_playwright

import jd_profile_pool

POOL_DIR = jd_profile_pool.POOL_DIR
SIDECAR = '.jd_account.json'
SCAN_TIMEOUT = 180          # 扫码最多等 180s
LAUNCH_ARGS = [
    '--no-first-run',
    '--no-default-browser-check',
    '--disable-blink-features=AutomationControlled',
    '--lang=zh-CN',
]

# 全局配置状态(同一时刻只允许一个扫码/验证操作)
_LOCK = threading.Lock()
_state = {'busy': False, 'profile_id': None, 'action': None, 'cancel': False}


# ---------- 路径 / 旁车 ----------

def _ppath(pid: int, suffix: str = '') -> str:
    return os.path.join(POOL_DIR, f'profile_{pid}{suffix}')


def _read_sidecar(path: str) -> dict:
    try:
        with open(os.path.join(path, SIDECAR), encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def _write_sidecar(path: str, nickname: Optional[str], ts: str) -> None:
    try:
        with open(os.path.join(path, SIDECAR), 'w', encoding='utf-8') as f:
            json.dump({'nickname': nickname, 'scanned_at': ts}, f, ensure_ascii=False)
    except Exception:
        pass


# ---------- 查询 ----------

def list_profiles_status() -> list:
    """列出所有 profile 槽位 + 状态(不启浏览器,只读目录与旁车)。"""
    os.makedirs(POOL_DIR, exist_ok=True)
    out = []
    for name in os.listdir(POOL_DIR):
        m = re.match(r'^profile_(\d+)(\.cooldown)?$', name)
        if not m:
            continue
        path = os.path.join(POOL_DIR, name)
        if not os.path.isdir(path):
            continue
        side = _read_sidecar(path)
        out.append({
            'id': int(m.group(1)),
            'cooldown': bool(m.group(2)),
            # 有 Default 子目录 = 曾经登录过(旧数据可能无旁车)
            'configured': os.path.isdir(os.path.join(path, 'Default')),
            'nickname': side.get('nickname'),
            'scanned_at': side.get('scanned_at'),
        })
    out.sort(key=lambda x: x['id'])
    return out


def next_free_id() -> int:
    """下一个空闲 profile 编号(填补空缺)。"""
    used = set()
    if os.path.isdir(POOL_DIR):
        for name in os.listdir(POOL_DIR):
            m = re.match(r'^profile_(\d+)(\.cooldown)?$', name)
            if m:
                used.add(int(m.group(1)))
    i = 1
    while i in used:
        i += 1
    return i


def is_busy() -> bool:
    return _state['busy']


# ---------- 登录检测(复用 home.jd.com 非风控页) ----------

def _check_login(page):
    """访问「我的京东」判断登录态并尽量抓昵称。返回 (logged_in, nickname)。"""
    try:
        page.goto('https://home.jd.com/', wait_until='domcontentloaded', timeout=15000)
        time.sleep(1.2)
        cur = (page.url or '').lower()
        title = page.title() or ''
        if '登录' in title or 'passport' in cur or 'login' in cur:
            return False, None
        nickname = None
        for sel in ('.nickname', '#aliasName', '.user-name', '.u-name', '.user-info .name'):
            try:
                el = page.query_selector(sel)
                if el:
                    txt = (el.inner_text() or '').strip()
                    if txt:
                        nickname = txt
                        break
            except Exception:
                pass
        return True, nickname
    except Exception:
        return False, None


# ---------- 扫码 / 验证(后台线程) ----------

def cancel() -> None:
    _state['cancel'] = True


def start_scan(profile_id: int, emit: Callable, before_launch: Optional[Callable] = None,
               on_done: Optional[Callable] = None) -> tuple:
    """启动扫码流程(后台线程)。emit(event, data) 推状态。返回 (ok, err)。"""
    with _LOCK:
        if _state['busy']:
            return False, '已有账号配置操作在进行,请稍候'
        _state.update(busy=True, profile_id=profile_id, action='scan', cancel=False)
    threading.Thread(target=_scan_worker,
                     args=(profile_id, emit, before_launch, on_done),
                     daemon=True).start()
    return True, ''


def start_verify(profile_id: int, emit: Callable, before_launch: Optional[Callable] = None,
                 on_done: Optional[Callable] = None) -> tuple:
    """验证某 profile 登录是否仍有效(启浏览器查一次即关)。返回 (ok, err)。"""
    with _LOCK:
        if _state['busy']:
            return False, '已有账号配置操作在进行,请稍候'
        _state.update(busy=True, profile_id=profile_id, action='verify', cancel=False)
    threading.Thread(target=_verify_worker,
                     args=(profile_id, emit, before_launch, on_done),
                     daemon=True).start()
    return True, ''


def _emit_status(emit, pid, stage, msg, **extra):
    emit('profile_scan', {'id': pid, 'stage': stage, 'message': msg, **extra})


def _scan_worker(pid, emit, before_launch, on_done):
    try:
        if before_launch:
            before_launch()   # app 层清残留 chromium + 清 crawler 单例,避免锁冲突
        # 若该 profile 处于 .cooldown,扫码即重新启用 → 用回正常名
        pdir, cdir = _ppath(pid), _ppath(pid, '.cooldown')
        if os.path.isdir(cdir) and not os.path.isdir(pdir):
            os.rename(cdir, pdir)
        os.makedirs(pdir, exist_ok=True)

        _emit_status(emit, pid, 'launching', '启动浏览器…')
        with sync_playwright() as p:
            ctx = p.chromium.launch_persistent_context(
                user_data_dir=pdir, headless=False, channel='chromium',
                no_viewport=True, args=LAUNCH_ARGS)
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            try:
                page.goto('https://passport.jd.com/new/login.aspx', timeout=30000)
            except Exception:
                pass
            _emit_status(emit, pid, 'waiting', '请在弹出的窗口用京东 App 扫码登录…')

            ok, nickname = False, None
            deadline = time.time() + SCAN_TIMEOUT
            while time.time() < deadline:
                if _state['cancel']:
                    _emit_status(emit, pid, 'cancelled', '已取消')
                    break
                time.sleep(3)
                logged, nick = _check_login(page)
                if logged:
                    ok, nickname = True, nick
                    break
                _emit_status(emit, pid, 'waiting', '等待扫码…',
                             remaining=max(0, int(deadline - time.time())))

            if ok:
                ts = time.strftime('%Y-%m-%d %H:%M')
                _write_sidecar(pdir, nickname or '已登录', ts)
                _emit_status(emit, pid, 'success',
                             f'✓ 登录成功:{nickname or "(未取到昵称)"}',
                             nickname=nickname, scanned_at=ts)
            elif not _state['cancel']:
                _emit_status(emit, pid, 'timeout', f'✗ 等待扫码超时({SCAN_TIMEOUT}s),未登录')

            try:
                ctx.close()
            except Exception:
                pass
    except Exception as e:
        _emit_status(emit, pid, 'error', f'扫码出错:{e}')
    finally:
        with _LOCK:
            _state.update(busy=False, profile_id=None, action=None, cancel=False)
        if on_done:
            on_done()


def _verify_worker(pid, emit, before_launch, on_done):
    try:
        if before_launch:
            before_launch()
        pdir = _ppath(pid)
        if not os.path.isdir(pdir):
            pdir = _ppath(pid, '.cooldown')
        if not os.path.isdir(pdir):
            _emit_status(emit, pid, 'error', 'profile 不存在')
            return
        _emit_status(emit, pid, 'verifying', '验证登录态…')
        with sync_playwright() as p:
            ctx = p.chromium.launch_persistent_context(
                user_data_dir=pdir, headless=False, channel='chromium',
                no_viewport=True, args=LAUNCH_ARGS)
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            logged, nick = _check_login(page)
            if logged:
                ts = time.strftime('%Y-%m-%d %H:%M')
                # 旁车里的昵称以新抓到的为准(抓不到则保留旧的)
                old = _read_sidecar(pdir)
                _write_sidecar(pdir, nick or old.get('nickname') or '已登录', ts)
                _emit_status(emit, pid, 'verified_ok',
                             f'✓ 登录有效:{nick or old.get("nickname") or "已登录"}',
                             nickname=nick or old.get('nickname'), scanned_at=ts)
            else:
                _emit_status(emit, pid, 'verified_expired', '⚠ 登录已过期,需重新扫码')
            try:
                ctx.close()
            except Exception:
                pass
    except Exception as e:
        _emit_status(emit, pid, 'error', f'验证出错:{e}')
    finally:
        with _LOCK:
            _state.update(busy=False, profile_id=None, action=None, cancel=False)
        if on_done:
            on_done()


# ---------- 冷却 / 移除(纯文件操作,无需浏览器) ----------

def set_cooldown(profile_id: int, on: bool) -> tuple:
    """on=True: profile_N → profile_N.cooldown(移出轮换);on=False: 反向恢复。"""
    pdir, cdir = _ppath(profile_id), _ppath(profile_id, '.cooldown')
    try:
        if on:
            if os.path.isdir(pdir):
                os.rename(pdir, cdir)
                return True, ''
            return False, 'profile 不存在或已在冷却'
        else:
            if os.path.isdir(cdir):
                os.rename(cdir, pdir)
                return True, ''
            return False, 'profile 不在冷却中'
    except Exception as e:
        return False, str(e)


def remove_profile(profile_id: int) -> tuple:
    """移除 profile —— 移到 .removed.<ts> 后缀(被池排除),可逆,不真删。"""
    for suffix in ('', '.cooldown'):
        d = _ppath(profile_id, suffix)
        if os.path.isdir(d):
            try:
                os.rename(d, _ppath(profile_id, f'.removed.{int(time.time())}'))
                return True, ''
            except Exception as e:
                return False, str(e)
    return False, 'profile 不存在'
