#!/usr/bin/env python3
"""
JD价格爬虫 - Web前端应用
"""
import os
import json
import time
from datetime import datetime
from threading import Thread
from flask import Flask, render_template, request, jsonify, send_file
from flask_socketio import SocketIO, emit
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
import pandas as pd
from werkzeug.utils import secure_filename

# 初始化Flask应用
app = Flask(__name__)
app.config['SECRET_KEY'] = 'jd-crawler-secret-key-2025'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///crawler_history.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# 确保上传目录存在
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# 初始化扩展
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')
db = SQLAlchemy(app)

# 全局变量
crawler_instance = None
crawling_task = None
is_crawling = False

# ==================== 数据库模型 ====================

class CrawlBatch(db.Model):
    """爬取批次记录"""
    id = db.Column(db.Integer, primary_key=True)
    batch_time = db.Column(db.String(50), nullable=False)
    total_count = db.Column(db.Integer, default=0)
    success_count = db.Column(db.Integer, default=0)
    failed_count = db.Column(db.Integer, default=0)
    unavailable_count = db.Column(db.Integer, default=0)
    duration = db.Column(db.Float, default=0.0)  # 运行时长（秒）
    status = db.Column(db.String(20), default='running')  # running, completed, stopped
    created_at = db.Column(db.DateTime, default=datetime.now)

    results = db.relationship('CrawlResult', backref='batch', lazy=True, cascade='all, delete-orphan')

class CrawlResult(db.Model):
    """单个商品爬取结果"""
    id = db.Column(db.Integer, primary_key=True)
    batch_id = db.Column(db.Integer, db.ForeignKey('crawl_batch.id'), nullable=False)
    url = db.Column(db.String(500), nullable=False)
    original_price = db.Column(db.String(50))
    promo_price = db.Column(db.String(50))
    status = db.Column(db.String(50))  # success, not_found, unavailable, blocked, forbidden, retry
    crawl_time = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.now)

class AppLog(db.Model):
    """应用日志"""
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.now)
    level = db.Column(db.String(20))  # INFO, WARNING, ERROR
    message = db.Column(db.Text)

# 创建数据库表
with app.app_context():
    db.create_all()

# ==================== 辅助函数 ====================

def log_message(level, message):
    """记录日志并通过Socket.IO发送到前端"""
    timestamp = datetime.now().strftime("%H:%M:%S")

    # 保存到数据库
    log = AppLog(level=level, message=message)
    db.session.add(log)
    db.session.commit()

    # 发送到前端
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
    """首页 - 重定向到仪表盘"""
    return render_template('dashboard.html')

@app.route('/dashboard')
def dashboard():
    """仪表盘页面"""
    return render_template('dashboard.html')

@app.route('/batch')
def batch():
    """批量爬取页面"""
    return render_template('batch.html')

@app.route('/single')
def single():
    """单品测试页面"""
    return render_template('single.html')

@app.route('/history')
def history():
    """历史记录页面"""
    return render_template('history.html')

@app.route('/logs')
def logs():
    """日志页面"""
    return render_template('logs.html')

@app.route('/settings')
def settings():
    """设置页面"""
    return render_template('settings.html')

# ==================== API端点 ====================

@app.route('/api/stats')
def api_stats():
    """获取统计数据"""
    # 获取今日数据
    today = datetime.now().date()
    today_batches = CrawlBatch.query.filter(
        db.func.date(CrawlBatch.created_at) == today
    ).all()

    total_success = sum(b.success_count for b in today_batches)
    total_failed = sum(b.failed_count for b in today_batches)
    total_unavailable = sum(b.unavailable_count for b in today_batches)
    total_count = sum(b.total_count for b in today_batches)

    success_rate = (total_success / total_count * 100) if total_count > 0 else 0

    return jsonify({
        'today_success': total_success,
        'today_failed': total_failed,
        'today_unavailable': total_unavailable,
        'success_rate': round(success_rate, 1),
        'total_count': total_count
    })

