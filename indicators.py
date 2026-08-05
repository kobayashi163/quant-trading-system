# -*- coding: utf-8 -*-
"""
技术指标计算模块
====================================
提供常用的技术分析指标计算函数。
所有函数都基于 pandas Series / DataFrame，方便与回测引擎配合使用。
"""

import pandas as pd
import numpy as np


def moving_average(data, period):
    """
    计算简单移动平均线（MA）

    参数:
        data (pd.Series): 收盘价序列
        period (int): 计算周期（天数）

    返回:
        pd.Series: 移动平均线序列

    举例:
        ma5 = moving_average(close_prices, 5)  # 5日均线
    """
    return data.rolling(window=period, min_periods=1).mean()


def exponential_moving_average(data, period):
    """
    计算指数移动平均线（EMA）
    EMA 比简单 MA 更重视近期价格，反应更灵敏。

    参数:
        data (pd.Series): 收盘价序列
        period (int): 计算周期

    返回:
        pd.Series: EMA 序列
    """
    return data.ewm(span=period, adjust=False).mean()


def macd(data, fast=12, slow=26, signal=9):
    """
    计算 MACD 指标（指数平滑异同移动平均线）

    MACD 由三部分组成:
        - DIF（快线）: 快速 EMA 与慢速 EMA 的差值
        - DEA（慢线）: DIF 的 EMA
        - MACD柱:   (DIF - DEA) × 2

    参数:
        data (pd.Series): 收盘价序列
        fast (int): 快线周期，默认 12
        slow (int): 慢线周期，默认 26
        signal (int): 信号线周期，默认 9

    返回:
        tuple: (dif, dea, macd_hist) 三个 pd.Series
    """
    ema_fast = exponential_moving_average(data, fast)
    ema_slow = exponential_moving_average(data, slow)
    dif = ema_fast - ema_slow
    dea = exponential_moving_average(dif, signal)
    macd_hist = (dif - dea) * 2
    return dif, dea, macd_hist


def rsi(data, period=14):
    """
    计算 RSI 指标（相对强弱指数）

    RSI 取值范围 0~100:
        - RSI > 70: 超买区域，可能即将下跌
        - RSI < 30: 超卖区域，可能即将上涨

    参数:
        data (pd.Series): 收盘价序列
        period (int): 计算周期，默认 14

    返回:
        pd.Series: RSI 序列
    """
    delta = data.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)

    avg_gain = gain.rolling(window=period, min_periods=1).mean()
    avg_loss = loss.rolling(window=period, min_periods=1).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi_values = 100 - (100 / (1 + rs))
    return rsi_values.fillna(50)  # 无数据时取中性值 50


def bollinger_bands(data, period=20, num_std=2):
    """
    计算布林带（Bollinger Bands）

    布林带由三条线组成:
        - 中轨: 移动平均线
        - 上轨: 中轨 + N倍标准差
        - 下轨: 中轨 - N倍标准差

    参数:
        data (pd.Series): 收盘价序列
        period (int): 计算周期，默认 20
        num_std (float): 标准差倍数，默认 2

    返回:
        tuple: (upper, middle, lower) 三条带线
    """
    middle = data.rolling(window=period, min_periods=1).mean()
    std = data.rolling(window=period, min_periods=1).std().fillna(0)
    upper = middle + num_std * std
    lower = middle - num_std * std
    return upper, middle, lower


def add_indicators(df):
    """
    一次性为 DataFrame 添加常用技术指标列

    参数:
        df (pd.DataFrame): 包含 'close' 列的 DataFrame

    返回:
        pd.DataFrame: 添加了各指标列的 DataFrame
    """
    close = df["close"]

    # 移动平均线
    df["ma5"] = moving_average(close, 5)
    df["ma10"] = moving_average(close, 10)
    df["ma20"] = moving_average(close, 20)
    df["ma60"] = moving_average(close, 60)

    # MACD
    df["dif"], df["dea"], df["macd_hist"] = macd(close)

    # RSI
    df["rsi"] = rsi(close, 14)

    # 布林带
    df["boll_upper"], df["boll_middle"], df["boll_lower"] = bollinger_bands(close)

    # 每日涨跌幅
    df["pct_change"] = close.pct_change() * 100

    return df
