#!/usr/bin/env python3
"""
京东价格监测工具 - 主程序
读取Product URL List，爬取价格，保存到Price Marks
"""
import pandas as pd
from datetime import datetime
import time
import random
from jd_price_crawler_final import JDPriceCrawler
import os


def main():
    """主函数"""
    print("=" * 60)
    print("京东价格监测工具")
    print("=" * 60)

    # 文件路径
    input_file = "Product URL List.xlsx"
    output_file = "Price Marks.xlsx"
    sheet_name = "JD Top Model by Brand"

    # 检查输入文件是否存在
    if not os.path.exists(input_file):
        print(f"错误: 找不到文件 {input_file}")
        return

    # 读取URL列表
    print(f"\n正在读取 {input_file}...")
    try:
        df_urls = pd.read_excel(input_file, sheet_name=sheet_name)
        print(f"✓ 成功读取 {len(df_urls)} 条记录")
        print(f"  列: {df_urls.columns.tolist()}")
    except Exception as e:
        print(f"错误: 读取Excel失败 - {str(e)}")
        return

    # 检查URL列是否存在
    if 'URL' not in df_urls.columns:
        print("错误: 未找到'URL'列")
        return

    # 获取URL列表（去除空值）
    urls = df_urls['URL'].dropna().tolist()
    print(f"\n找到 {len(urls)} 个有效URL")

    # 初始化爬虫
    print("\n初始化爬虫...")
    crawler = JDPriceCrawler(use_selenium=False)

    # 记录当前时间
    runtime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 准备结果列表
    results = []

    # 开始爬取
    print("\n开始爬取价格...")
    print("-" * 60)

    total = len(urls)
    success_count = 0
    failed_count = 0

    for idx, url in enumerate(urls, 1):
        print(f"\n[{idx}/{total}] {url}")

        # 获取价格
        price = crawler.get_price_with_retry(url, max_retries=2)

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

        # 添加随机延迟，避免被反爬
        if idx < total:  # 不是最后一个
            delay = random.uniform(1, 3)
            print(f"  等待 {delay:.1f} 秒...")
            time.sleep(delay)

    # 关闭爬虫
    crawler.close()

    print("\n" + "-" * 60)
    print(f"爬取完成!")
    print(f"  成功: {success_count}")
    print(f"  失败: {failed_count}")
    print(f"  总计: {total}")

    # 保存结果
    print(f"\n正在保存结果到 {output_file}...")

    try:
        # 读取现有的Price Marks数据（如果存在）
        if os.path.exists(output_file):
            try:
                df_existing = pd.read_excel(output_file, sheet_name='Marks')
                print(f"  发现现有数据 {len(df_existing)} 条")
            except:
                df_existing = pd.DataFrame(columns=['Runtime', 'URL', 'Price'])
        else:
            df_existing = pd.DataFrame(columns=['Runtime', 'URL', 'Price'])

        # 创建新数据的DataFrame
        df_new = pd.DataFrame(results)

        # 合并新旧数据
        df_combined = pd.concat([df_existing, df_new], ignore_index=True)

        # 保存到Excel
        with pd.ExcelWriter(output_file, engine='openpyxl', mode='w') as writer:
            df_combined.to_excel(writer, sheet_name='Marks', index=False)

        print(f"✓ 成功保存 {len(df_new)} 条新记录")
        print(f"  总记录数: {len(df_combined)}")

    except Exception as e:
        print(f"✗ 保存失败: {str(e)}")
        # 保存到备份文件
        backup_file = f"Price_Marks_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        try:
            df_new = pd.DataFrame(results)
            df_new.to_excel(backup_file, index=False)
            print(f"  已保存到备份文件: {backup_file}")
        except:
            print("  备份也失败了")

    print("\n" + "=" * 60)
    print("程序结束")
    print("=" * 60)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n程序被用户中断")
    except Exception as e:
        print(f"\n\n发生错误: {str(e)}")
        import traceback
        traceback.print_exc()
