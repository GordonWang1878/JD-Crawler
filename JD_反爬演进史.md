# 京东价格爬虫：反爬演进史

> 本文按时间线回顾从 2025-12 至 2026-05 半年内，京东商品页爬取在风控对抗中走过的每一步。
> 用于回看踩过的坑、解决方案、京东风控逐步收紧的规律。
> 来源：git log + CHANGELOG + 现网代码注释。

---

## TL;DR — 整条对抗主线

| 阶段 | 时间 | 京东风控点 | 我们的对策 |
|------|------|-----------|-----------|
| 0 | 2025-12-03 | 检测 selenium 指纹，访问商品页直接 403 | 普通 Selenium，被秒杀 |
| 1 | 2025-12-03 | 同上 | `undetected-chromedriver` + 搜索→点击的"伪人"路径 |
| 2 | 2025-12-04 | 连续搜索本身触发验证页 | 跳过搜索直接访问商品页 + 首次手动验证一次 |
| 3 | 2025-12-08~09 | （不是反爬）DOM 价格元素 97 个候选误抓 | 关键词过滤 + 删除线识别 + 容器限定选择器 |
| 4 | 2025-12-08 | 重定向到首页有歧义 | 区分 `?d`（终态 not_found）vs 其他首页重定向（blocked 可重试） |
| 5 | 2026-04-24 | 京东 DOM 改版，旧选择器全失效 | 重写为 `.product-price--value` / `.product-price--gray` + warmup + 渐进式延迟 + 失败冷却 |
| 6 | 2026-05-22 上午 | 京东直接识别 selenium/chromedriver，attach 模式也失效 | **迁移到 patchright** + profile 池 + 自动批次冷却 |
| 7 | 2026-05-22 下午 | 即使 patchright，~20 条/批后照样全员重定向（`reason=403`）| 商品页改 **点击导航**（注入隐藏 `<a>` + `locator.click()`），触发 user activation flag |
| 8 | 2026-05-22 晚 | playwright sync 工作线程在 Flask 长时间挂机后死掉，但 `.url` 仍返回旧值 → 假阳性"会话存活" | `is_session_valid()` 改成 `page.evaluate("1")` 走 CDP 真探活；加 `/api/reset_browser` 一键复位 |
| 9 | 2026-06-18~19 | ① 登录态检测页（订单中心）被风控误判，扫码后反复刷回登录页 ② PC 频控页（`pc-frequent-pro`）实测是**账号级**封控：同账号换 profile/浏览器无效，**同 IP 换账号即恢复** | ① 登录检测页改 `home.jd.com`（非风控页）② 确认 profile 池须**每 profile 不同账号**才有用；加爬取强度档位（常规/快速，加强=100/批必挂已删）③ 顺手修了 retry 的数据丢失链 + 错误文件持久化 |

---

## Phase 0 — 起点：裸 Selenium（2025-12-03）

**方案**：普通 `selenium` + ChromeDriver，直接 `driver.get("https://item.jd.com/<id>.html")`。

**反爬表现**：
- 商品页响应几乎瞬间 302 → `https://www.jd.com/?reason=403`
- 浏览器 navigator.webdriver = true，京东握手阶段就识别

**结论**：完全跑不通。

---

## Phase 1 — undetected-chromedriver + 搜索式访问（2025-12-03）

**关键 commit**：`6410b9c` → `8dc6812`

**调整**：
1. 换 `undetected-chromedriver` 替代普通 selenium —— 自动消除 `navigator.webdriver` 等指纹
2. 解决 Chrome 版本匹配（`version_main=142`），引入自动检测
3. 把流程改成"人类路径"：
   - 打开首页
   - 搜索框输入商品名
   - 在搜索结果列表里点击商品链接
4. 点击导航的方式天然带 `link_clicked` 类型 → 京东把它当真人

**效果**：不再被 302 到 `?reason=403`，可以稳定进商品页。

---

## Phase 2 — 跳过搜索直访 + 浏览器稳定性（2025-12-04）

**关键 commit**：`3ca7b8b` 跳过搜索；`a9748f9` 会话恢复

**新发现的风控**：
- **连续搜索**本身也是高危行为，搜几次后被定位到 JD 风控验证页
- 验证页过一次后，session 在一段时间内"洗白"，后续直访商品页就行

**调整**：
- 流程改成：首次出现验证页 → 提示用户手动完成 → 后续直接 `driver.get(item_url)`
- 浏览器稳定性补丁：
  - `invalid session id` 检测
  - 每 50 个商品定期重启浏览器释放内存
  - 智能重试最多 2 次
  - 第 22 个商品后整批崩溃的问题修复

