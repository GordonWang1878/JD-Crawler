#!/usr/bin/env python3
"""
JD价格爬虫 - 简化Web前端（无数据库版本）
"""
import os
import re
import time
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

# ==================== 辅助函数 ====================

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

# ==================== 路由 ====================

@app.route('/')
def index():
    """首页"""
    return render_template('batch_simple.html')

@app.route('/api/upload', methods=['POST'])
def api_upload():
    """上传Excel文件"""
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

    # 读取URL数量
    try:
        df = pd.read_excel(filepath)

        # 检查是否有ProductKey列
        if 'ProductKey' in df.columns:
            url_count = len(df['ProductKey'].dropna())
        else:
            url_count = len(df)

        return jsonify({
            'success': True,
            'filename': filename,
            'filepath': filepath,
            'url_count': url_count
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/crawl/start', methods=['POST'])
def api_crawl_start():
    """开始批量爬取"""
    global is_crawling, current_batch_file

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

    # 启动爬取任务
    is_crawling = True
    crawling_task = Thread(target=run_crawl_task, args=(filepath, current_batch_file, config))
    crawling_task.start()

    return jsonify({
        'success': True,
        'message': 'Crawling started',
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

# ==================== 爬取任务 ====================

def run_crawl_task(input_filepath, output_filepath, config):
    """运行爬取任务"""
    global is_crawling, crawler_instance, current_results

    try:
        emit_log('INFO', '=' * 50)
        emit_log('INFO', '开始批量爬取')
        emit_log('INFO', '=' * 50)

        # 读取Excel
        emit_log('INFO', f'读取文件: {os.path.basename(input_filepath)}')
        df = pd.read_excel(input_filepath)

        # 智能检测列：优先使用URL列，否则使用ProductKey列
        if 'ProductUrl std' in df.columns:
            urls = df['ProductUrl std'].tolist()
            emit_log('INFO', f'从ProductUrl std列读取URL（共{len(urls)}个）')
        elif 'ProductKey' in df.columns:
            product_ids = df['ProductKey'].tolist()
            urls = [f"https://item.jd.com/{pid}.html" for pid in product_ids]
            emit_log('INFO', f'从ProductKey列读取商品ID（共{len(urls)}个）')
        elif 'URL' in df.columns or 'url' in df.columns:
            col_name = 'URL' if 'URL' in df.columns else 'url'
            urls = df[col_name].tolist()
            emit_log('INFO', f'从{col_name}列读取URL（共{len(urls)}个）')
        else:
            urls = df.iloc[:, 0].tolist()
            emit_log('INFO', f'从第一列读取URL（共{len(urls)}个）')

        total = len(urls)
        emit_log('INFO', f'共 {total} 个商品')

        # 初始化爬虫
        emit_log('INFO', '初始化浏览器...')
        crawler = JDCrawlerViaSearch(headless=False)
        crawler_instance = crawler

        # 登录
        emit_log('INFO', '正在登录...')
        crawler.login()

        if not crawler.is_logged_in:
            emit_log('ERROR', '登录失败')
            is_crawling = False
            return

        emit_log('INFO', '✓ 登录成功')

        # 准备结果列表
        results = []
        success_count = 0
        failed_count = 0
        unavailable_count = 0

        batch_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        start_time = time.time()

        # 开始爬取
        for idx, url in enumerate(urls, 1):
            if not is_crawling:
                emit_log('WARNING', '爬取已停止')
                break

            # 提取商品ID
            match = re.search(r'/(\d+)\.html', str(url))
            if not match:
                emit_log('WARNING', f'[{idx}/{total}] 无法提取商品ID: {url}')
                continue

            product_id = match.group(1)
            emit_log('INFO', f'[{idx}/{total}] 处理: {product_id}')

            # 发送进度
            emit_progress({
                'current': idx,
                'total': total,
                'percent': round(idx / total * 100, 1),
                'current_url': url,
                'product_id': product_id,
                'status': 'processing'
            })

            try:
                # 获取价格
                prices = crawler.get_price_via_search(product_id)

                crawl_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                if prices:
                    original = prices.get('original')
                    promo = prices.get('promo')

                    # 判断状态并保存结果
                    if original == 'not_found':
                        emit_log('WARNING', f'  ⚠️  商品不存在')
                        results.append({
                            'Batch Time': batch_time,
                            'Crawl Time': crawl_time,
                            'URL': url,
                            'Price': 'Not Found',
                            'Promotion Price': 'Not Found'
                        })
                        unavailable_count += 1

                    elif original == 'blocked':
                        emit_log('WARNING', f'  ⚠️  触发反爬验证 (建议重试)')
                        results.append({
                            'Batch Time': batch_time,
                            'Crawl Time': crawl_time,
                            'URL': url,
                            'Price': 'Blocked (Retry)',
                            'Promotion Price': 'Blocked (Retry)'
                        })
                        failed_count += 1

                    elif original == 'forbidden':
                        emit_log('WARNING', f'  ⚠️  403禁止访问 (建议重试)')
                        results.append({
                            'Batch Time': batch_time,
                            'Crawl Time': crawl_time,
                            'URL': url,
                            'Price': 'Forbidden (Retry)',
                            'Promotion Price': 'Forbidden (Retry)'
                        })
                        failed_count += 1

                    elif original == 'unavailable':
                        emit_log('WARNING', f'  ⚠️  商品已下架')
                        results.append({
                            'Batch Time': batch_time,
                            'Crawl Time': crawl_time,
                            'URL': url,
                            'Price': 'Unavailable',
                            'Promotion Price': 'Unavailable'
                        })
                        unavailable_count += 1

                    else:
                        emit_log('INFO', f'  ✓ 成功: ¥{original} / ¥{promo}')
                        results.append({
                            'Batch Time': batch_time,
                            'Crawl Time': crawl_time,
                            'URL': url,
                            'Price': original if original else 'N/A (Retry)',
                            'Promotion Price': promo if promo else 'N/A (Retry)'
                        })
                        if original and promo:
                            success_count += 1
                        else:
                            failed_count += 1

                else:
                    emit_log('WARNING', f'  ✗ 获取失败 (可重试)')
                    results.append({
                        'Batch Time': batch_time,
                        'Crawl Time': crawl_time,
                        'URL': url,
                        'Price': 'N/A (Retry)',
                        'Promotion Price': 'N/A (Retry)'
                    })
                    failed_count += 1

                # 发送统计更新
                emit_progress({
                    'statistics': {
                        'success': success_count,
                        'failed': failed_count,
                        'unavailable': unavailable_count,
                        'total': idx
                    }
                })

            except Exception as e:
                emit_log('ERROR', f'  ✗ 错误: {str(e)}')
                failed_count += 1
                results.append({
                    'Batch Time': batch_time,
                    'Crawl Time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    'URL': url,
                    'Price': 'N/A (Retry)',
                    'Promotion Price': 'N/A (Retry)'
                })

            # 短暂延迟
            time.sleep(0.5)

        # 保存Excel
        emit_log('INFO', '保存结果到Excel...')
        df_results = pd.DataFrame(results)
        df_results.to_excel(output_filepath, index=False, engine='openpyxl')

        # 完成
        duration = time.time() - start_time
        emit_log('INFO', '=' * 50)
        emit_log('INFO', f'✓ 爬取完成!')
        emit_log('INFO', f'  成功: {success_count}')
        emit_log('INFO', f'  失败: {failed_count}')
        emit_log('INFO', f'  下架: {unavailable_count}')
        emit_log('INFO', f'  用时: {duration:.1f}秒')
        emit_log('INFO', f'  结果文件: {os.path.basename(output_filepath)}')
        emit_log('INFO', '=' * 50)

        # 发送完成通知
        socketio.emit('crawl_complete', {
            'success': True,
            'output_file': os.path.basename(output_filepath),
            'stats': {
                'success': success_count,
                'failed': failed_count,
                'unavailable': unavailable_count,
                'total': len(results),
                'duration': round(duration, 1)
            }
        })

        # 关闭爬虫
        crawler.close()
        crawler_instance = None
        is_crawling = False
        current_results = results

    except Exception as e:
        emit_log('ERROR', f'爬取任务异常: {str(e)}')
        import traceback
        traceback.print_exc()
        is_crawling = False
        if crawler_instance:
            crawler_instance.close()

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
    print("JD价格爬虫 - 简化Web前端")
    print("=" * 70)
    print("\n访问: http://localhost:5001")
    print("\n按 Ctrl+C 停止服务器\n")

    socketio.run(app, debug=True, host='0.0.0.0', port=5001, allow_unsafe_werkzeug=True)
