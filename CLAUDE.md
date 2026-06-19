# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Flask + Socket.IO web app for batch-crawling product prices from JD.com (京东) and Tmall/Taobao. User uploads an Excel of URLs, gets back an Excel with original/promo prices.

Two independent crawler stacks share one Flask backend and one frontend (`templates/batch.html`):

- **JD** — `jd_crawler_patchright.py` is the main path (patchright = anti-detection Playwright fork). `jd_crawler_via_search.py` is a stale selenium fallback that should not be touched.
- **Tmall/Taobao** — `tmall_crawler.py`, undetected-chromedriver + Selenium. Forces QR scan every run (no cookie reuse because Taobao detects it).

There are **no tests**. Verification is done by running the app and watching the live log in the UI.

## Common commands

```bash
# Run the app (single process, foreground)
python3 app.py
# → http://localhost:5001

# Initialize the JD profile pool — one-time setup, requires manual QR scan per profile
python3 prepare_jd_profile_pool_patchright.py 3

# Install patchright's bundled Chromium for Testing (needed after pip install)
patchright install chromium

# Recover from a stuck port
lsof -ti :5001 | xargs kill -9   # Flask
lsof -ti :9222 | xargs kill -9   # leftover chromium
```

Most "restart Flask" scenarios are now handled by the **"重置浏览器" button** on the UI (left panel, bottom). Hitting `POST /api/reset_browser` closes the old patchright context, kills lingering Chromium / chromedriver, and clears the singletons so the next `开始爬取` boots a fresh session. Use this instead of restarting Flask unless you've edited Python code.

`TEMPLATES_AUTO_RELOAD = True` is set, so HTML/CSS edits don't need a Flask restart — just refresh the browser (Cmd+Shift+R to bypass cache).

## Architecture

### Request flow (JD batch crawl)

