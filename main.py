# -*- coding: utf-8 -*-
"""
量化交易系统 - 主程序
====================================
这是整个系统的入口程序。运行它会自动完成:
    1. 获取股票数据（真实或模拟）
    2. 计算技术指标
    3. 运行交易策略，生成买卖信号
    4. 执行回测，计算收益指标
    5. 绘制可视化图表

运行方式:
    python main.py
"""

import sys
import os
import warnings

# 屏蔽警告信息，让输出更干净
warnings.filterwarnings("ignore")

# 设置 matplotlib 中文字体
import matplotlib
matplotlib.use("Agg")  # 使用非交互式后端，确保能保存图片
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.patches import Rectangle

import pandas as pd
import numpy as np

# 导入系统模块
import config
from data_fetcher import fetch_stock_data
from indicators import add_indicators
from strategy import MovingAverageCrossStrategy, MACDStrategy
from backtest import Backtest


def setup_chinese_font():
    """设置 matplotlib 中文显示字体"""
    plt.rcParams["font.sans-serif"] = [config.CHINESE_FONT, "SimHei", "Microsoft YaHei", "Arial Unicode MS"]
    plt.rcParams["axes.unicode_minus"] = False  # 正确显示负号


def print_header(title):
    """打印格式化标题"""
    width = 56
    print()
    print("=" * width)
    print(f"  {title}")
    print("=" * width)


def print_trade_details(result):
    """打印交易明细"""
    print_header("交易明细")
    if not result.trades:
        print("  本次回测无交易记录")
        return

    print(f"  {'日期':<12} {'操作':<6} {'价格':>10} {'数量':>10} {'费用':>8} {'盈亏':>10}")
    print("  " + "-" * 60)
    for t in result.trades:
        date_str = t["date"].strftime("%Y-%m-%d") if hasattr(t["date"], "strftime") else str(t["date"])[:10]
        action = t["action"]
        price = f"¥{t['price']:,.2f}"
        shares = f"{t['shares']:,.0f}"
        cost = f"¥{t['cost']:,.2f}"
        profit = f"¥{t.get('profit', 0):,.2f}" if "profit" in t else "-"
        print(f"  {date_str:<12} {action:<6} {price:>10} {shares:>10} {cost:>8} {profit:>10}")


def plot_backtest_result(df, result, strategy, stock_code):
    """
    绘制回测结果可视化图表

    包含四个子图:
        1. 股价K线 + 均线 + 买卖点
        2. 资金曲线（总资产变化）
        3. MACD 指标
        4. 成交量
    """
    setup_chinese_font()

    fig, axes = plt.subplots(4, 1, figsize=config.FIGURE_SIZE, dpi=config.FIGURE_DPI,
                              gridspec_kw={"height_ratios": [3, 2, 1.5, 1]},
                              sharex=True)

    fig.suptitle(f"{stock_code} - {strategy} 回测结果", fontsize=16, fontweight="bold")

    # ===== 子图1: 股价 + 均线 + 买卖点 =====
    ax1 = axes[0]
    ax1.plot(df.index, df["close"], color="#333333", linewidth=1, label="收盘价")
    ax1.plot(df.index, df["ma_short"], color="#FF6B6B", linewidth=1.2, label=f"短期MA{strategy.short_period}")
    ax1.plot(df.index, df["ma_long"], color="#4ECDC4", linewidth=1.2, label=f"长期MA{strategy.long_period}")

    # 标记买入点（向上箭头）
    buy_signals = df[df["signal"] == 1]
    ax1.scatter(buy_signals.index, buy_signals["close"], marker="^",
                color="#E74C3C", s=120, zorder=5, label="买入")

    # 标记卖出点（向下箭头）
    sell_signals = df[df["signal"] == -1]
    ax1.scatter(sell_signals.index, sell_signals["close"], marker="v",
                color="#27AE60", s=120, zorder=5, label="卖出")

    ax1.set_ylabel("价格 (元)", fontsize=11)
    ax1.legend(loc="upper left", fontsize=9, ncol=3)
    ax1.grid(True, alpha=0.3)
    ax1.set_title(f"总收益率: {result.total_return:.2f}% | 最大回撤: {result.max_drawdown:.2f}%",
                   fontsize=11, color="#555555")

    # ===== 子图2: 资金曲线 =====
    ax2 = axes[1]
    ax2.plot(result.equity_curve.index, result.equity_curve.values,
             color="#2980B9", linewidth=1.5, label="策略资产")
    ax2.axhline(y=result.initial_capital, color="#999999", linestyle="--",
                linewidth=1, label=f"初始资金 ¥{result.initial_capital:,.0f}")

    # 标记最大回撤区域
    peak = result.equity_curve.expanding().max()
    drawdown = (result.equity_curve - peak) / peak * 100
    max_dd_idx = drawdown.idxmin()
    max_dd_peak_idx = result.equity_curve.loc[:max_dd_idx].idxmax()

    ax2.fill_between(result.equity_curve.index, result.equity_curve.values, peak.values,
                     where=(result.equity_curve < peak), alpha=0.2, color="#E74C3C", label="回撤区域")

    ax2.set_ylabel("总资产 (元)", fontsize=11)
    ax2.legend(loc="upper left", fontsize=9)
    ax2.grid(True, alpha=0.3)
    ax2.set_title(f"最终资产: ¥{result.final_capital:,.2f}", fontsize=11, color="#555555")

    # ===== 子图3: MACD =====
    ax3 = axes[2]
    if "dif" in df.columns and "dea" in df.columns:
        ax3.plot(df.index, df["dif"], color="#FF6B6B", linewidth=1, label="DIF")
        ax3.plot(df.index, df["dea"], color="#4ECDC4", linewidth=1, label="DEA")
        # MACD 柱状图
        colors = ["#E74C3C" if v >= 0 else "#27AE60" for v in df["macd_hist"]]
        ax3.bar(df.index, df["macd_hist"], color=colors, width=1, alpha=0.6)
        ax3.axhline(y=0, color="#999999", linewidth=0.8)
        ax3.set_ylabel("MACD", fontsize=11)
        ax3.legend(loc="upper left", fontsize=9)
    ax3.grid(True, alpha=0.3)

    # ===== 子图4: 成交量 =====
    ax4 = axes[3]
    vol_colors = ["#E74C3C" if df["close"].iloc[i] >= df["open"].iloc[i] else "#27AE60"
                  for i in range(len(df))]
    ax4.bar(df.index, df["volume"], color=vol_colors, width=1, alpha=0.6)
    ax4.set_ylabel("成交量", fontsize=11)
    ax4.grid(True, alpha=0.3)

    # 设置 X 轴日期格式
    ax4.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax4.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
    fig.autofmt_xdate(rotation=30)

    plt.tight_layout()

    # 保存图表
    if config.SAVE_CHART:
        chart_path = os.path.join(os.path.dirname(__file__), config.CHART_FILENAME)
        plt.savefig(chart_path, dpi=config.FIGURE_DPI, bbox_inches="tight")
        print(f"\n  图表已保存: {chart_path}")

    plt.close()


