# -*- coding: utf-8 -*-
"""
数据获取模块
====================================
负责获取股票行情数据，支持两种数据源:

1. iFinD 真实数据（同花顺金融数据服务）
   - 需要配置 IFIND_AUTH_TOKEN
   - 获取真实 A 股股票的历史行情数据

2. 模拟数据（内置）
   - 无需任何配置
   - 生成符合真实市场特征的模拟 K 线数据
   - 适合学习和测试系统功能
"""

import os
import json
import math
import random
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

import config


# ============================================================
# iFinD 真实数据获取
# ============================================================

# 请求会话和 ID 管理
_sessions = {}
_req_ids = {}

# 危险字段过滤
_BLOCKED_KEYS = {"__proto__", "prototype", "constructor"}


def _get_auth_token():
    """获取 iFinD 认证 Token"""
    token = config.IFIND_AUTH_TOKEN
    if token and not token.startswith("your ") and len(token) > 10:
        return token
    return None


def _next_id(server_type):
    _req_ids[server_type] = _req_ids.get(server_type, 0) + 1
    return _req_ids[server_type]


def _make_headers(server_type=None):
    token = _get_auth_token()
    if not token:
        raise RuntimeError("iFinD Token 未配置，请在 config.py 中设置 IFIND_AUTH_TOKEN")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "Authorization": token,
    }
    if server_type in _sessions:
        headers["Mcp-Session-Id"] = _sessions[server_type]
    return headers


def _post(server_type, payload, timeout=60):
    url = config.IFIND_SERVERS[server_type]
    resp = requests.post(
        url, json=payload, headers=_make_headers(server_type),
        verify=False, timeout=timeout,
    )
    data = None
    if resp.text.strip():
        try:
            data = resp.json()
        except Exception:
            data = resp.text
    return resp, data


def _init_session(server_type):
    """初始化 iFinD MCP 会话"""
    if server_type in _sessions:
        return

    payload = {
        "jsonrpc": "2.0",
        "id": _next_id(server_type),
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "quant-system", "version": "1.0.0"},
        },
    }
    resp, _ = _post(server_type, payload, timeout=30)
    resp.raise_for_status()

    session_id = resp.headers.get("Mcp-Session-Id")
    if not session_id:
        raise RuntimeError("iFinD 初始化失败：未返回会话ID")

    _sessions[server_type] = session_id

    # 发送初始化完成通知
    requests.post(
        config.IFIND_SERVERS[server_type],
        json={"jsonrpc": "2.0", "method": "notifications/initialized"},
        headers=_make_headers(server_type),
        verify=False, timeout=10,
    )


def _list_tools(server_type):
    """获取可用工具列表"""
    _init_session(server_type)
    payload = {
        "jsonrpc": "2.0",
        "id": _next_id(server_type),
        "method": "tools/list",
        "params": {},
    }
    resp, data = _post(server_type, payload)
    resp.raise_for_status()
    return data


def _call_ifind(server_type, tool_name, params):
    """
    调用 iFinD MCP 工具

    参数:
        server_type: 服务类型，如 "stock"
        tool_name: 工具名称，如 "get_stock_performance"
        params: 参数字典
    """
    _init_session(server_type)

    payload = {
        "jsonrpc": "2.0",
        "id": _next_id(server_type),
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": params},
    }
    resp, data = _post(server_type, payload)

    if isinstance(data, dict) and "error" in data:
        return {"ok": False, "error": data["error"]}
    resp.raise_for_status()
    return {"ok": True, "data": data}


def fetch_from_ifind(stock_code, start_date, end_date):
    """
    从 iFinD 获取真实股票日频行情数据

    参数:
        stock_code (str): 股票名称或代码，如 "贵州茅台" 或 "600519.SH"
        start_date (str): 开始日期 "2024-01-01"
        end_date (str): 结束日期 "2025-12-31"

    返回:
        pd.DataFrame: 包含 open, high, low, close, volume 列的 DataFrame
    """
    # 构建查询语句
    query = f"{stock_code}从{start_date}到{end_date}的日频开盘价、最高价、最低价、收盘价、成交量"

    result = _call_ifind("stock", "get_stock_performance", {"query": query})

    if not result.get("ok"):
        raise RuntimeError(f"iFinD 查询失败: {result.get('error', '未知错误')}")

    # 解析 iFinD 返回的数据
    df = _parse_ifind_response(result["data"], stock_code)
    return df


