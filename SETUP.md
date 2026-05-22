# 配环境 + 跑起来

> 从另一台电脑拉下代码后，按这份文档操作。10-20 分钟搞定。
> 适用：macOS（已验证）。Linux/Windows 可参考但 Chrome 路径需要自己调。

## 0. 前置依赖

- **Python 3.11+**（macOS 自带 3.9 可能不够，建议用 homebrew 装新的）
- **Google Chrome**（你日常用的就行；patchright 自己另装 Chromium for Testing，不冲突）
- **手机淘宝 App + 手机京东 App**（扫码登录用）

## 1. 拉代码

```bash
git clone https://github.com/GordonWang1878/JD-Crawler.git
cd JD-Crawler
```

## 2. 装 Python 依赖

```bash
pip3 install -r requirements.txt
```

## 3. 装 patchright 自带的 Chromium for Testing

```bash
patchright install chromium
```

这会下载约 100MB 到 `~/Library/Caches/ms-playwright/`。这个独立 Chromium **不影响你日常的 Chrome**。

## 4. 准备京东 profile 池（首次配置，5-10 分钟）

京东反爬严，需要预备 3 个独立 profile 轮转。每个 profile 需要你手动扫码登录一次：

```bash
python3 prepare_jd_profile_pool_patchright.py 3
```

按提示操作：
- 弹出 chromium 窗口 → 扫码登录京东 → 回终端按回车关闭 → 进入下一个 profile
- 3 个 profile 可以用同一个京东账号登录（每个 profile 在京东那里是独立"身份"）

完成后 `jd_chrome_profile_pool/profile_1/2/3` 都会有登录态。这步**只做一次**，profile 持久化。

> 💡 如果想多准备几个 profile（爬量大时切换更多）：`python3 prepare_jd_profile_pool_patchright.py 5`

## 5. 启动 Web 服务

```bash
python3 app.py
```

浏览器打开 [http://localhost:5001](http://localhost:5001)

## 6. 跑起来

### 京东批量爬取
1. 左 panel 选「京东」tab
2. **下载模板** → 填入你要爬的商品 URL（也支持只填 ProductKey）→ 上传
3. 点「开始爬取」
4. crawler 自动 spawn `profile_1` 的 chromium → 跑 → 连续 3 次失败时自动切换 `profile_2/3`
5. 跑完下载 Excel；如果有失败项，点「重试失败项」自动补完

### 天猫批量爬取（独立模块）
1. 左 panel 切到「天猫淘宝」tab
2. **下载天猫模板** → 必填商品 URL 列 → 上传
3. 点「开始爬取」→ 弹 Chrome 扫码登录淘宝（每次都要扫，淘宝反爬比京东更严）
4. 后续流程跟京东类似

---

## 限流参数（已内置默认值）

文件：`app.py` 顶部

| 参数 | 默认 | 说明 |
|---|---|---|
| `JD_BATCH_SIZE` | 25 | 京东单批商品数 |
| `JD_BATCH_COOLDOWN` | 600 秒 | 京东批次间冷却 |
| `TMALL_BATCH_SIZE` | 25 | 天猫单批商品数 |
| `TMALL_BATCH_COOLDOWN` | 1500 秒 | 天猫批次间冷却 |

跑得稳了想加快可以缩短 cooldown；被反爬就拉长。改完需要重启 `python3 app.py`。

---

## 常用维护命令

**端口 5001 被占用**：
```bash
lsof -ti :5001 | xargs kill -9
```

**清理京东 profile 池重新扫码**（profile 累积风控分到全部失效时）：
```bash
rm -rf jd_chrome_profile_pool
python3 prepare_jd_profile_pool_patchright.py 3
```

**清掉旧的输出文件**：
```bash
rm outputs/*.xlsx
```

**端口 9222 上有遗留 Chrome 进程**：
```bash
lsof -ti :9222 | xargs kill -9
```

---

## 故障排查

### 京东第 1 条就 `reason=403`
- 检查 `jd_chrome_profile_pool/profile_1` 是不是有登录态（用 `prepare_jd_profile_pool_patchright.py` 重做一次）
- 用同一账号登录你日常 Chrome 试访问 `https://item.jd.com/100015253059.html`：如果日常 Chrome 也被拦 → 账号被深度风控，等 24-48 小时或换账号

### 天猫每条都 `slider=True`
- 滑块拦截，需要手动在 chrome 窗口拖动滑块过验证；过完后 crawler 会自动继续

### 京东 chromium 启动失败
- 可能是 `patchright install chromium` 没成功，重新跑一次
- 或者 9222 端口被占用（看上面"维护命令"）

### "找不到 patchright 模块"
```bash
pip3 install patchright>=1.59.0
patchright install chromium
```

---

## 文件结构（精简版）

```
JD-Crawler/
├── app.py                                      # Flask Web 服务(京东+天猫)
├── jd_crawler_patchright.py                    # 京东爬虫(patchright 版,主)
├── jd_crawler_via_search.py                    # 京东爬虫(selenium 旧版,fallback)
├── jd_profile_pool.py                          # 京东 profile 池工具
├── tmall_crawler.py                            # 天猫爬虫(selenium + undetected-chromedriver)
├── prepare_jd_profile_pool_patchright.py       # 初始化京东 profile 池(扫码)
├── templates/batch.html                        # 前端单页
├── requirements.txt
└── outputs/                                    # 爬取结果 Excel(gitignore)
```

不入 git 的目录：`jd_chrome_profile_pool/`（profile 池含 cookies,几百 MB）、`outputs/`、`uploads/`、`*.pkl`

---

## 跨平台说明

`prepare_jd_profile_pool_patchright.py` 用 patchright 启动 chromium，**跨平台通用**（不依赖 Mac 路径）。

`tmall_crawler.py` 和旧 `jd_crawler_via_search.py` 用 undetected-chromedriver，需要本地装 Chrome，**Mac 路径已硬编码**：

```python
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
```

如果在 Linux/Windows 跑，要改 `_detect_chrome_version()` 里的路径。