---

## Phase 3 — 价格提取精度大改造（2025-12-08 → 12-12）

> 这一阶段严格说不是反爬，但是当时占用了大量时间。京东商品页 DOM 极其嘈杂（保险、运费、配送、电池容量 `mAh` 都长得像价格），价格候选一度高达 97 个。

**踩过的连环坑**：
- Bug：抓到产品规格里的"100W大功率"当价格（`affa66f`）
- Bug：把 211 限时达的"211"当价格（`e310be3`）
- Bug：日常价/到手价/补贴价识别漏（`2ef4538`）
- Bug：CSS `text-decoration: line-through` 的删除线没被识别，只检查了 `<del>` 标签（`45c0d93`）

**最终方案**：
1. **容器限定**：先定位 `.itemInfo-wrap` / `.product-intro` / `#choose` / `#detail`，只在容器内搜（`feb8570`）
2. **超精确选择器**：`.p-price .price`、`.p-price del`、`#summary-price .price`、`#summary-price del`（`e440526`）
3. **删除线三重检测**：`<del>` 标签 + 在 `<del>` 内 + CSS `textDecoration` 样式
4. **关键词排除**：积分、优惠券、满减、运费、送达、mAh、限时达、京准达、物流、功率、W大、颜色、版本、规格
5. **去重保留有标注的**：相同价格优先保留有删除线/有关键词的那个（`62dde3e`）

**结果**：价格候选 97 → 4-11 个，准确率从 ~40% 升到 100%。

---

## Phase 4 — 商品状态精准分级（2025-12-08 / 12-18）

**关键 commit**：`5b99d29`

**问题**：之前所有失败都标 N/A，无法区分"真没货"和"临时被拦"，导致重试逻辑要么漏重试要么瞎重试。

**新增 5 种状态**：

| 状态 | 触发条件 | 终态/可重试 |
|------|---------|------------|
| `not_found` | 重定向到 `https://www.jd.com/?d` | 终态 |
| `unavailable` | 页面含"已下柜/已下架/已售馨"等关键字 | 终态 |
| `blocked` | 重定向到风控页 / `risk_handler` / `verify` | 可重试 |
| `forbidden` | URL 含 `error` + `403` | 可重试 |
| `N/A (Retry)` | 价格提取失败 | 可重试 |

`?d` vs 其他首页重定向的区分是个隐形坑 —— 京东对"商品被删除"用 `?d` 这个具体参数，其他重定向是软拒绝。

---

## Phase 5 — Web UI 化 + 登录流程优化（2025-12-19 ~ 12-22）

**关键 commit**：`ce2e8d4` → `8afb909`

不是反爬技术变化，但深度改变了开发反馈节奏：
- Flask + Socket.IO 把一切搬到浏览器
- 阻塞 `input()` 改为轮询登录态（每 5 秒，最多 3 分钟），适配后台执行
- Material Design 一套
- 最终砍掉数据库版本，保留轻量版

---

## Phase 6 — 京东 DOM 改版 + 软反爬策略（2026-04-24）

**关键 commit**：`5ec89c1`

**京东新动作**：
- 商品页 DOM 整体改版，旧的 `.p-price .price` 全失效，价格抓取 100% 失败
- 同时反爬节奏明显收紧

**调整**：

价格选择器全部重写：
- `.product-price--value` — 当前售价/促销价
- `.product-price--gray` — 划线原价/日常价
- `.calculator-product-info .product-price` — fallback
- `.product-price` / `.p-price .price` — 旧版兜底

软反爬四件套（这一版还是 selenium）：
1. **warmup**：登录后 首页 → 搜索 → 点商品 → 返回，约 30 秒模拟正常浏览
2. **渐进式延迟**：前 10 个 2-4s / 11-20 4-7s / 之后 6-10s
3. **连续失败冷却**：2 次连续失败触发 30s → 60s → 90s（最多 120s），冷却后访问首页"重置"会话
4. **浏览器会话跨批复用**：批次结束不关浏览器，避免重复初始化

---

## Phase 7 — selenium 彻底被识别 → 迁移到 patchright（2026-05-22 上午）

**关键 commit**：`cb48441`

**京东大升级**：
- 2026 年 5 月，京东开始**直接识别 selenium / chromedriver 本身**
- 即使是 selenium 通过 CDP 9222 端口 attach 已经存在的 Chrome（这种用户态启动的 Chrome 之前能"洗白"指纹），现在也失效
- undetected-chromedriver 也不够了

