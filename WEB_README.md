# JD价格爬虫 - Web前端

## 版本说明

本项目提供两个版本的Web应用：

### 📦 简化版 (app_simple.py)
- **端口**: 5001
- **特点**: 轻量化，无数据库依赖
- **适用**: 快速测试、临时使用
- **访问**: http://localhost:5001

### 🚀 完整版 (app.py)
- **端口**: 5002
- **特点**: 完整功能，SQLite数据库
- **功能**: 历史记录、批次管理、统计分析、日志查询
- **适用**: 生产环境、长期使用
- **访问**: http://localhost:5002

> 💡 两个版本可以**同时运行**，互不干扰

---

## 功能特性

✨ **现代化Web界面**
- 直观的可视化操作界面
- 实时进度显示
- 实时日志输出
- 历史记录查看

🚀 **核心功能**
- 仪表盘 - 统计数据展示
- 批量爬取 - 上传Excel、实时监控
- 单品测试 - 快速测试单个商品
- 历史记录 - 查看所有批次记录
- 实时日志 - 查看系统运行日志
- 设置页面 - 配置爬虫参数

## 安装依赖

```bash
pip3 install -r requirements.txt
```

## 启动应用

### 启动简化版
```bash
python3 app_simple.py
```
应用会在 `http://localhost:5001` 启动

### 启动完整版
```bash
python3 app.py
```
应用会在 `http://localhost:5002` 启动

## 使用说明

### 1. 访问界面

打开浏览器访问:
- 简化版: `http://localhost:5001`
- 完整版: `http://localhost:5002`

### 2. 批量爬取

1. 进入"批量爬取"页面
2. 上传Excel文件（包含商品URL列表）
3. 配置参数（可选）
4. 点击"开始批量爬取"
5. 实时查看进度和日志

### 3. 单品测试

1. 进入"单品测试"页面
2. 输入商品URL或商品ID
3. 点击"开始测试"
4. 查看测试结果

### 4. 查看历史

1. 进入"历史记录"页面
2. 浏览所有批次记录
3. 点击"查看"查看详情

## 技术栈

- **后端**: Flask + Flask-SocketIO
- **前端**: Bootstrap 5 + Chart.js + Socket.IO
- **数据库**: SQLite
- **实时通信**: WebSocket (Socket.IO)

## 项目结构

```
JD-Crawler/
├── app.py                 # Flask应用主文件
├── jd_crawler_via_search.py  # 爬虫核心代码
├── main_batch.py              # 批量处理脚本
├── requirements.txt           # 依赖包
├── static/
│   ├── css/style.css     # 自定义样式
│   ├── js/main.js        # 主要JavaScript
│   └── js/socket.js      # Socket.IO客户端
├── templates/
│   ├── base.html         # 基础模板
│   ├── dashboard.html    # 仪表盘
│   ├── batch.html        # 批量爬取
│   ├── single.html       # 单品测试
│   ├── history.html      # 历史记录
│   ├── logs.html         # 日志页面
│   └── settings.html     # 设置页面
├── uploads/               # 上传文件目录
└── crawler_history.db     # SQLite数据库

```

## 注意事项

1. 首次运行会自动创建数据库
2. 上传的Excel文件会保存在 `uploads/` 目录
3. 日志会保存到数据库中
4. 建议使用Chrome/Edge浏览器访问

## 开发说明

### API端点

- `GET /api/stats` - 获取统计数据
- `GET /api/history` - 获取历史记录
- `GET /api/batch/<id>` - 获取批次详情
- `GET /api/logs` - 获取日志
- `POST /api/upload` - 上传文件
- `POST /api/crawl/start` - 开始爬取
- `POST /api/crawl/stop` - 停止爬取
- `POST /api/test-single` - 测试单个商品

### Socket.IO事件

- `connect` - 客户端连接
- `disconnect` - 客户端断开
- `progress` - 进度更新
- `log` - 日志消息

## 常见问题

**Q: 端口被占用怎么办？**
A: 修改 `app.py` 最后一行的端口号

**Q: 如何更改数据库位置？**
A: 修改 `app.py` 中的 `SQLALCHEMY_DATABASE_URI` 配置

**Q: 上传文件大小限制？**
A: 默认无限制，可在 `app.py` 中添加 `MAX_CONTENT_LENGTH` 配置
