#!/usr/bin/env python3
"""
京东价格监测工具 - 无头模式版本
适合已经登录过、有cookies的情况使用
浏览器在后台运行，不显示窗口，更稳定
"""
import pandas as pd
from datetime import datetime
import time
import random
from jd_crawler_with_login import JDCrawlerWithLogin
import os


def main():
    """主函数"""
    print("=" * 60)
    print("京东价格监测工具 - 无头模式")
    print("=" * 60)

    # 检查是否有cookies
    if not os.path.exists("jd_cookies.pkl"):
        print("\n⚠️  未找到登录凭据！")
        print("请先运行 main_with_login.py 完成首次登录。")
        print("登录后会自动保存凭据，之后就可以使用无头模式了。")
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
    print("\n" + "-" * 60)
    mode = input("选择运行模式:\n  1. 测试模式（只爬取前3个URL）\n  2. 小批量模式（爬取前10个URL）\n  3. 完整模式（爬取全部URL）\n请输入 1、2 或 3: ").strip()

    if mode == "1":
        urls = urls[:3]
        print(f"\n✓ 测试模式：将爬取前3个URL")
    elif mode == "2":
        urls = urls[:10]
        print(f"\n✓ 小批量模式：将爬取前10个URL")
    else:
        print(f"\n✓ 完整模式：将爬取全部{len(urls)}个URL")
        confirm = input(f"这将花费约 {len(urls) * 5 / 60:.0f}-{len(urls) * 8 / 60:.0f} 分钟，确认继续？(y/n): ").strip().lower()
        if confirm != 'y':
            print("已取消")
            return

    print("\n" + "-" * 60)

    # 初始化爬虫（无头模式）
    print("\n初始化无头浏览器...")
    print("提示：浏览器会在后台运行，你看不到窗口，这是正常的。")

    crawler = JDCrawlerWithLogin(headless=True)  # 无头模式

    try:
        # 登录
        print("\n使用保存的cookies登录...")
        crawler.login()

        if not crawler.is_logged_in:
            print("\n✗ 登录失败，cookies可能已过期")
            print("请运行 main_with_login.py 重新登录")
            return

        print("✓ 登录成功！")

        # 记录当前时间
        runtime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 开始爬取
        results = []
        success_count = 0
        failed_count = 0

        print("\n" + "=" * 60)
        print("开始爬取价格")
        print("=" * 60 + "\n")

        for idx, url in enumerate(urls, 1):
            print(f"[{idx}/{len(urls)}] {url}")

            # 获取价格
            price = crawler.get_price(url)

            if price:
                print(f"  ✓ 价格: ¥{price}")
                success_count += 1
            else:
                print(f"  ✗ 获取失败")
                failed_count += 1

            # 保存结果
            results.append({
                'Runtime': runtime,
                'URL': url,
                'Price': price if price else 'N/A'
            })

            # 添加延迟
            if idx < len(urls):
                delay = random.uniform(2, 4)
                print(f"  等待 {delay:.1f} 秒...\n")
                time.sleep(delay)

        # 显示统计
        print("\n" + "=" * 60)
        print("爬取完成！")
        print("=" * 60)
        print(f"  成功: {success_count}")
        print(f"  失败: {failed_count}")
        print(f"  总计: {len(urls)}")
        if len(urls) > 0:
            print(f"  成功率: {success_count/len(urls)*100:.1f}%")

        # 保存结果
        print(f"\n正在保存结果到 {output_file}...")

        try:
            # 读取现有数据
            if os.path.exists(output_file):
                try:
                    df_existing = pd.read_excel(output_file, sheet_name='Marks')
                    print(f"  发现现有数据 {len(df_existing)} 条")
                except:
                    df_existing = pd.DataFrame(columns=['Runtime', 'URL', 'Price'])
            else:
                df_existing = pd.DataFrame(columns=['Runtime', 'URL', 'Price'])

            # 创建新数据
            df_new = pd.DataFrame(results)

            # 合并
            df_combined = pd.concat([df_existing, df_new], ignore_index=True)

            # 保存
            with pd.ExcelWriter(output_file, engine='openpyxl', mode='w') as writer:
                df_combined.to_excel(writer, sheet_name='Marks', index=False)

            print(f"✓ 成功保存 {len(df_new)} 条新记录")
            print(f"  总记录数: {len(df_combined)}")

        except Exception as e:
            print(f"✗ 保存失败: {str(e)}")
            # 保存到备份文件
            backup_file = f"Price_Marks_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            try:
                df_new.to_excel(backup_file, index=False)
                print(f"  已保存到备份文件: {backup_file}")
            except:
                pass

        print("\n" + "=" * 60)
        print("程序结束")
        print("=" * 60)

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