**迁移方案**：换 `patchright`（Playwright 的反检测 fork）

为什么 patchright 行：
- 从源码层修补 CDP 命令暴露点：`navigator.webdriver`、`Runtime.enable` 等
- 修补 chromedriver 启动参数指纹
- 修补 webdriver 自动注入的 `cdc_xxx` JS 函数
- 用 `launch_persistent_context` 直接接管 profile 目录，**完全不走 CDP attach 这条路**

**配套改造**：

1. **Profile 池**（`jd_profile_pool.py`）：
   - `jd_chrome_profile_pool/profile_1/2/3` 各自独立的 user-data-dir
   - 每个 profile 一次性扫码登录绑定一个京东账号
   - 京东把每个 profile 视为独立"身份"
   - 启动时拿 `available_profiles[0]`
   - 连续 3 次失败自动 `switch_to_next_profile()`，关 context → 启动下一个
   - 池耗尽时当前批次剩余标 `skipped`，下一批等满冷却期再从 `profile_1` 重新开始

2. **批次节奏常量**：
   - `JD_BATCH_SIZE = 25`
   - `JD_BATCH_COOLDOWN = 600s`（批间冷却 10 分钟）
   - 批内每 10-15 条插入一次 `random_walk()`（去首页/购物车/我的京东）

3. **天猫顺便独立出来**（`tmall_crawler.py`）：
   - undetected-chromedriver + Selenium
   - 每次都强制扫码登录（淘宝检测 cookie 复用）
   - 独立批次参数（`TMALL_BATCH_SIZE=25 / COOLDOWN=1500s`）

---

## Phase 8 — user activation 检测：点击导航（2026-05-22 下午）

**关键 commit**：`3f93ea4`

**新发现的风控**：
即使在 patchright 加持下，每批 ~20 条之后**所有**商品页请求开始 302 到 `jd.com/?reason=403`。
- 真人继续在同一个浏览器手动点商品页 → 仍然能进
- 程序 `page.goto()` → 全部被拦

**根因定位**：京东开始检测两个浏览器层面的信号：
1. `navigator.userActivation` 标志 —— 程序化 `goto` 不带这个 flag
2. Navigation type —— `page.goto()` 是 `typed`，真人点链接是 `link_clicked`

**解法** —— `_navigate_via_click()`（patchright 版核心改造）：

```python
# 1. 在当前页 evaluate 注入一个隐藏可点击的 <a>
a = document.createElement('a');
a.href = target_url;
a.style.cssText = 'position:fixed;top:80px;left:80px;width:40px;height:20px;...';

# 2. 用 patchright locator.click() 模拟真实鼠标，带 mousedown→mouseup 延迟
with page.expect_navigation(wait_until='domcontentloaded'):
    page.locator(f'#{link_id}').click(delay=random.randint(40, 120))
```

这套机制做到：
- 携带 `user activation flag`
- 导航类型 = `link_clicked`
- 触发真实的 hover + click 事件

**优化策略**：
- 仅商品页用 `_navigate_via_click`（高风险）
- 首页、购物车、我的京东等非风控页面继续 `page.goto()`（不暴露不必要的指纹）
- 当前页若是风控/403/空白页，先 `goto` 回首页拿干净起点再点

**实测效果**：
- 反爬上限从每批 ~20 条 → 每批 25 条稳态 0 触发

---

### Phase 8 的副带修复：`product_id` 必须从 URL 解析

**关键 commit**：`3f93ea4` 第二个修复

Excel 里 `ProductKey` 列是另一个系统的 ID，经常被污染成 `<JD_ID>|<商品中文名>` 这种脏字符串。如果代码 fallback 到这列拼 URL，会构造出 `item.jd.com/12345|商品名.html` 这种畸形 URL，京东把它当怪请求 → 触发风控。

**规则**（已写入 CLAUDE.md）：
- 所有 `crawler.get_price_via_search(...)` 调用前，`product_id` 必须用 `re.search(r'/(\d+)\.html', url).group(1)` 从 URL 解析
- 解析失败 → 行作废，不 fallback
- `ProductKey` 仅用于 Excel 输出的展示列

---

## Phase 9 — 死会话识别 + 重置按钮（2026-05-22 晚）

**关键 commit**：`27c467d`

