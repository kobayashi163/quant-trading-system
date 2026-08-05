# -*- coding: utf-8 -*-
"""
回测引擎模块
====================================
回测 = 用历史数据"模拟"策略运行，看看如果按策略交易能赚多少钱。

本模块模拟完整的交易过程:
    1. 按策略信号在对应日期买入/卖出
    2. 计算交易成本（手续费、印花税、滑点）
    3. 跟踪资金和持仓的变化
    4. 统计收益、回撤、夏普比率等核心指标
"""

import pandas as pd
import numpy as np
import config


class BacktestResult:
    """
    回测结果容器，保存所有回测数据和统计指标
    """

    def __init__(self):
        # 交易记录
        self.trades = []           # 每笔交易明细
        # 每日数据
        self.equity_curve = None   # 资金曲线（每日总资产）
        self.position_curve = None  # 每日持仓状态
        # 统计指标
        self.total_return = 0.0       # 总收益率
        self.annual_return = 0.0      # 年化收益率
        self.max_drawdown = 0.0       # 最大回撤
        self.sharpe_ratio = 0.0       # 夏普比率
        self.win_rate = 0.0           # 胜率
        self.total_trades = 0         # 总交易次数
        self.profit_trades = 0        # 盈利交易次数
        self.loss_trades = 0          # 亏损交易次数
        self.avg_profit = 0.0         # 平均每笔交易盈亏
        self.initial_capital = 0.0    # 初始资金
        self.final_capital = 0.0      # 最终资金

    def summary(self):
        """返回格式化的回测摘要字符串"""
        lines = [
            "=" * 50,
            "           回测结果摘要",
            "=" * 50,
            f"  初始资金:       ¥{self.initial_capital:>14,.2f}",
            f"  最终资金:       ¥{self.final_capital:>14,.2f}",
            f"  总收益率:        {self.total_return:>13.2f}%",
            f"  年化收益率:      {self.annual_return:>13.2f}%",
            f"  最大回撤:        {self.max_drawdown:>13.2f}%",
            f"  夏普比率:        {self.sharpe_ratio:>13.2f}",
            "-" * 50,
            f"  总交易次数:      {self.total_trades:>13d}",
            f"  盈利次数:        {self.profit_trades:>13d}",
            f"  亏损次数:        {self.loss_trades:>13d}",
            f"  胜率:            {self.win_rate:>13.2f}%",
            f"  平均每笔盈亏:    ¥{self.avg_profit:>13,.2f}",
            "=" * 50,
        ]
        return "\n".join(lines)


class Backtest:
    """
    回测引擎

    使用方法:
        bt = Backtest()
        result = bt.run(data_with_signals, strategy)
        print(result.summary())
    """

    def __init__(
        self,
        initial_capital=None,
        commission_rate=None,
        stamp_tax_rate=None,
        slippage=None,
    ):
        self.initial_capital = initial_capital or config.INITIAL_CAPITAL
        self.commission_rate = commission_rate or config.COMMISSION_RATE
        self.stamp_tax_rate = stamp_tax_rate or config.STAMP_TAX_RATE
        self.slippage = slippage or config.SLIPPAGE

    def run(self, df, strategy=None):
        """
        执行回测

        参数:
            df (pd.DataFrame): 包含信号的数据，必须有列:
                - close: 收盘价
                - signal: 交易信号（1买入 / -1卖出 / 0无操作）
            strategy: 策略对象（仅用于显示名称）

        返回:
            BacktestResult: 回测结果
        """
        result = BacktestResult()
        result.initial_capital = self.initial_capital

        # 初始化状态
        cash = self.initial_capital   # 可用现金
        shares = 0                     # 持有股票数量
        entry_price = 0.0              # 买入价格（用于计算单笔盈亏）

        # 记录每日资产
        equity_list = []
        position_list = []

        for i in range(len(df)):
            row = df.iloc[i]
            close = row["close"]
            signal = row.get("signal", 0)
            date = row.name if hasattr(row, "name") else i

            # ---------- 执行交易 ----------
            if signal == 1 and shares == 0:
                # 买入：用全部可用资金买入（考虑滑点，买入价略高）
                buy_price = close * (1 + self.slippage)
                # 扣除手续费
                buy_cost = cash
                commission = buy_cost * self.commission_rate
                actual_buy = buy_cost - commission
                shares = actual_buy / buy_price
                cash = 0.0
                entry_price = buy_price

                result.trades.append({
                    "date": date,
                    "action": "买入",
                    "price": round(buy_price, 2),
                    "shares": round(shares, 2),
                    "cost": round(commission, 2),
                    "cash_after": round(cash, 2),
                })

            elif signal == -1 and shares > 0:
                # 卖出：卖出全部持仓（考虑滑点，卖出价略低）
                sell_price = close * (1 - self.slippage)
                proceeds = shares * sell_price
                # 手续费 + 印花税
                commission = proceeds * self.commission_rate
                stamp_tax = proceeds * self.stamp_tax_rate
                cash = proceeds - commission - stamp_tax

                # 记录这笔交易的盈亏
                trade_profit = (sell_price - entry_price) * shares - commission - stamp_tax
                result.trades.append({
                    "date": date,
                    "action": "卖出",
                    "price": round(sell_price, 2),
                    "shares": round(shares, 2),
                    "cost": round(commission + stamp_tax, 2),
                    "profit": round(trade_profit, 2),
                    "cash_after": round(cash, 2),
                })

                shares = 0
                entry_price = 0.0

            # ---------- 记录当日资产 ----------
            total_equity = cash + shares * close
            equity_list.append(total_equity)
            position_list.append(1 if shares > 0 else 0)

        # 最终资金
        result.final_capital = equity_list[-1] if equity_list else self.initial_capital

        # 构建资金曲线
        result.equity_curve = pd.Series(equity_list, index=df.index, name="equity")
        result.position_curve = pd.Series(position_list, index=df.index, name="position")

        # ---------- 计算统计指标 ----------
        self._calculate_metrics(result, df)

        return result

    def _calculate_metrics(self, result, df):
        """计算各项回测统计指标"""

        equity = result.equity_curve

        # 总收益率
        result.total_return = (result.final_capital / result.initial_capital - 1) * 100

        # 年化收益率
        trading_days = len(equity)
        if trading_days > 1:
            years = trading_days / 252  # A股每年约252个交易日
            result.annual_return = (
                (result.final_capital / result.initial_capital) ** (1 / years) - 1
            ) * 100 if years > 0 else 0

        # 最大回撤
        peak = equity.expanding().max()
        drawdown = (equity - peak) / peak * 100
        result.max_drawdown = abs(drawdown.min())

        # 夏普比率（假设无风险利率为3%）
        daily_returns = equity.pct_change().dropna()
        if len(daily_returns) > 1 and daily_returns.std() > 0:
            annual_rf = 0.03
            daily_rf = annual_rf / 252
            excess_returns = daily_returns - daily_rf
            result.sharpe_ratio = (
                np.sqrt(252) * excess_returns.mean() / daily_returns.std()
            )

        # 交易统计
        sell_trades = [t for t in result.trades if t["action"] == "卖出"]
        result.total_trades = len(sell_trades)
        result.profit_trades = sum(1 for t in sell_trades if t.get("profit", 0) > 0)
        result.loss_trades = sum(1 for t in sell_trades if t.get("profit", 0) <= 0)
        result.win_rate = (
            result.profit_trades / result.total_trades * 100
            if result.total_trades > 0
            else 0
        )
        if result.total_trades > 0:
            total_profit = sum(t.get("profit", 0) for t in sell_trades)
            result.avg_profit = total_profit / result.total_trades
