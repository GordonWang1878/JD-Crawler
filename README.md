# 京东价格监测工具

自动爬取京东商品价格并保存到Excel的工具。

## 功能特点

- 自动读取Excel中的京东商品URL列表
- **支持京东账号登录**，获取准确价格
- 自动保存登录状态，无需重复登录
- 爬取商品价格并保存到Excel
- 支持批量处理
- 测试模式和完整模式可选
- 友好的进度显示

## 文件说明

### 主要文件

- `main.py` - 主程序入口
- `jd_price_crawler_final.py` - 京东价格爬虫核心模块
- `test_main.py` - 测试程序（只测试前3个URL）

### 数据文件

- `Product URL List.xlsx` - 输入文件，包含要监测的商品URL
  - Sheet名称: `JD Top Model by Brand`
  - URL列: 第C列（列名为"URL"）

- `Price Marks.xlsx` - 输出文件，保存爬取的价格数据
  - Sheet名称: `Marks`
  - 列: Runtime（运行时间）, URL（商品URL）, Price（价格）

## 安装依赖

```bash
pip3 install pandas openpyxl requests selenium beautifulsoup4 lxml webdriver-manager
```

## 使用方法

### 推荐使用：登录版本（推荐）⭐

使用登录版本可以获取准确的价格数据：

```bash
python3 main_with_login.py
```

**首次运行步骤**：
1. 程序会打开Chrome浏览器
2. 在浏览器中登录你的京东账号（建议使用手机扫码登录）
3. 登录成功后回到终端按Enter键
4. 选择测试模式（3个URL）或完整模式（全部URL）
5. 程序自动爬取价格并保存

**后续运行**：
- 程序会自动使用保存的cookies，无需重复登录
- 如果cookies过期，程序会提示重新登录

### 备选：无登录版本（不推荐）

无法获取准确价格，但可以尝试：

```bash
python3 main.py
```

### 查看结果

运行完成后，打开 `Price Marks.xlsx` 查看结果。

## 工作原理

1. 从 `Product URL List.xlsx` 的 "JD Top Model by Brand" sheet 读取URL列表
2. 对每个URL：
   - 访问京东商品页面
   - 从页面HTML中提取价格信息
   - 保存结果
   - 添加延迟（1-3秒）避免被反爬
3. 将所有结果保存到 `Price Marks.xlsx`

## 注意事项

### 价格提取说明

由于京东的反爬机制，价格数据可能无法100%准确获取。工具会：
- 先尝试快速的requests方式
- 如果失败，自动切换到Selenium浏览器方式
- 最多重试2次

### 常见问题

1. **价格显示不准确**
   - 京东页面可能需要登录才能显示完整价格
   - 工具会尽量从页面的促销标签、图片等位置提取价格

2. **运行速度慢**
   - 为避免被京东反爬虫系统封禁，程序在每个请求之间添加了1-3秒的随机延迟
   - 194个URL大约需要10-20分钟完成

3. **某些URL获取失败**
   - 可能是网络问题或京东页面结构变化
   - 失败的URL会在结果中标记为"N/A"
   - 可以稍后重新运行程序，只针对失败的URL

## 技术栈

- **Python 3.9+**
- **pandas** - Excel数据处理
- **requests** - HTTP请求
- **Selenium** - 浏览器自动化（处理动态加载）
- **BeautifulSoup** - HTML解析

## 文件结构

```
JD Crawler/
├── main.py                          # 主程序
├── test_main.py                     # 测试程序
├── jd_price_crawler_final.py        # 爬虫模块
├── Product URL List.xlsx            # 输入：URL列表
├── Price Marks.xlsx                 # 输出：价格数据
└── README.md                        # 说明文档
```

## 开发文件（可忽略）

以下文件是开发测试过程中创建的，运行主程序时不需要：

- `jd_price_crawler.py` - 早期版本
- `jd_price_crawler_v2.py` - 改进版本
- `jd_price_crawler_selenium.py` - Selenium版本
- `inspect_excel.py` - Excel检查脚本
- `test_connection.py` - 连接测试
- `debug_selenium.py` - 调试脚本
- `*.html`, `*.png` - 调试输出文件

## 更新记录

### 2025-12-03
- ✓ 完成基础爬虫功能
- ✓ 实现Excel读写
- ✓ 添加重试机制
- ✓ 创建测试模式
- ✓ 完成使用文档