@app.route('/api/history')
def api_history():
    """获取历史记录"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)

    pagination = CrawlBatch.query.order_by(CrawlBatch.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    batches = [{
        'id': b.id,
        'batch_time': b.batch_time,
        'total': b.total_count,
        'success': b.success_count,
        'failed': b.failed_count,
        'unavailable': b.unavailable_count,
        'duration': round(b.duration, 1),
        'status': b.status,
        'created_at': b.created_at.strftime("%Y-%m-%d %H:%M:%S")
    } for b in pagination.items]

    return jsonify({
        'batches': batches,
        'total': pagination.total,
        'pages': pagination.pages,
        'current_page': page
    })

@app.route('/api/batch/<int:batch_id>')
def api_batch_detail(batch_id):
    """获取批次详情"""
    batch = CrawlBatch.query.get_or_404(batch_id)
    results = [{
        'url': r.url,
        'original_price': r.original_price,
        'promo_price': r.promo_price,
        'status': r.status,
        'crawl_time': r.crawl_time
    } for r in batch.results]

    return jsonify({
        'batch': {
            'id': batch.id,
            'batch_time': batch.batch_time,
            'total': batch.total_count,
            'success': batch.success_count,
            'failed': batch.failed_count,
            'unavailable': batch.unavailable_count,
            'duration': round(batch.duration, 1),
            'status': batch.status
        },
        'results': results
    })

@app.route('/api/logs')
def api_logs():
    """获取日志"""
    limit = request.args.get('limit', 100, type=int)
    level = request.args.get('level', 'all')

    query = AppLog.query
    if level != 'all':
        query = query.filter_by(level=level.upper())

    logs = query.order_by(AppLog.timestamp.desc()).limit(limit).all()

    return jsonify({
        'logs': [{
            'timestamp': log.timestamp.strftime("%H:%M:%S"),
            'level': log.level,
            'message': log.message
        } for log in logs]
    })

@app.route('/api/upload', methods=['POST'])
def api_upload():
    """上传Excel文件"""
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    if not file.filename.endswith(('.xlsx', '.xls')):
        return jsonify({'error': 'Invalid file type. Please upload Excel file.'}), 400

    # 保存文件
    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)

    # 读取URL数量
    try:
        df = pd.read_excel(filepath)
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
    global is_crawling, crawling_task

    if is_crawling:
        return jsonify({'error': 'Crawler is already running'}), 400

    data = request.json
    filepath = data.get('filepath')
    config = data.get('config', {})

    if not filepath or not os.path.exists(filepath):
        return jsonify({'error': 'Invalid file path'}), 400

    # 启动爬取任务
    is_crawling = True
    crawling_task = Thread(target=run_crawl_task, args=(filepath, config))
    crawling_task.start()

    return jsonify({'success': True, 'message': 'Crawling started'})

@app.route('/api/crawl/stop', methods=['POST'])
def api_crawl_stop():
    """停止爬取"""
    global is_crawling
    is_crawling = False
    return jsonify({'success': True, 'message': 'Crawling stopped'})

@app.route('/api/test-single', methods=['POST'])
def api_test_single():
    """测试单个商品"""
    data = request.json
    product_id = data.get('product_id')

    if not product_id:
        return jsonify({'error': 'Product ID is required'}), 400

    # 这里会集成实际的爬虫代码
    # 暂时返回模拟数据
    return jsonify({
        'success': True,
        'result': {
            'product_id': product_id,
            'status': 'success',
            'original_price': '102.00',
            'promo_price': '91.80',
            'crawl_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'response_time': '2.3'
        }
    })

# ==================== 爬取任务 ====================

def run_crawl_task(filepath, config):
    """运行爬取任务（在后台线程中）"""
    global is_crawling, crawler_instance

    with app.app_context():
        try:
            from jd_crawler_via_search import JDCrawlerViaSearch
            import re

            log_message('INFO', '初始化浏览器...')

            # 读取Excel
            df = pd.read_excel(filepath)

            # 智能检测列：优先使用URL列，否则使用ProductKey列
            if 'ProductUrl std' in df.columns:
                urls = df['ProductUrl std'].tolist()
            elif 'ProductKey' in df.columns:
                # 如果只有ProductKey，构造完整URL
                urls = [f"https://item.jd.com/{pk}.html" if not str(pk).startswith('http') else pk
                       for pk in df['ProductKey'].tolist()]
            elif 'URL' in df.columns or 'url' in df.columns:
                col_name = 'URL' if 'URL' in df.columns else 'url'
                urls = df[col_name].tolist()
            else:
                # 兜底：使用第一列
                urls = df.iloc[:, 0].tolist()

            total = len(urls)

            # 创建批次记录
            batch_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            batch = CrawlBatch(
                batch_time=batch_time,
                total_count=total,
                status='running'
            )
            db.session.add(batch)
            db.session.commit()

            # 初始化爬虫
            headless = config.get('headless', False)
            crawler = JDCrawlerViaSearch(headless=headless)
            crawler_instance = crawler

            # 登录
            log_message('INFO', '正在登录...')
            crawler.login()

            if not crawler.is_logged_in:
                log_message('ERROR', '登录失败')
                batch.status = 'failed'
                db.session.commit()
                is_crawling = False
                return

            log_message('INFO', '✓ 登录成功')

            # 开始爬取
            results = []
            success_count = 0
            failed_count = 0
            unavailable_count = 0
            start_time = time.time()

            for idx, url in enumerate(urls, 1):
                if not is_crawling:
                    log_message('WARNING', '爬取已停止')
                    break

                # 提取商品ID
                match = re.search(r'/(\d+)\.html', str(url))
                if not match:
                    log_message('WARNING', f'[{idx}/{total}] 无法提取商品ID: {url}')
                    continue

                product_id = match.group(1)
                log_message('INFO', f'[{idx}/{total}] 正在处理: {product_id}')

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

                    if prices:
                        original = prices.get('original')
                        promo = prices.get('promo')

                        # 判断状态
                        if original == 'not_found':
                            status = 'not_found'
                            status_text = 'Not Found'
                            unavailable_count += 1
                        elif original == 'blocked':
                            status = 'blocked'
                            status_text = 'Blocked (Retry)'
                            failed_count += 1
                        elif original == 'forbidden':
                            status = 'forbidden'
                            status_text = 'Forbidden (Retry)'
                            failed_count += 1
                        elif original == 'unavailable':
                            status = 'unavailable'
                            status_text = 'Unavailable'
                            unavailable_count += 1
                        else:
                            status = 'success'
                            status_text = f'¥{original} / ¥{promo}'
                            success_count += 1

                        log_message('INFO', f'  ✓ {status_text}')

                        # 保存结果
                        result = CrawlResult(
                            batch_id=batch.id,
                            url=url,
                            original_price=str(original),
                            promo_price=str(promo),
                            status=status,
                            crawl_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        )
                        db.session.add(result)

                    else:
                        log_message('WARNING', f'  ✗ 获取失败')
                        failed_count += 1

                        result = CrawlResult(
                            batch_id=batch.id,
                            url=url,
                            original_price='N/A (Retry)',
                            promo_price='N/A (Retry)',
                            status='retry',
                            crawl_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        )
                        db.session.add(result)

                    db.session.commit()

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
                    log_message('ERROR', f'  ✗ 错误: {str(e)}')
                    failed_count += 1

                time.sleep(0.5)  # 短暂延迟，避免过快

            # 完成
            duration = time.time() - start_time
            batch.success_count = success_count
            batch.failed_count = failed_count
            batch.unavailable_count = unavailable_count
            batch.duration = duration
            batch.status = 'completed' if is_crawling else 'stopped'
            db.session.commit()

            log_message('INFO', f'✓ 爬取完成! 成功: {success_count}, 失败: {failed_count}, 下架: {unavailable_count}')

            # 关闭爬虫
            crawler.close()
            crawler_instance = None
            is_crawling = False

        except Exception as e:
            log_message('ERROR', f'爬取任务异常: {str(e)}')
            is_crawling = False
            if crawler_instance:
                crawler_instance.close()

# ==================== Socket.IO事件 ====================

@socketio.on('connect')
def handle_connect():
    """客户端连接"""
    print('Client connected')
    emit('connected', {'data': 'Connected to server'})

@socketio.on('disconnect')
def handle_disconnect():
    """客户端断开"""
    print('Client disconnected')

# ==================== 启动应用 ====================

if __name__ == '__main__':
    print("=" * 70)
    print("JD价格爬虫 - Web前端 (完整版)")
    print("=" * 70)
    print("\n访问: http://localhost:5002")
    print("\n按 Ctrl+C 停止服务器\n")

    socketio.run(app, debug=True, host='0.0.0.0', port=5002, allow_unsafe_werkzeug=True)
