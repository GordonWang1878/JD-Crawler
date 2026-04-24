# 京东价格监测工具

基于 Web UI 的京东商品价格批量爬取工具,带登录、反爬缓解、实时进度显示。

## 功能特点

- **Web UI**：浏览器内操作,实时查看进度、日志、历史记录
- **登录持久化**：首次扫码登录后保存 cookies,后续免登录
- **反爬策略**：
  - 登录后 warmup 模拟正常浏览
  - 渐进式请求间隔(随批次增大延迟)
  - 连续失败自动冷却,冷却后重置会话
  - 浏览器实例跨批复用,避免重复初始化
- **精确区分状态**：成功 / 部分 / 失败 / 被拦截 / 已下架 / 未找到 (`?d` 首页重定向 → `not_found`)
- **Excel 完整回写**：保留输入的 Brand / Item / URL / Product Key / Price Reference,附加 Status / Price / Promotion Price
- **批量重试**：一键重试所有失败/被拦截项
- **单品快速查询**：不走批量流程,直接查一条

## 快速开始

### 安装依赖

```bash
pip3 install flask flask-socketio flask-cors pandas openpyxl undetected-chromedriver selenium werkzeug
```

### 启动

```bash
python3 app.py
```

浏览器打开 http://localhost:5001

### 首次使用流程

1. 上传 Excel(数据格式见下)
2. 在"数据预览"标签页确认数据
3. 点击"开始爬取"
4. 弹出 Chrome 窗口,扫码登录京东(首次)
5. 登录后自动 warmup,然后开始批量抓取
6. 实时查看"爬取结果"与"运行日志"
7. 完成后下载 Excel,或点击"重试失败项"

Cookies 保存在 `jd_cookies.pkl`,再次运行不需要重新登录(直到过期)。

## Excel 数据格式

### 输入

工具会自动识别以下列名(不区分大小写、空格、下划线,支持前缀变体如 `Price Reference_0`):

| 字段 | 识别名称(任一) | 说明 |
|------|---------------|------|
| 品牌 | `Brand` / `品牌` | 显示用 |
| 型号 | `Item` / `Model` / `型号` | 显示用,用于识别商品 |
| 链接 | `URL` / `ProductUrl Std` / `链接` | 抓取目标,缺失时由 Product Key 自动构造 |
| 商品 ID | `Product Key` / `ProductKey` / `SKU` | 京东商品 ID |
| 参考价 | `Price Reference` / `参考价` | 仅显示对比 |

其中 URL 和 Product Key 至少有一个。其他字段可为空。

### 输出

保存到 `outputs/Price_Marks_<时间戳>.xlsx`,包含:

```
Batch Time | Crawl Time | Brand | Item | URL | Product Key | Price Reference | Status | Price | Promotion Price
```

## 文件结构

```
JD Crawler/
├── app.py                      # Flask Web 服务
├── jd_crawler_via_search.py    # 爬虫核心(登录、抓取、状态判断)
├── templates/
│   └── batch.html              # 前端单页
├── uploads/                    # 上传的 Excel
├── outputs/                    # 生成的价格 Excel
├── jd_cookies.pkl              # 登录 cookies(自动生成)
├── README.md
└── CHANGELOG.md
```

## 状态含义

| 状态 | 说明 | 会重试 |
|------|------|--------|
| `success` | 成功抓到原价和促销价 | ✗ |
| `partial` | 只抓到其中一个价格 | ✓ |
| `failed` | 未知错误或无法提取价格 | ✓ |
| `blocked` | 反爬拦截(被重定向/验证页) | ✓ |
| `forbidden` | 403 | ✓ |
| `unavailable` | 商品已下架 | ✗ |
| `not_found` | 商品不存在(`?d` 重定向) | ✗ |

"重试失败项"按钮会重新抓取所有可重试状态。

## 反爬机制说明

- **首次批量前 warmup**:访问首页 → 搜索 → 点击某商品 → 返回,降低直接打商品页的可疑度
- **连续 2 次失败**:触发冷却(30s → 60s → 90s,最多 120s),冷却期间访问首页"重置"会话
- **请求间隔**:前 10 个 2-4s / 11-20 个 4-7s / 之后 6-10s
- **会话复用**:批次结束后不关闭浏览器,下次直接复用

即便如此,重复在同一 IP 高频跑仍可能被标记。建议每日只跑一轮完整批次,或轻度使用以保留登录会话。

## 常见问题

**Q: 初始化浏览器很慢(几分钟)**
A: `undetected-chromedriver` 需要从 Google 下载 ChromeDriver,国内网络受限时第一次下载耗时较长。下载完成后会缓存到 `~/Library/Application Support/undetected_chromedriver/`,后续启动只需数秒。

**Q: 登录失败**
A: 删除 `jd_cookies.pkl` 后重启,会重新弹出登录页。

**Q: 全部被判定为被拦截/失败**
A: IP 可能被京东反爬系统标记。停止测试 2-3 小时或切换网络后重试。

**Q: 端口 5001 被占用**
A: `lsof -ti:5001 | xargs kill -9`

## 技术栈

- Flask + Flask-SocketIO(后端 + WebSocket 实时推送)
- undetected-chromedriver + Selenium(浏览器自动化)
- pandas + openpyxl(Excel 读写)
- 原生 HTML/CSS/JS 前端(无打包工具)