1. User uploads Excel → `POST /api/upload` → `_parse_excel()` builds row dicts and stores them; `uploaded_rows` / `uploaded_urls` are globals
2. User clicks 开始爬取 → `POST /api/crawl/start` spawns a `Thread` running `run_crawl_task_from_rows()`
3. The thread checks `crawler_instance` singleton:
   - If `is_session_valid()` → reuse (saves the 5-10s patchright boot)
   - Else → `JDCrawlerViaSearch(headless=False)` (this name is legacy; it's actually the patchright implementation)
4. `warmup()` returns `(ok, err)`. **If the session is dead, the caller emits a visible error to the UI log and aborts** instead of trying to crawl with a zombie browser
5. Input is chunked into batches of `JD_BATCH_SIZE` (25), with `JD_BATCH_COOLDOWN` (600s) between them. Inside a batch, every 10-15 items a `random_walk()` to homepage/cart/我的京东 is inserted
6. Live progress streams over Socket.IO via `emit_log()` / `emit_progress()` / `emit_result_row()`. Results accumulate in `live_results` (module global) — survives across crawls but lost on Flask restart
7. Retry button (`POST /api/crawl/retry`) re-runs retryable items (`failed/blocked/forbidden/skipped`). Source = `live_results` in-session, or the latest `*_errors.xlsx` after a Flask restart. Results are **merged back into the existing master Excel by row identity** (not blind overwrite). Each finished run also writes a paired `<master>_errors.xlsx` (upload-format, 5 cols) holding the still-failing rows — durable, re-uploadable as a fresh batch, and the retry data source. See gotchas 6 & 7.

Tmall flow is parallel (`/api/tmall/*`) but uses `tmall_crawler_instance` and `TMALL_BATCH_SIZE / COOLDOWN` constants.

### JD profile pool

`jd_profile_pool.py` manages `jd_chrome_profile_pool/profile_1/2/3` — each is a persistent Chromium user-data-dir. The crawler:

- Picks `available_profiles[0]` on init (list comes from `list_available_profiles()` which excludes any `.cooldown` / `.bak` suffix dir)
- On **3 consecutive failures** inside a batch, `switch_to_next_profile()` rotates to the next profile (closes context, relaunches)
- When the pool is exhausted, the remaining rows in the current batch are marked `skipped` and the next batch waits the full cooldown before retrying from `profile_pool[0]`

**⚠️ The pool only helps if each profile is a DIFFERENT JD account.** The PC 频控页 (`pc-frequent-pro.pf.jd.com/?reason=403`) block is **account-level** (2026-06 controlled test: same IP + different account = fine; same account + different browser/profile = still 403). The old `prepare_jd_profile_pool_patchright.py` prompt said "同一账号可登录所有 profile" — that makes rotation useless, because switching to another cookie-jar of the *same* burned account doesn't escape the block. Scan a distinct account into each profile. Same-IP is fine at current volume (no proxy needed yet). See `JD_反爬演进史.md` Phase 9.

Manual cooldown for a burned profile: `mv jd_chrome_profile_pool/profile_1 jd_chrome_profile_pool/profile_1.cooldown` (rename back after 24-48h — frequency control is time-based and self-heals).

## Non-obvious gotchas (read before editing)

These are bugs we've already hit. The fixes are in the code, but new code paths can easily regress them.

### 1. `product_id` must always be parsed from the URL

The Excel's `ProductKey` column is **another system's ID**, often polluted with `<JD_ID>|<商品中文名>` strings. Do not use it for navigation. Every place that builds a JD URL or calls `crawler.get_price_via_search(...)` must derive `product_id` via `re.search(r'/(\d+)\.html', url).group(1)`. If URL is absent/unparseable, the row is invalid — do not fall back to `ProductKey`. ProductKey is only for display/reference columns in the output Excel.

### 2. JD detects programmatic navigation (`page.goto`)

After ~20 item.jd.com visits via `page.goto()`, JD redirects everything to `jd.com/?reason=403`. Manual clicks from the same browser still work. Root cause: missing `navigator.userActivation` flag and `link_clicked` navigation type.

**Fix**: `_navigate_via_click()` in `jd_crawler_patchright.py` injects a hidden `<a>` into the current page and uses `locator.click()` with `expect_navigation()`. This sets the user activation flag and changes navigation type. Use it for **every** item page visit. Homepage / cart / my-jd random walks can stay on `page.goto()` because those URLs aren't risk-controlled.

### 3. `is_session_valid()` must call a real Playwright API, not read `.url`

`self._page.url` is a cached Python-side attribute. When the patchright sync worker thread dies (which happens after a few hours of Flask idle — playwright's sync API is bound to the thread that called `sync_playwright().start()`), `.url` still returns the old value, so a naive check returns `True` and the next operation crashes with `cannot switch to a different thread (which happens to have exited)`.

`is_session_valid()` must do `self._page.evaluate("1")` — that forces a CDP roundtrip and propagates the dead-thread error correctly. **Do not weaken this check.**

### 4. Don't restart Flask between crawls

A user closing the chromium window or letting Flask sit idle for hours doesn't require a Flask restart. The `重置浏览器` button + `/api/reset_browser` endpoint handle the cleanup. Restart Flask only when you've edited Python code.

### 5. The selenium-era `jd_crawler_via_search.py` is dead code

Kept as a fallback import target only. Real path is `jd_crawler_patchright.py`. The `_DriverShim` inner class in patchright_crawler exists specifically to satisfy `crawler.driver.xxx` calls left over from the selenium API in `app.py` — don't add new code that depends on it.

### 6. Merge results / dedup by row identity, NOT by URL

A JD product can legitimately appear on **multiple input rows with different `Item` names** (same URL, different internal SKU description). The output-Excel merge and `_upsert_live_result` key on the 4-tuple **(Brand, Item, URL, Product Key)** via `_row_identity()`. Keying on URL alone silently collapses those legitimate rows and drops data. Normal crawls `append` (preserve every row, even exact dups); only retry uses identity-based upsert (replace the stale failed row so it isn't re-retried).

### 7. Retry must not delete before it re-crawls (data-loss)

The original `api_crawl_retry` removed failed items from `live_results` **before** spawning the crawl thread; if the thread died (e.g. a stale chromium held the profile lock → `TargetClosedError`), the items were gone forever. Rule: **never destroy the only copy before the replacement is confirmed written.** Now failed items stay in `live_results`, persist to `*_errors.xlsx`, and are only replaced (by identity) once a new result lands. The errors file also makes retry survive a Flask restart.

### 8. `_is_logged_in_now()` must probe a non-risk-controlled page

It navigates to `home.jd.com` (我的京东), NOT `order.jd.com` (订单中心). Both redirect to passport when logged out (so detection still works), but the order center is a risk-controlled page: a freshly-QR-logged-in automation browser hitting it gets bounced back to login, so the 3s poll reads "not logged in" and the window **loops back to the login page even though the scan worked**. Keep the detection page off the risk list.

### 9. Kill chromium with `pkill -f 'Chrome for Testing'`, not `'Chromium'`

patchright's process is `Google Chrome for Testing` (the path only has lowercase `chromium-1217`). `pkill -f 'Chromium'` (capital C) matches **zero** processes, so for a long time `reset_browser` never actually killed anything — zombie chromiums piled up holding profile `user-data-dir` locks. Use `_kill_stale_browser_processes()` (pattern `Chrome for Testing` / `chrome_crashpad` / `chromedriver`).

## Cross-platform note

`tmall_crawler.py` and `jd_crawler_via_search.py` hardcode the macOS Chrome path:

```python
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
```

For Linux/Windows you have to patch `_detect_chrome_version()`. `jd_crawler_patchright.py` is cross-platform (patchright ships its own Chromium).

## Setup specifics

Full step-by-step (deps + profile pool init + first run) is in `SETUP.md`. It's accurate; defer to it for environment setup questions rather than guessing.