def _parse_ifind_response(data, stock_code):
    """
    解析 iFinD API 返回的数据，转换为标准 DataFrame

    iFinD 返回格式可能为 JSON-RPC 结构，数据在 result.content 中。
    此函数尝试多种格式进行解析。
    """
    # 尝试提取文本内容
    content_text = ""

    if isinstance(data, dict):
        # JSON-RPC 格式
        result = data.get("result", {})
        if isinstance(result, dict):
            content = result.get("content", [])
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict):
                        content_text += item.get("text", "")
                    elif isinstance(item, str):
                        content_text += item
            elif isinstance(content, str):
                content_text = content
        elif isinstance(result, str):
            content_text = result
    elif isinstance(data, str):
        content_text = data

    # 尝试将文本解析为表格
    try:
        df = _parse_table_text(content_text)
        if df is not None and len(df) > 0:
            return df
    except Exception:
        pass

    # 如果无法解析，抛出带提示的异常
    raise RuntimeError(
        f"无法解析 iFinD 返回的数据。请检查股票代码 '{stock_code}' 是否正确，\n"
        f"以及日期范围是否有效。\n\n"
        f"原始返回内容（前500字符）:\n{content_text[:500]}"
    )


def _parse_table_text(text):
    """
    尝试将 iFinD 返回的文本解析为 DataFrame。
    支持 CSV、TSV 和 JSON 格式。
    """
    import io

    # 尝试 JSON 格式
    try:
        data = json.loads(text)
        if isinstance(data, list) and len(data) > 0:
            return pd.DataFrame(data)
        if isinstance(data, dict):
            # 尝试找到数据列表
            for key in ["data", "rows", "result"]:
                if key in data and isinstance(data[key], list):
                    return pd.DataFrame(data[key])
    except (json.JSONDecodeError, ValueError):
        pass

    # 尝试 CSV/TSV 格式
    for sep in [",", "\t", "|"]:
        try:
            df = pd.read_csv(io.StringIO(text), sep=sep)
            if len(df) > 0 and len(df.columns) > 1:
                return df
        except Exception:
            continue

    return None


# ============================================================
# 模拟数据生成
# ============================================================

def generate_mock_data(stock_code, start_date, end_date, base_price=1680.0):
    """
    生成模拟股票 K 线数据

    使用几何布朗运动模型生成符合真实市场特征的模拟数据:
        - 价格围绕基准价波动
        - 包含趋势和随机波动
        - 成交量与价格变动相关

    参数:
        stock_code (str): 股票名称（仅用于显示）
        start_date (str): 开始日期
        end_date (str): 结束日期
        base_price (float): 基准价格（模拟茅台约1680元）

    返回:
        pd.DataFrame: 包含 open, high, low, close, volume 列
    """
    # 生成交易日列表（跳过周末）
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    dates = []
    current = start
    while current <= end:
        if current.weekday() < 5:  # 0-4 为周一到周五
            dates.append(current)
        current += timedelta(days=1)

    n_days = len(dates)
    if n_days == 0:
        return pd.DataFrame()

    # 使用固定随机种子，确保结果可复现
    np.random.seed(42)

    # 模拟价格路径（几何布朗运动 + 趋势）
    daily_returns = np.random.normal(0.0005, 0.018, n_days)  # 日均收益0.05%，波动率1.8%

    # 添加一些趋势变化（模拟牛熊周期）
    trend_periods = np.sin(np.linspace(0, 4 * np.pi, n_days)) * 0.003
    daily_returns += trend_periods

    # 计算收盘价
    close_prices = np.zeros(n_days)
    close_prices[0] = base_price
    for i in range(1, n_days):
        close_prices[i] = close_prices[i - 1] * (1 + daily_returns[i])

    # 生成开盘价、最高价、最低价
    open_prices = np.zeros(n_days)
    high_prices = np.zeros(n_days)
    low_prices = np.zeros(n_days)
    volumes = np.zeros(n_days)

    for i in range(n_days):
        # 开盘价在前一日收盘价附近波动
        if i > 0:
            open_prices[i] = close_prices[i - 1] * (1 + np.random.normal(0, 0.005))
        else:
            open_prices[i] = base_price * (1 + np.random.normal(0, 0.005))

        # 最高价和最低价
        daily_range = abs(close_prices[i] - open_prices[i]) + close_prices[i] * np.random.uniform(0.005, 0.02)
        high_prices[i] = max(open_prices[i], close_prices[i]) + daily_range * np.random.uniform(0.3, 1.0)
        low_prices[i] = min(open_prices[i], close_prices[i]) - daily_range * np.random.uniform(0.3, 1.0)
        low_prices[i] = max(low_prices[i], close_prices[i] * 0.95)  # 最低价不低于收盘价的95%

        # 成交量（与价格波动正相关）
        base_vol = 2_000_000  # 基准成交量 200万股
        vol_change = abs(daily_returns[i]) * 50 + 0.5
        volumes[i] = int(base_vol * vol_change * np.random.uniform(0.7, 1.3))

    # 构建 DataFrame
    df = pd.DataFrame({
        "date": dates,
        "open": np.round(open_prices, 2),
        "high": np.round(high_prices, 2),
        "low": np.round(low_prices, 2),
        "close": np.round(close_prices, 2),
        "volume": volumes.astype(int),
    })
    df.set_index("date", inplace=True)

    return df