**痛点**：
- Flask 进程跑几个小时后，patchright 的 sync 工作线程会死（playwright sync API 跟首次 `sync_playwright().start()` 调用的线程绑死，那个线程挂了所有调用都炸）
- 但 `self._page.url` 是 Python 端的缓存属性，死了之后仍能返回旧值
- 结果：`is_session_valid()` 返回 True，下一次操作直接 `cannot switch to a different thread (which happens to have exited)` 崩溃，整批数据全废

**解法**：

1. **`is_session_valid()` 必须走 CDP 真探活**
   ```python
   def is_session_valid(self) -> bool:
       if not self._page or not self._context:
           return False
       try:
           _ = self._page.evaluate("1")  # 强制 CDP 往返
           return True
       except Exception:
           return False
   ```
   绝不能弱化为读 `.url`。

2. **`warmup()` 改为返回 `(ok, err)` 元组**
   不再静默吞错；上层在 warmup 失败时直接 emit 醒目错误到 UI 日志，**不让僵尸浏览器进入实际爬取**。

3. **`POST /api/reset_browser` + 前端"重置浏览器"按钮**
   - 关 context、清单例、`pkill` 残留 chromium/chromedriver
   - 用户日常恢复操作不再需要重启 Flask
   - 唯一仍需 restart Flask 的场景：改了 Python 代码

4. **`TEMPLATES_AUTO_RELOAD = True`**
   改 HTML/CSS 直接 Cmd+Shift+R 刷新即可。

---

## Phase 9 — 频控账号级实锤 + retry 数据链修复 + 爬取强度档位（2026-06-18~19）

这一轮一半是反爬认知突破，一半是把 Web 工具链的可靠性补齐。

### 9.1 登录态检测页被风控误判

**症状**：profile 登录过期后，用户扫码、京东显示"登录成功"，几秒后窗口又刷回登录页，循环不止。

**根因**：`_is_logged_in_now()` 每 3 秒跳一次**订单中心**（`order.jd.com/center/list.action`）做登录态探测。订单中心是风控严页，刚扫码登录的自动化浏览器访问它会被打回 passport，于是轮询判定"未登录"。

**修复**：检测页改成**我的京东** `home.jd.com`——同样未登录会跳 passport（检测逻辑不变），但它在 `random_walk` 里就被当非风控页，不会触发"刚登录就被踢"。

### 9.2 PC 频控页是「账号级」——profile 池轮换的认知纠正

**实测对照**（2026-06-19）：
- 被封账号：换完全不同指纹的浏览器 + 不同 profile，登录**同账号** → 照样全部 403（排除 cookie/会话级）。
- **同一 IP** 下换一个**另外手机号注册的账号** → **完全正常**。变量只动账号 → **确定账号级，不是 IP 级**。

**认知纠正**：之前以为 profile 池轮换能解风控。实际上 `jd_profile_pool` 是**同账号 × N 个 cookie 罐 × 同 IP**，对账号级封控**无效**——这就是为什么轮换从没真正救过场。机制本身没错，错在 prepare 脚本提示"同一账号可登录所有 profile"。**正确做法：每个 profile 扫一个不同的京东账号。** 当前单 IP 不需要代理（瓶颈是账号不是 IP，但量大了 IP 仍可能被限，勿过度外推）。

### 9.3 retry 的数据丢失链（三连环 bug）

某次 retry 点了没反应，挖出一条故障链：
1. **Bug C（根源）**：`reset_browser` 用 `pkill -f 'Chromium'`（大写），但 patchright 进程名是 `Google Chrome for Testing`（路径只有小写 `chromium`），**匹配 0 个** → 僵尸 chromium 从没被清理，一直占着 profile 的 user-data-dir 锁。
2. **Bug A**：retry 新建 crawler 前不清理残留进程 → 撞锁 `TargetClosedError` 崩溃。
3. **Bug B（数据丢失）**：`api_crawl_retry` 在开爬**前**就把失败项从 `live_results` 删除，线程一崩，失败项既没重爬又永久丢失。

**修复**：
- pkill pattern 改 `Chrome for Testing`；新建 crawler 前先清理残留进程（`_kill_stale_browser_processes`）。
- 不再提前删；改用按**行身份**（Brand+Item+URL+Product Key，不能只用 URL——同 URL 不同 Item 是合法多行）的幂等 upsert。
- **错误文件持久化**：每次跑完/停止，除主文件外产出配对的 `*_errors.xlsx`（上传格式 5 列）。retry 优先读内存、内存空了（Flask 重启后）读最新错误文件，结果按行身份**回填主文件**。错误文件也可手动当新批次重传——retry 坏了也有退路。

