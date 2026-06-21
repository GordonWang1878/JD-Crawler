#!/usr/bin/env python3
"""JD profile 池管理 — 自动轮转,绕过京东对单 profile 的累积风控.

工作原理:
- profile 目录:jd_chrome_profile_pool/profile_1/, profile_2/, ...
- 每个 profile 独立 Chrome user-data-dir,京东视为独立"身份"
- crawler 启动时 spawn profile_1 的 Chrome(端口 9222)
- 连续 3 次失败时 kill 当前 Chrome,spawn 下一个 profile 的 Chrome
"""
import os
import re
import time
import socket
import signal
import subprocess
from typing import List, Optional


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
POOL_DIR = os.path.join(SCRIPT_DIR, 'jd_chrome_profile_pool')
CDP_PORT = 9222
CHROME_PATH = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


SIDECAR = '.jd_account.json'


def has_login_sidecar(path: str) -> bool:
    """profile 目录里有带昵称的旁车 = 真正扫码登录过.

    注意:不能用「目录非空 / 有 Default 子目录」判断—— Chromium 一启动就会建
    Default,所以一个被取消/失败/移除后残留的空 profile 也会有 Default,会被误判
    成「已登录」。旁车 .jd_account.json 只在扫码/验证成功时写入,是唯一可靠信号.
    """
    try:
        import json
        with open(os.path.join(path, SIDECAR), encoding='utf-8') as f:
            return bool(json.load(f).get('nickname'))
    except Exception:
        return False


def list_available_profiles() -> List[int]:
    """扫描 pool 目录,返回所有已登录的 profile id(按 ID 排序)."""
    if not os.path.isdir(POOL_DIR):
        return []
    ids = []
    for name in os.listdir(POOL_DIR):
        m = re.match(r'^profile_(\d+)$', name)
        if m:
            path = os.path.join(POOL_DIR, name)
            if os.path.isdir(path) and has_login_sidecar(path):  # 真正登录过才算"已准备"
                ids.append(int(m.group(1)))
    return sorted(ids)


def profile_dir(profile_id: int) -> str:
    return os.path.join(POOL_DIR, f'profile_{profile_id}')


def is_cdp_port_listening(port: int = CDP_PORT) -> bool:
    """快速判断 9222 端口是否有 Chrome 在监听."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1.0)
    try:
        return sock.connect_ex(('127.0.0.1', port)) == 0
    except Exception:
        return False
    finally:
        try:
            sock.close()
        except Exception:
            pass


def find_pids_on_port(port: int = CDP_PORT) -> List[int]:
    """用 lsof 找占用指定端口的进程 PID."""
    try:
        out = subprocess.check_output(
            ['lsof', '-nP', '-iTCP:%d' % port, '-sTCP:LISTEN', '-t'],
            stderr=subprocess.DEVNULL,
        ).decode().strip()
        return [int(x) for x in out.split('\n') if x.strip().isdigit()]
    except subprocess.CalledProcessError:
        return []
    except Exception:
        return []


def kill_chrome_on_port(port: int = CDP_PORT, timeout: float = 5.0) -> bool:
    """优雅关闭占用端口的 Chrome 进程.返回是否成功关闭."""
    pids = find_pids_on_port(port)
    if not pids:
        return True

    # SIGTERM 试图优雅退出
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        except Exception:
            pass

    # 等端口释放
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not is_cdp_port_listening(port):
            return True
        time.sleep(0.3)

    # 还没释放,SIGKILL
    pids = find_pids_on_port(port)
    for pid in pids:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except Exception:
            pass

    # 再等
    deadline = time.time() + 3.0
    while time.time() < deadline:
        if not is_cdp_port_listening(port):
            return True
        time.sleep(0.3)
    return not is_cdp_port_listening(port)


def spawn_chrome(profile_id: int, port: int = CDP_PORT) -> int:
    """启动指定 profile 的 Chrome 并返回 PID.

    Raises:
        RuntimeError: profile 不存在 / Chrome 不存在 / 端口已被占用
    """
    pdir = profile_dir(profile_id)
    if not os.path.isdir(pdir):
        raise RuntimeError(f'profile_{profile_id} 不存在,请先运行 prepare_jd_profile_pool.sh')
    if not os.listdir(pdir):
        raise RuntimeError(f'profile_{profile_id} 是空目录,可能没扫码登录过')

    if not os.path.exists(CHROME_PATH):
        raise RuntimeError(f'Chrome 不存在: {CHROME_PATH}')

    if is_cdp_port_listening(port):
        raise RuntimeError(f'端口 {port} 已被占用,请先 kill 当前 Chrome')

    cmd = [
        CHROME_PATH,
        f'--remote-debugging-port={port}',
        f'--user-data-dir={pdir}',
        '--no-first-run',
        '--no-default-browser-check',
        'https://www.jd.com',
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            start_new_session=True)
    return proc.pid


def wait_for_cdp_ready(timeout: float = 30.0, port: int = CDP_PORT) -> bool:
    """轮询直到 CDP 端口就绪."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if is_cdp_port_listening(port):
            time.sleep(1.5)  # 让 Chrome 完全初始化
            return True
        time.sleep(0.5)
    return False


def switch_to_profile(profile_id: int) -> int:
    """杀掉当前 Chrome,启动指定 profile 的 Chrome,等待 CDP 就绪.
    返回新 Chrome 的 PID.
    """
    print(f'  [profile_pool] 切换到 profile_{profile_id}')
    if is_cdp_port_listening():
        print(f'  [profile_pool] 关闭当前 Chrome...')
        if not kill_chrome_on_port():
            raise RuntimeError(f'无法关闭占用端口 {CDP_PORT} 的 Chrome')

    print(f'  [profile_pool] 启动 profile_{profile_id} 的 Chrome...')
    pid = spawn_chrome(profile_id)

    print(f'  [profile_pool] 等待 CDP 就绪...')
    if not wait_for_cdp_ready():
        raise RuntimeError(f'profile_{profile_id} Chrome 启动后 CDP 端口未就绪')

    print(f'  [profile_pool] ✓ profile_{profile_id} 就绪 (PID {pid})')
    return pid


def ensure_chrome_running(profile_id: int = 1) -> int:
    """确保 9222 上有 Chrome 在跑.如果没有,spawn 指定 profile 的 Chrome.
    返回 Chrome PID(或 0 — 如果是连接到已存在的进程,无法知道 PID).
    """
    if is_cdp_port_listening():
        print(f'  [profile_pool] CDP 端口 {CDP_PORT} 已有 Chrome 在跑,直接复用')
        return 0
    print(f'  [profile_pool] 端口空闲,启动 profile_{profile_id}...')
    pid = spawn_chrome(profile_id)
    if not wait_for_cdp_ready():
        raise RuntimeError(f'profile_{profile_id} Chrome 启动后 CDP 端口未就绪')
    print(f'  [profile_pool] ✓ profile_{profile_id} 就绪 (PID {pid})')
    return pid
