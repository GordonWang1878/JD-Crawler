# 配环境 + 跑起来

> 从另一台电脑拉下代码后，按这份文档操作。10 分钟装完就能开服务。
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

## 4. 启动 Web 服务

```bash
python3 app.py
```

浏览器打开 [http://localhost:5001](http://localhost:5001)

## 5. 跑起来

### 京东批量爬取
1. **配京东账号**（只有第一次要做）：左侧「03 账号池」→「管理京东账号」→「＋ 扫码新增账号」→ 手机京东扫码，登录态后台自动识别。同一对话框可验证、冷却、移除、重扫。
2. 左 panel 选「京东」tab
3. **下载模板** → 填入你要爬的商品 URL（也支持只填 ProductKey）→ 上传
4. 点「开始爬取」
5. 跑完下载 Excel；如果有失败项，点「重试失败项」自动补完

账号池两个要点：
- **一个槽位放一个不同的京东账号**。403 频控是账号级的，同账号换槽位照样被拦，轮换等于白做（2026-06 对照实测：同 IP + 不同账号 = 正常；同账号 + 不同 profile = 仍 403）。详见 `CLAUDE.md` 第 64 行与 `JD_反爬演进史.md` Phase 9-10。
- 只有 1 个账号也能跑，只是批次间没得轮换，回落到 600 秒冷却。之后拿到新账号随时在 UI 里加。

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

**账号全部失效要重来**（profile 累积风控分到全部被拦时）：在「管理京东账号」对话框里逐个「移除」再「＋ 扫码新增账号」，不要手删 `jd_chrome_profile_pool/`。

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
- 打开「管理京东账号」看该账号是不是「已登录」，点「验证」复核；掉登录态就「重扫」
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
├── profile_provision.py                        # 账号池扫码/验证/冷却/移除(UI 后端)
├── templates/batch.html                        # 前端单页
├── requirements.txt
└── outputs/                                    # 爬取结果 Excel(gitignore)
```

不入 git 的目录：`jd_chrome_profile_pool/`（profile 池含 cookies,几百 MB）、`outputs/`、`uploads/`、`*.pkl`

---

## 跨平台说明

京东账号池扫码走 patchright 启动的 chromium，**跨平台通用**（不依赖 Mac 路径）。

`tmall_crawler.py` 和旧 `jd_crawler_via_search.py` 用 undetected-chromedriver，需要本地装 Chrome，**Mac 路径已硬编码**：

```python
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
```

如果在 Linux/Windows 跑，要改 `_detect_chrome_version()` 里的路径。