def main():
    """主程序入口"""
    print_header("股票量化交易系统")
    print(f"  股票: {config.STOCK_CODE}")
    print(f"  时间: {config.START_DATE} ~ {config.END_DATE}")
    print(f"  数据模式: {'iFinD真实数据' if config.DATA_MODE == 'ifind' else '模拟数据'}")
    print(f"  策略: 双均线交叉 (MA{config.SHORT_MA_PERIOD}/MA{config.LONG_MA_PERIOD})")
    print(f"  初始资金: ¥{config.INITIAL_CAPITAL:,.2f}")

    # ===== 第1步: 获取数据 =====
    print_header("第1步: 获取股票数据")
    df = fetch_stock_data()
    print(f"  数据范围: {df.index[0].strftime('%Y-%m-%d')} ~ {df.index[-1].strftime('%Y-%m-%d')}")
    print(f"  数据条数: {len(df)} 个交易日")
    print(f"\n  最近5日行情:")
    print(df[["open", "high", "low", "close", "volume"]].tail().to_string())

    # ===== 第2步: 计算技术指标 =====
    print_header("第2步: 计算技术指标")
    df = add_indicators(df)
    print("  已计算指标: MA5, MA10, MA20, MA60, MACD, RSI, 布林带")

    # ===== 第3步: 运行策略 =====
    print_header("第3步: 运行交易策略")
    strategy = MovingAverageCrossStrategy()
    df = strategy.generate_signals(df)
    print(f"  策略: {strategy}")

    buy_count = (df["signal"] == 1).sum()
    sell_count = (df["signal"] == -1).sum()
    print(f"  买入信号: {buy_count} 次")
    print(f"  卖出信号: {sell_count} 次")

    # ===== 第4步: 执行回测 =====
    print_header("第4步: 执行回测")
    bt = Backtest()
    result = bt.run(df, strategy)

    # 打印交易明细
    print_trade_details(result)

    # 打印回测摘要
    print_header("第5步: 回测结果")
    print(result.summary())

    # ===== 第5步: 绘制图表 =====
    print_header("第6步: 生成可视化图表")
    plot_backtest_result(df, result, strategy, config.STOCK_CODE)

    print_header("回测完成!")
    print(f"  图表文件: {config.CHART_FILENAME}")
    print(f"  打开图片即可查看完整的回测可视化结果。")
    print()
    print("  提示: 修改 config.py 中的参数可以调整策略和回测设置。")
    print("=" * 56)

    return result


if __name__ == "__main__":
    main()