# ============================================================
# 统一数据获取接口
# ============================================================

def fetch_stock_data(stock_code=None, start_date=None, end_date=None, mode=None):
    """
    获取股票行情数据（统一入口）

    根据 mode 自动选择数据源:
        - "ifind": 从 iFinD 获取真实数据
        - "mock":  生成模拟数据

    参数:
        stock_code: 股票代码/名称，默认从 config 读取
        start_date: 开始日期，默认从 config 读取
        end_date: 结束日期，默认从 config 读取
        mode: 数据模式，默认从 config 读取

    返回:
        pd.DataFrame: 包含 open, high, low, close, volume 列
    """
    stock_code = stock_code or config.STOCK_CODE
    start_date = start_date or config.START_DATE
    end_date = end_date or config.END_DATE
    mode = mode or config.DATA_MODE

    # 数据缓存
    cache_key = f"{stock_code}_{start_date}_{end_date}_{mode}"
    cache_dir = config.CACHE_DIR
    cache_file = os.path.join(cache_dir, f"{cache_key}.csv")

    # 尝试读取缓存
    if os.path.exists(cache_file):
        print(f"  [缓存] 从本地缓存读取数据: {stock_code}")
        df = pd.read_csv(cache_file, parse_dates=["date"], index_col="date")
        return df

    if mode == "ifind":
        print(f"  [iFinD] 正在从同花顺获取真实数据: {stock_code} ({start_date} ~ {end_date})")
        try:
            df = fetch_from_ifind(stock_code, start_date, end_date)
            print(f"  [iFinD] 成功获取 {len(df)} 条行情数据")
        except Exception as e:
            print(f"  [iFinD] 获取失败: {e}")
            print(f"  [回退] 自动切换到模拟数据模式...")
            df = generate_mock_data(stock_code, start_date, end_date)
            print(f"  [模拟] 成功生成 {len(df)} 条模拟数据")
    else:
        print(f"  [模拟] 正在生成模拟数据: {stock_code} ({start_date} ~ {end_date})")
        df = generate_mock_data(stock_code, start_date, end_date)
        print(f"  [模拟] 成功生成 {len(df)} 条模拟数据")

    # 保存缓存
    os.makedirs(cache_dir, exist_ok=True)
    df.to_csv(cache_file)
    print(f"  [缓存] 数据已缓存到本地")

    return df


def clear_cache():
    """清除所有数据缓存"""
    cache_dir = config.CACHE_DIR
    if os.path.exists(cache_dir):
        import shutil
        shutil.rmtree(cache_dir)
        print("  缓存已清除")
