#!/usr/bin/env python3
"""
JD价格爬虫 - Web前端
"""
import os
import re
import time
import random
import glob as glob_mod
from datetime import datetime
from threading import Thread
from flask import Flask, render_template, request, jsonify, send_file
from flask_socketio import SocketIO
from flask_cors import CORS
import pandas as pd
from werkzeug.utils import secure_filename
from jd_crawler_via_search import JDCrawlerViaSearch

# 初始化Flask应用
app = Flask(__name__)
app.config['SECRET_KEY'] = 'jd-crawler-simple-2025'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['OUTPUT_FOLDER'] = 'outputs'

# 确保目录存在
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['OUTPUT_FOLDER'], exist_ok=True)

# 初始化扩展
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# 全局变量
crawler_instance = None
is_crawling = False
current_results = []
current_batch_file = None
# Store per-row results for live table + retry
live_results = []
# Track the uploaded dataframe for preview
uploaded_df = None
uploaded_urls = []
# Full parsed rows from uploaded Excel (brand/item/url/product_key/price_reference)
uploaded_rows = []

# ==================== 辅助函数 ====================

def _norm_col(name):
    """归一化列名用于匹配"""
    return str(name).strip().lower().replace(' ', '').replace('_', '')

def _parse_excel(filepath):
    """读取 Excel 并提取 5 个核心列,返回 row dict 列表"""
    df = pd.read_excel(filepath)
    col_map = {_norm_col(c): c for c in df.columns}

    def pick(*candidates):
        # 精确匹配
        for c in candidates:
            if _norm_col(c) in col_map:
                return col_map[_norm_col(c)]
        # 前缀匹配 fallback(兼容 "Price Reference_0" 之类的后缀列名)
        for c in candidates:
            nc = _norm_col(c)
            for norm, orig in col_map.items():
                if norm.startswith(nc):
                    return orig
        return None

    brand_col = pick('Brand', '品牌')
    item_col = pick('Item', '型号', 'Model')
    url_col = pick('URL', 'ProductUrl std', 'ProductUrl', '链接')
    key_col = pick('Product Key', 'ProductKey', 'SKU')
    ref_col = pick('Price Reference', 'PriceReference', '参考价')

    rows = []
    for _, r in df.iterrows():
        def val(col):
            if not col:
                return ''
            v = r[col]
            if pd.isna(v):
                return ''
            if isinstance(v, float):
                if v.is_integer():
                    return str(int(v))
                return f'{v:.2f}'
            return str(v).strip()

        brand = val(brand_col)
        item = val(item_col)
        url = val(url_col)
        key = val(key_col)
        ref = val(ref_col)

        # URL 缺失时,从 Product Key 构造
        if not url and key:
            url = f"https://item.jd.com/{key}.html"

        # 从 URL 提取 product_id(爬取用)
        product_id = ''
        if url:
            m = re.search(r'/(\d+)\.html', url)
            if m:
                product_id = m.group(1)
        if not product_id and key:
            product_id = key

        if not url and not product_id:
            continue  # 跳过无效行

        rows.append({
            'brand': brand,
            'item': item,
            'url': url,
            'product_key': key,
            'price_reference': ref,
            'product_id': product_id,
        })
    return rows

