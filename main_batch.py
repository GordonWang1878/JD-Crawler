#!/usr/bin/env python3
"""
京东价格批量爬取工具
支持原价和促销价双价格提取
使用搜索方式绕过反爬检测
"""
import pandas as pd
from datetime import datetime
import time
import random
import os
import re
from jd_crawler_via_search import JDCrawlerViaSearch


def main():
    """主函数"""
    print("=" * 70)
    print("京东价格批量爬取工具 - 双价格版本")
    print("=" * 70)

    # 检查cookies
    if not os.path.exists("jd_cookies.pkl"):
        print("\n⚠️  未找到登录凭据！")
        print("请先运行以下命令完成首次登录：")
        print("  python3 jd_crawler_via_search.py")
        return

    # 文件路径
    input_file = "Product URL List.xlsx"
    output_file = "Price Marks.xlsx"
    sheet_name = "JD Top Model by Brand"

    # 检查输入文件
    if not os.path.exists(input_file):
        print(f"✗ 找不到文件: {input_file}")
        return

    # 读取URL列表
    print(f"\n正在读取 {input_file}...")
    try:
        df_urls = pd.read_excel(input_file, sheet_name=sheet_name)
        print(f"✓ 成功读取 {len(df_urls)} 条记录")
    except Exception as e:
        print(f"✗ 读取Excel失败: {str(e)}")
        return

    # 获取URL列表
    if 'URL' not in df_urls.columns:
        print("✗ 未找到'URL'列")
        return

    urls = df_urls['URL'].dropna().tolist()
    print(f"  找到 {len(urls)} 个有效URL")

    # 询问用户运行模式
    print("\n" + "-" * 70)
    mode = input("选择运行模式:\n  1. 测试模式（只爬取前3个URL）\n  2. 小批量模式（爬取前10个URL）\n  3. 完整模式（爬取全部URL）\n请输入 1、2 或 3: ").strip()

    if mode == "1":
        urls = urls[:3]
        print(f"\n✓ 测试模式：将爬取前3个URL")
    elif mode == "2":
        urls = urls[:10]
        print(f"\n✓ 小批量模式：将爬取前10个URL")
    else:
        print(f"\n✓ 完整模式：将爬取全部{len(urls)}个URL")
        confirm = input(f"这将花费约 {len(urls) * 5 / 60:.0f}-{len(urls) * 10 / 60:.0f} 分钟，确认继续？(y/n): ").strip().lower()
        if confirm != 'y':
            print("已取消")
            return

    print("\n" + "-" * 70)

    # 初始化爬虫（有窗口模式，方便观察）
    print("\n初始化浏览器...")
    crawler = JDCrawlerViaSearch(headless=False)

    try:
        # 登录
        print("使用保存的cookies登录...")
        crawler.login()

        if not crawler.is_logged_in:
            print("\n✗ 登录失败，cookies可能已过期")
            print("请运行 python3 jd_crawler_via_search.py 重新登录")
            return

        print("✓ 登录成功！")

        # 记录当前时间
        runtime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 开始爬取
        results = []
        success_count = 0
        failed_count = 0
        partial_count = 0  # 只获取到一个价格

        print("\n" + "=" * 70)
        print("开始爬取价格")
        print("=" * 70 + "\n")

        for idx, url in enumerate(urls, 1):
            print(f"[{idx}/{len(urls)}] {url}")

            # 定期重启浏览器（每50个商品），避免内存泄漏
            if idx > 1 and (idx - 1) % 50 == 0:
                print(f"\n  🔄 已完成 {idx-1} 个商品，重启浏览器释放内存...\n")
                crawler.restart_browser()
                time.sleep(3)

            # 提取商品ID
            match = re.search(r'/(\d+)\.html', url)
            if not match:
                print(f"  ✗ 无法提取商品ID\n")
                results.append({
                    'Runtime': runtime,
                    'URL': url,
                    'Price': 'N/A',
                    'Promotion Price': 'N/A'
                })
                failed_count += 1
                continue

            product_id = match.group(1)

            # 获取价格（带重试机制）
            max_retries = 2
            retry_count = 0
            prices = None

            while retry_count <= max_retries:
                try:
                    # 检查会话是否有效
                    if not crawler.is_session_valid():
                        print(f"  ⚠️  会话失效，尝试重启浏览器...")
                        if not crawler.restart_browser():
                            print(f"  ✗ 浏览器重启失败")
                            break
                        time.sleep(2)

                    prices = crawler.get_price_via_search(product_id)
                    break  # 成功则退出重试循环

                except Exception as e:
                    error_msg = str(e)
                    if "invalid session id" in error_msg.lower():
                        retry_count += 1
                        if retry_count <= max_retries:
                            print(f"  ⚠️  会话失效，第 {retry_count} 次重试...")
                            if crawler.restart_browser():
                                time.sleep(2)
                                continue
                            else:
                                print(f"  ✗ 浏览器重启失败")
                                break
                        else:
                            print(f"  ✗ 重试 {max_retries} 次后仍失败")
                            break
                    else:
                        # 其他错误直接抛出
                        raise

            # 处理结果
            try:

                if prices:
                    original = prices.get('original')
                    promo = prices.get('promo')

                    # 显示结果
                    if original and promo:
                        print(f"  ✓ 原价: ¥{original}, 促销价: ¥{promo}")
                        success_count += 1
                    elif original or promo:
                        if original:
                            print(f"  ⚠️  只找到原价: ¥{original}")
                        if promo:
                            print(f"  ⚠️  只找到促销价: ¥{promo}")
                        partial_count += 1
                    else:
                        print(f"  ✗ 未找到价格")
                        failed_count += 1

                    # 保存结果
                    results.append({
                        'Runtime': runtime,
                        'URL': url,
                        'Price': original if original else 'N/A',
                        'Promotion Price': promo if promo else 'N/A'
                    })
                else:
                    print(f"  ✗ 获取失败")
                    failed_count += 1
                    results.append({
                        'Runtime': runtime,
                        'URL': url,
                        'Price': 'N/A',
                        'Promotion Price': 'N/A'
                    })

            except Exception as e:
                print(f"  ✗ 错误: {e}")
                failed_count += 1
                results.append({
                    'Runtime': runtime,
                    'URL': url,
                    'Price': 'N/A',
                    'Promotion Price': 'N/A'
                })

            # 添加延迟
            if idx < len(urls):
                delay = random.uniform(3, 5)
                print(f"  等待 {delay:.1f} 秒...\n")
                time.sleep(delay)

        # 显示统计
        print("\n" + "=" * 70)
        print("爬取完成！")
        print("=" * 70)
        print(f"  完全成功（两个价格都获取）: {success_count}")
        print(f"  部分成功（只获取一个价格）: {partial_count}")
        print(f"  失败: {failed_count}")
        print(f"  总计: {len(urls)}")
        if len(urls) > 0:
            total_success = success_count + partial_count
            print(f"  有效率: {total_success/len(urls)*100:.1f}%")

        # 保存结果
        print(f"\n正在保存结果到 {output_file}...")

        try:
            from openpyxl import load_workbook
            from openpyxl.utils.dataframe import dataframe_to_rows

            # 创建新数据
            df_new = pd.DataFrame(results)

            if os.path.exists(output_file):
                # 文件存在，追加数据（保留 Excel Table 格式）
                print(f"  检测到现有文件，追加新数据...")

                # 加载现有工作簿
                wb = load_workbook(output_file)

                # 获取 Marks sheet
                if 'Marks' in wb.sheetnames:
                    ws = wb['Marks']

                    # 找到表格（如果存在）
                    table = None
                    if ws.tables:
                        table_name = list(ws.tables.keys())[0]
                        table = ws.tables[table_name]
                        print(f"  发现 Excel Table: {table_name}")

                    # 找到最后一行
                    last_row = ws.max_row

                    # 读取现有数据行数
                    existing_count = last_row - 1  # 减去表头

                    # 追加新数据（从最后一行的下一行开始）
                    for r_idx, row in enumerate(dataframe_to_rows(df_new, index=False, header=False), start=last_row + 1):
                        for c_idx, value in enumerate(row, start=1):
                            ws.cell(row=r_idx, column=c_idx, value=value)

                    # 如果有 Table，扩展其范围
                    if table:
                        # 计算新的表格范围
                        new_last_row = last_row + len(df_new)
                        # 获取列数
                        num_cols = len(df_new.columns)
                        # 更新表格范围
                        from openpyxl.utils import get_column_letter
                        new_ref = f"A1:{get_column_letter(num_cols)}{new_last_row}"
                        table.ref = new_ref
                        print(f"  已扩展 Table 范围到: {new_ref}")

                    # 保存
                    wb.save(output_file)
                    print(f"✓ 成功追加 {len(df_new)} 条新记录")
                    print(f"  总记录数: {existing_count + len(df_new)}")

                else:
                    # Sheet 不存在，创建新的
                    df_new.to_excel(output_file, sheet_name='Marks', index=False)
                    print(f"✓ 创建新表格，保存 {len(df_new)} 条记录")

            else:
                # 文件不存在，创建新文件
                df_new.to_excel(output_file, sheet_name='Marks', index=False)
                print(f"✓ 创建新文件，保存 {len(df_new)} 条记录")

            # 显示Excel列格式
            print("\nExcel 列格式:")
            print("  1. Runtime - 运行时间")
            print("  2. URL - 商品链接")
            print("  3. Price - 原价")
            print("  4. Promotion Price - 促销价")

        except Exception as e:
            print(f"✗ 保存失败: {str(e)}")
            # 保存到备份文件
            backup_file = f"Price_Marks_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            try:
                df_new.to_excel(backup_file, index=False)
                print(f"  已保存到备份文件: {backup_file}")
            except:
                pass

        print("\n" + "=" * 70)
        print("程序结束")
        print("=" * 70)

    except KeyboardInterrupt:
        print("\n\n程序被用户中断")
    except Exception as e:
        print(f"\n\n发生错误: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        print("\n正在关闭浏览器...")
        crawler.close()
        print("✓ 已关闭")


if __name__ == "__main__":
    main()