### 9.4 爬取强度档位

UI 新增强度档位，接管分批/冷却：**常规**（25/批）、**快速**（50/批），冷却都 10 分钟。**加强（100/批）实测在第 3 批 ~209 条必触发频控、连续失败 100+，已从 UI 和后端移除。** 同时把天猫入口暂时隐藏，集中打磨京东。

---

## 当前对抗态势（截至 2026-06）

**稳态参数**：
- 爬取强度档位:常规 25/批、快速 50/批（`JD_SPEED_PRESETS`），冷却都 600s;加强 100/批已废
- 每 10-15 条 random_walk 一次
- 批内每商品延迟由阶段性 jitter 控制
- profile 池 3 个，连续 3 次失败自动轮转 —— **但只有每个 profile 是不同账号时才有意义**（同账号轮换对账号级封控无效）

**京东目前确认会检测**：
- selenium / chromedriver 进程级指纹 ✗
- CDP attach 模式 ✗
- `navigator.webdriver` 等 JS 端指纹 ✗
- `navigator.userActivation` flag ✗
- Navigation type（`typed` vs `link_clicked`）✗
- **账号短时累积访问量 → PC 频控页 403（账号级，~40-50 条/会话是阈值）** ← 2026-06 实锤的主硬墙
- 登录态检测页（订单中心）对刚登录的自动化浏览器敏感（已绕开，改用 home.jd.com）

**关于封控层级（2026-06 实测纠正）**：
- PC 频控页是**账号级**：同 IP 换账号即恢复 → **当前单 IP 不需要代理**;换 profile（同账号）救不了。
- 之前"IP 级永久封禁/换 profile 就能恢复"的记述**已作废**——那是同账号轮换的假象。
- 滑块/拼图验证码：仅偶尔触发，warmup 后多数可绕开。

**仍未碰到的硬墙**：
- 真正的 IP 级封禁（当前量级下同 IP 多账号仍正常，量大了未知）
- 设备指纹跨账号关联（暂未观察到新账号被旧账号牵连）

---

## 给未来自己的备忘

1. **每次京东改版优先怀疑两件事**：DOM 选择器换名 + 反爬新检测点。两者经常同时发生。
2. **不要弱化 `is_session_valid()`** —— 读缓存属性会导致假阳性，最终崩在更难调试的位置。
3. **不要用 `ProductKey` 列拼 URL** —— 脏数据会构造畸形 URL 反过来触发风控。
4. **新加的程序化跳转默认用 `_navigate_via_click`**，除非确认目标 URL 不在风控名单内（首页/购物车/我的京东可以 `page.goto`）。
5. **profile 池满了不等于今天结束**，等满批次冷却（10 分钟）再从 profile_1 开始通常能继续，但当天总量有上限，强行跑会触发更长冷却。
6. **手动 cooldown profile**：`mv jd_chrome_profile_pool/profile_1 jd_chrome_profile_pool/profile_1.cooldown`（24-48h 后改回来）—— 此命名规则会被 `list_available_profiles()` 自动排除。
7. **selenium 那一套是死代码**（`jd_crawler_via_search.py`），保留只是为了让旧 import 不炸；不要往那里加新逻辑。
8. **PC 频控页是账号级**——别再把"换 profile / profile 池轮换"当频控解药推荐。同账号轮换无效;池子要发挥作用,必须**每个 profile 一个不同账号**。当前单 IP 不需要代理。
9. **登录态检测别用风控严页**——`order.jd.com`（订单中心）会把刚登录的自动化浏览器打回登录页,造成"扫码成功又刷回"。用 `home.jd.com` 这类非风控但需登录的页。
10. **结果/retry 合并按「行身份」四元组(Brand+Item+URL+Product Key),不能只按 URL**——同一个京东商品挂多条不同 Item 是合法数据,按 URL 去重会丢行。
11. **杀 patchright chromium 用 `pkill -f 'Chrome for Testing'`,不是 `'Chromium'`**——进程名是 `Google Chrome for Testing`,路径只有小写 `chromium`,大写 pattern 匹配 0 个(僵尸进程占 profile 锁的根源)。
12. **破坏性操作必须先确认再删**——retry 旧逻辑"开爬前先删失败项"导致线程崩溃即丢数据。现在改为错误文件持久化(`*_errors.xlsx`)+ 幂等回填,崩了也不丢、Flask 重启也能重试。