def emit_log(level, message):
    """发送日志到前端"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    socketio.emit('log', {
        'timestamp': timestamp,
        'level': level,
        'message': message
    })
    print(f"[{timestamp}] [{level}] {message}")

def emit_progress(data):
    """发送进度更新到前端"""
    socketio.emit('progress', data)

def emit_result_row(row):
    """发送单条爬取结果到前端"""
    socketio.emit('result_row', row)

# ==================== 路由 ====================

@app.route('/')
def index():
    """首页"""
    return render_template('batch.html')

@app.route('/api/upload', methods=['POST'])
def api_upload():
    """上传Excel文件"""
    global uploaded_df, uploaded_urls, uploaded_rows

    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    if not file.filename.endswith(('.xlsx', '.xls')):
        return jsonify({'error': 'Invalid file type'}), 400

    # 保存文件
    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)

    # 读取并解析
    try:
        df = pd.read_excel(filepath)
        uploaded_df = df

        rows = _parse_excel(filepath)
        uploaded_rows = rows
        uploaded_urls = [r['url'] for r in rows]

        return jsonify({
            'success': True,
            'filename': filename,
            'filepath': filepath,
            'url_count': len(rows),
            'columns': list(df.columns)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/preview')
def api_preview():
    """预览上传的数据 — 返回 Brand / Item / URL / Product Key / Price Reference"""
    global uploaded_rows

    if not uploaded_rows:
        return jsonify({'error': 'No file uploaded'}), 400

    rows = []
    for i, r in enumerate(uploaded_rows):
        rows.append({
            'index': i + 1,
            'brand': r.get('brand', ''),
            'item': r.get('item', ''),
            'url': r.get('url', ''),
            'product_key': r.get('product_key', ''),
            'price_reference': r.get('price_reference', ''),
        })

    return jsonify({'success': True, 'rows': rows, 'total': len(rows)})

@app.route('/api/history')
def api_history():
    """获取历史爬取结果文件列表"""
    output_dir = app.config['OUTPUT_FOLDER']
    files = []

    for f in sorted(glob_mod.glob(os.path.join(output_dir, '*.xlsx')), key=os.path.getmtime, reverse=True):
        fname = os.path.basename(f)
        stat = os.stat(f)
        # Try to read row count
        try:
            df = pd.read_excel(f)
            row_count = len(df)
        except:
            row_count = None

        files.append({
            'filename': fname,
            'size': stat.st_size,
            'modified': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M'),
            'row_count': row_count
        })

    return jsonify({'success': True, 'files': files[:20]})  # Limit to 20 most recent

@app.route('/api/results')
def api_results():
    """获取当前爬取结果"""
    return jsonify({'success': True, 'results': live_results})

@app.route('/api/crawl/start', methods=['POST'])
def api_crawl_start():
    """开始批量爬取"""
    global is_crawling, current_batch_file, live_results

    if is_crawling:
        return jsonify({'error': 'Crawler is already running'}), 400

    data = request.json
    filepath = data.get('filepath')
    config = data.get('config', {})

    if not filepath or not os.path.exists(filepath):
        return jsonify({'error': 'Invalid file path'}), 400

    # 生成输出文件名
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = f"Price_Marks_{timestamp}.xlsx"
    current_batch_file = os.path.join(app.config['OUTPUT_FOLDER'], output_filename)

    # Reset live results
    live_results = []

    # 启动爬取任务
    is_crawling = True
    crawling_task = Thread(target=run_crawl_task, args=(filepath, current_batch_file, config))
    crawling_task.start()

    return jsonify({
        'success': True,
        'message': 'Crawling started',
        'output_file': output_filename
    })

@app.route('/api/crawl/retry', methods=['POST'])
def api_crawl_retry():
    """重试失败的商品"""
    global is_crawling, current_batch_file, live_results

    if is_crawling:
        return jsonify({'error': 'Crawler is already running'}), 400

    # Collect failed items from live_results (keep brand/item context)
    failed_items = [r for r in live_results if r.get('status') in ('failed', 'blocked', 'forbidden')]

    if not failed_items:
        return jsonify({'error': 'No failed items to retry'}), 400

    # Remove failed items from live_results (they'll be re-crawled)
    live_results = [r for r in live_results if r.get('status') not in ('failed', 'blocked', 'forbidden')]

    # Generate new output file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = f"Price_Marks_retry_{timestamp}.xlsx"
    current_batch_file = os.path.join(app.config['OUTPUT_FOLDER'], output_filename)

    is_crawling = True
    crawling_task = Thread(target=run_crawl_task_from_rows, args=(failed_items, current_batch_file, {}))
    crawling_task.start()

    return jsonify({
        'success': True,
        'message': f'Retrying {len(failed_items)} failed items',
        'retry_count': len(failed_items),
        'output_file': output_filename
    })

@app.route('/api/crawl/stop', methods=['POST'])
def api_crawl_stop():
    """停止爬取"""
    global is_crawling
    is_crawling = False
    return jsonify({'success': True, 'message': 'Crawling stopped'})

@app.route('/api/download/<filename>')
def api_download(filename):
    """下载结果文件"""
    filepath = os.path.join(app.config['OUTPUT_FOLDER'], filename)
    if os.path.exists(filepath):
        return send_file(filepath, as_attachment=True)
    else:
        return jsonify({'error': 'File not found'}), 404

@app.route('/api/quick-check', methods=['POST'])
def api_quick_check():
    """快速查询单个商品价格"""
    global crawler_instance, is_crawling

    if is_crawling:
        return jsonify({'error': 'Crawler is busy with batch job'}), 400

    data = request.json
    product_input = data.get('product_id', '').strip()

    if not product_input:
        return jsonify({'error': 'Product ID is required'}), 400

    # Extract product ID from URL or raw ID
    match = re.search(r'(\d{6,})', product_input)
    if not match:
        return jsonify({'error': 'Invalid product ID or URL'}), 400

    product_id = match.group(1)

    # Run in a thread and return result via socket
    def do_check():
        global crawler_instance
        try:
            socketio.emit('quick_check_status', {'status': 'starting', 'product_id': product_id})

            # Initialize crawler if needed
            if not crawler_instance or not crawler_instance.is_session_valid():
                socketio.emit('quick_check_status', {'status': 'logging_in', 'product_id': product_id})
                crawler = JDCrawlerViaSearch(headless=False)
                crawler.login()
                if not crawler.is_logged_in:
                    socketio.emit('quick_check_result', {
                        'success': False,
                        'product_id': product_id,
                        'error': 'Login failed'
                    })
                    return
                crawler_instance = crawler
            else:
                crawler = crawler_instance

            socketio.emit('quick_check_status', {'status': 'fetching', 'product_id': product_id})
            prices = crawler.get_price_via_search(product_id)

            if prices:
                original = prices.get('original')
                promo = prices.get('promo')

                # Determine status
                if original in ('not_found', 'blocked', 'forbidden', 'unavailable'):
                    socketio.emit('quick_check_result', {
                        'success': False,
                        'product_id': product_id,
                        'status': original,
                        'error': f'Product status: {original}'
                    })
                else:
                    socketio.emit('quick_check_result', {
                        'success': True,
                        'product_id': product_id,
                        'original_price': original,
                        'promo_price': promo,
                        'url': f'https://item.jd.com/{product_id}.html'
                    })
            else:
                socketio.emit('quick_check_result', {
                    'success': False,
                    'product_id': product_id,
                    'error': 'Could not extract price'
                })

        except Exception as e:
            socketio.emit('quick_check_result', {
                'success': False,
                'product_id': product_id,
                'error': str(e)
            })

    thread = Thread(target=do_check)
    thread.start()

    return jsonify({'success': True, 'message': 'Quick check started', 'product_id': product_id})

# ==================== 爬取任务 ====================

def process_single_row(crawler, input_row, idx, total, batch_time):
    """处理单行并返回结果 row"""
    global is_crawling

    url = str(input_row.get('url', ''))
    product_id = input_row.get('product_id', '')
    if not product_id:
        m = re.search(r'/(\d+)\.html', url)
        if m:
            product_id = m.group(1)

    if not product_id:
        emit_log('WARNING', f'[{idx}/{total}] Cannot extract product ID: {url}')
        return None

    item_label = input_row.get('item') or product_id
    emit_log('INFO', f'[{idx}/{total}] Processing: {item_label}')

    # 发送进度
    emit_progress({
        'current': idx,
        'total': total,
        'percent': round(idx / total * 100, 1),
        'current_url': url,
        'product_id': product_id,
        'status': 'processing'
    })

    crawl_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    row = {
        'index': idx,
        'brand': input_row.get('brand', ''),
        'item': input_row.get('item', ''),
        'product_key': input_row.get('product_key', ''),
        'price_reference': input_row.get('price_reference', ''),
        'product_id': product_id,
        'url': url,
        'batch_time': batch_time,
        'crawl_time': crawl_time,
        'original_price': None,
        'promo_price': None,
        'status': 'pending'
    }

    try:
        prices = crawler.get_price_via_search(product_id)

        if prices:
            original = prices.get('original')
            promo = prices.get('promo')

            if original == 'not_found':
                emit_log('WARNING', f'  Product not found')
                row.update({'status': 'not_found', 'original_price': '-', 'promo_price': '-'})
            elif original == 'blocked':
                emit_log('WARNING', f'  Anti-crawl triggered (retry)')
                row.update({'status': 'blocked', 'original_price': '-', 'promo_price': '-'})
            elif original == 'forbidden':
                emit_log('WARNING', f'  403 Forbidden (retry)')
                row.update({'status': 'forbidden', 'original_price': '-', 'promo_price': '-'})
            elif original == 'unavailable':
                emit_log('WARNING', f'  Product delisted')
                row.update({'status': 'unavailable', 'original_price': '-', 'promo_price': '-'})
            else:
                emit_log('INFO', f'  OK: ¥{original} / ¥{promo}')
                row.update({
                    'status': 'success',
                    'original_price': original,
                    'promo_price': promo
                })
                if not original or not promo:
                    row['status'] = 'partial'
        else:
            emit_log('WARNING', f'  Failed (can retry)')
            row.update({'status': 'failed', 'original_price': '-', 'promo_price': '-'})

    except Exception as e:
        emit_log('ERROR', f'  Error: {str(e)}')
        row.update({'status': 'failed', 'original_price': '-', 'promo_price': '-'})

    return row


def run_crawl_task(input_filepath, output_filepath, config):
    """运行爬取任务（从文件）"""
    global uploaded_urls, uploaded_rows

    emit_log('INFO', f'Reading file: {os.path.basename(input_filepath)}')
    rows = _parse_excel(input_filepath)
    uploaded_rows = rows
    uploaded_urls = [r['url'] for r in rows]
    run_crawl_task_from_rows(rows, output_filepath, config)


def run_crawl_task_from_rows(input_rows, output_filepath, config):
    """运行爬取任务（从 row dict 列表）"""
    global is_crawling, crawler_instance, current_results, live_results

    try:
        total = len(input_rows)
        emit_log('INFO', '=' * 50)
        emit_log('INFO', f'Starting batch crawl: {total} products')
        emit_log('INFO', '=' * 50)

        # 复用已有的浏览器实例，避免重复初始化
        if crawler_instance and crawler_instance.is_session_valid():
            emit_log('INFO', '复用已有浏览器会话')
            crawler = crawler_instance
            # 确认登录状态
            if not crawler.is_logged_in:
                emit_log('INFO', 'Logging in...')
                crawler.login()
        else:
            emit_log('INFO', 'Initializing browser...')
            crawler = JDCrawlerViaSearch(headless=False)
            crawler_instance = crawler
            emit_log('INFO', 'Logging in...')
            crawler.login()

        if not crawler.is_logged_in:
            emit_log('ERROR', 'Login failed')
            is_crawling = False
            socketio.emit('crawl_complete', {'success': False, 'error': 'Login failed'})
            return

        emit_log('INFO', 'Login successful')

        # 热身：模拟正常浏览降低反爬风险
        emit_log('INFO', '正在热身（模拟正常浏览）...')
        crawler.warmup()

        batch_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        start_time = time.time()

        success_count = 0
        failed_count = 0
        unavailable_count = 0
        consecutive_failures = 0
        anti_crawl_cooldowns = 0  # 已触发冷却的次数

        for idx, input_row in enumerate(input_rows, 1):
            if not is_crawling:
                emit_log('WARNING', 'Crawl stopped by user')
                break

            # 反爬冷却：首次失败就立即触发，不等5次
            if consecutive_failures >= 2:
                anti_crawl_cooldowns += 1
                cooldown = min(30 + anti_crawl_cooldowns * 30, 120)  # 60s, 90s, 120s...
                emit_log('WARNING', f'检测到反爬，冷却{cooldown}秒... (第{anti_crawl_cooldowns}次)')
                time.sleep(cooldown)
                consecutive_failures = 0

                # 冷却后先访问京东首页"重置"会话
                try:
                    emit_log('INFO', '重置会话：访问京东首页...')
                    crawler.driver.get("https://www.jd.com")
                    time.sleep(random.uniform(3.0, 5.0))
                    # 模拟浏览首页
                    crawler.driver.execute_script("window.scrollTo(0, 500);")
                    time.sleep(1)
                    crawler.driver.execute_script("window.scrollTo(0, 0);")
                    time.sleep(1)
                except Exception:
                    if not crawler.is_session_valid():
                        emit_log('INFO', '会话失效，重启浏览器...')
                        crawler.restart_browser()

            row = process_single_row(crawler, input_row, idx, total, batch_time)
            if not row:
                continue

            # Add to live results and emit
            live_results.append(row)
            emit_result_row(row)

            # Count stats and track consecutive failures
            if row['status'] == 'success':
                success_count += 1
                consecutive_failures = 0
                anti_crawl_cooldowns = 0  # 成功后重置冷却计数
            elif row['status'] in ('failed', 'blocked', 'forbidden', 'partial'):
                failed_count += 1
                consecutive_failures += 1
            elif row['status'] in ('unavailable', 'not_found'):
                unavailable_count += 1

            # 发送统计更新
            emit_progress({
                'statistics': {
                    'success': success_count,
                    'failed': failed_count,
                    'unavailable': unavailable_count,
                    'total': idx
                }
            })

            # 渐进式延迟：前10个短间隔，之后逐渐增加
            if idx <= 10:
                delay = random.uniform(2.0, 4.0)
            elif idx <= 20:
                delay = random.uniform(4.0, 7.0)
            else:
                delay = random.uniform(6.0, 10.0)
            time.sleep(delay)

        # 保存Excel
        emit_log('INFO', 'Saving results to Excel...')
        excel_rows = []
        for r in live_results:
            excel_rows.append({
                'Batch Time': r['batch_time'],
                'Crawl Time': r['crawl_time'],
                'Brand': r.get('brand', ''),
                'Item': r.get('item', ''),
                'URL': r['url'],
                'Product Key': r.get('product_key', '') or r.get('product_id', ''),
                'Price Reference': r.get('price_reference', ''),
                'Status': r['status'],
                'Price': r['original_price'] if r['original_price'] not in (None, '-') else 'N/A',
                'Promotion Price': r['promo_price'] if r['promo_price'] not in (None, '-') else 'N/A'
            })

        df_results = pd.DataFrame(excel_rows)
        df_results.to_excel(output_filepath, index=False, engine='openpyxl')

        duration = time.time() - start_time
        emit_log('INFO', '=' * 50)
        emit_log('INFO', f'Crawl complete!')
        emit_log('INFO', f'  Success: {success_count}')
        emit_log('INFO', f'  Failed: {failed_count}')
        emit_log('INFO', f'  Unavailable: {unavailable_count}')
        emit_log('INFO', f'  Duration: {duration:.1f}s')
        emit_log('INFO', f'  Output: {os.path.basename(output_filepath)}')
        emit_log('INFO', '=' * 50)

        socketio.emit('crawl_complete', {
            'success': True,
            'output_file': os.path.basename(output_filepath),
            'stats': {
                'success': success_count,
                'failed': failed_count,
                'unavailable': unavailable_count,
                'total': len(live_results),
                'duration': round(duration, 1)
            }
        })

        # 不关闭浏览器，下次复用（避免重新下载 ChromeDriver）
        is_crawling = False
        current_results = live_results

    except Exception as e:
        emit_log('ERROR', f'Crawl task error: {str(e)}')
        import traceback
        traceback.print_exc()
        is_crawling = False

        socketio.emit('crawl_complete', {
            'success': False,
            'error': str(e)
        })

# ==================== Socket.IO事件 ====================

@socketio.on('connect')
def handle_connect():
    """客户端连接"""
    print('Client connected')
    socketio.emit('connected', {'data': 'Connected to server'})

@socketio.on('disconnect')
def handle_disconnect():
    """客户端断开"""
    print('Client disconnected')

# ==================== 启动应用 ====================

if __name__ == '__main__':
    print("=" * 70)
    print("JD Price Crawler")
    print("=" * 70)
    print("\nOpen: http://localhost:5001")
    print("\nPress Ctrl+C to stop\n")

    socketio.run(app, debug=False, host='0.0.0.0', port=5001, allow_unsafe_werkzeug=True)
