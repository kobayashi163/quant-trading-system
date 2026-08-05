# -*- coding: utf-8 -*-
"""
交易策略模块
====================================
本模块包含各种量化交易策略。
每个策略的核心任务是：根据历史数据生成"买入/卖出"信号。

策略信号说明:
    1  = 买入信号（金叉）
   -1  = 卖出信号（死叉）
    0  = 无操作（持有或空仓等待）
"""

import pandas as pd
import config
from indicators import moving_average


class MovingAverageCrossStrategy:
    """
    双均线交叉策略（最适合新手理解的经典策略）

    原理:
        - 计算短期均线（如5日）和长期均线（如20日）
        - 当短期均线从下方上穿长期均线 → "金叉" → 买入
        - 当短期均线从上方下穿长期均线 → "死叉" → 卖出

    优点: 逻辑简单，趋势跟踪效果好
    缺点: 震荡市中容易产生虚假信号
    """

    def __init__(self, short_period=None, long_period=None):
        """
        参数:
            short_period (int): 短期均线周期，默认从 config 读取
            long_period (int): 长期均线周期，默认从 config 读取
        """
        self.short_period = short_period or config.SHORT_MA_PERIOD
        self.long_period = long_period or config.LONG_MA_PERIOD
        self.name = f"双均线策略(MA{self.short_period}/MA{self.long_period})"

    def generate_signals(self, df):
        """
        生成交易信号

        参数:
            df (pd.DataFrame): 股票数据，必须包含 'close' 列

        返回:
            pd.DataFrame: 添加了以下列的数据:
                - ma_short: 短期均线
                - ma_long:  长期均线
                - signal:   交易信号（1买入 / -1卖出 / 0无操作）
                - position: 持仓状态（1持仓 / 0空仓）
        """
        df = df.copy()

        # 计算短期和长期均线
        df["ma_short"] = moving_average(df["close"], self.short_period)
        df["ma_long"] = moving_average(df["close"], self.long_period)

        # 判断金叉和死叉
        # shift(1) 表示前一天的数据，用于比较"今天 vs 昨天"
        prev_short = df["ma_short"].shift(1)
        prev_long = df["ma_long"].shift(1)

        # 金叉：昨天短均线在长均线下方，今天在上方
        golden_cross = (prev_short <= prev_long) & (df["ma_short"] > df["ma_long"])

        # 死叉：昨天短均线在长均线上方，今天在下方
        death_cross = (prev_short >= prev_long) & (df["ma_short"] < df["ma_long"])

        # 生成信号
        df["signal"] = 0
        df.loc[golden_cross, "signal"] = 1    # 买入
        df.loc[death_cross, "signal"] = -1    # 卖出

        # 计算持仓状态：买入后持仓为1，卖出后为0
        # 用信号的累积效果来跟踪持仓
        df["position"] = 0
        current_position = 0
        for i in range(len(df)):
            if df["signal"].iloc[i] == 1:
                current_position = 1
            elif df["signal"].iloc[i] == -1:
                current_position = 0
            df["position"].iloc[i] = current_position

        return df

    def __str__(self):
        return self.name


class MACDStrategy:
    """
    MACD 策略

    原理:
        - 当 DIF（快线）上穿 DEA（慢线）时买入
        - 当 DIF 下穿 DEA 时卖出

    适合有一定基础后尝试的策略。
    """

    def __init__(self, fast=12, slow=26, signal=9):
        self.fast = fast
        self.slow = slow
        self.signal = signal
        self.name = f"MACD策略({fast},{slow},{signal})"

    def generate_signals(self, df):
        from indicators import macd as calc_macd

        df = df.copy()
        df["dif"], df["dea"], df["macd_hist"] = calc_macd(
            df["close"], self.fast, self.slow, self.signal
        )

        prev_dif = df["dif"].shift(1)
        prev_dea = df["dea"].shift(1)

        buy_signal = (prev_dif <= prev_dea) & (df["dif"] > df["dea"])
        sell_signal = (prev_dif >= prev_dea) & (df["dif"] < df["dea"])

        df["signal"] = 0
        df.loc[buy_signal, "signal"] = 1
        df.loc[sell_signal, "signal"] = -1

        df["position"] = 0
        current_position = 0
        for i in range(len(df)):
            if df["signal"].iloc[i] == 1:
                current_position = 1
            elif df["signal"].iloc[i] == -1:
                current_position = 0
            df["position"].iloc[i] = current_position

        return df

    def __str__(self):
        return self.name
