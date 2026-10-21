"""
工具函数集合
支持双模式：USE_REAL_DATA=True 用 Tushare 真实数据，False 用 Mock 数据
便于开发期使用 Mock 快速调试，演示期切换到真实数据
"""
import os
from dotenv import load_dotenv

load_dotenv()

# 全局开关：是否使用真实数据
# 通过环境变量 USE_REAL_DATA 控制，默认 False（Mock 模式）
USE_REAL_DATA = os.getenv("USE_REAL_DATA", "false").lower() == "true"

# 懒加载 tushare（只在需要时初始化，避免没装 tushare 时整个文件挂掉）
_tushare_pro = None

def _get_tushare_pro():
    """懒加载 Tushare 客户端"""
    global _tushare_pro
    if _tushare_pro is None:
        import tushare as ts
        ts.set_token(os.getenv("TUSHARE_TOKEN"))
        _tushare_pro = ts.pro_api()
    return _tushare_pro


# ==================== 工具 1：股票行情 ====================

def _get_stock_price_mock(stock_code: str) -> dict:
    """Mock 版本"""
    mock_data = {
        "600519": {"代码": "600519", "名称": "贵州茅台", "最新价": 1453.50, "涨跌幅": 0.85, "成交量": 2156789},
        "000001": {"代码": "000001", "名称": "平安银行", "最新价": 11.25, "涨跌幅": -0.42, "成交量": 158923456},
        "600036": {"代码": "600036", "名称": "招商银行", "最新价": 36.80, "涨跌幅": 1.12, "成交量": 56234123},
        "300750": {"代码": "300750", "名称": "宁德时代", "最新价": 198.45, "涨跌幅": 2.34, "成交量": 23456789},
        "002594": {"代码": "002594", "名称": "比亚迪", "最新价": 245.60, "涨跌幅": -1.25, "成交量": 18765432},
    }
    if stock_code in mock_data:
        return mock_data[stock_code]
    return {"error": f"未找到股票代码 {stock_code}"}


def _convert_to_tushare_code(stock_code: str) -> str:
    """
    把 6 位股票代码转换为 Tushare 格式（带交易所后缀）
    600 / 601 / 603 / 605 / 688 开头 → .SH（上交所）
    其他（000 / 002 / 300）→ .SZ（深交所）
    """
    if stock_code.startswith(("600", "601", "603", "605", "688")):
        return f"{stock_code}.SH"
    else:
        return f"{stock_code}.SZ"


def _get_stock_price_real(stock_code: str) -> dict:
    """Tushare 版本：获取最近一个交易日的行情"""
    try:
        pro = _get_tushare_pro()
        ts_code = _convert_to_tushare_code(stock_code)

        # 1. 获取股票名称（基础信息）
        basic_df = pro.stock_basic(ts_code=ts_code, fields='ts_code,name')
        if basic_df.empty:
            return {"error": f"未找到股票代码 {stock_code}"}
        stock_name = basic_df.iloc[0]['name']

        # 2. 获取最近的日行情（取最近 5 天，确保至少有 1 个交易日数据）
        daily_df = pro.daily(ts_code=ts_code, limit=1)
        if daily_df.empty:
            return {"error": f"暂无 {stock_code} 的行情数据"}

        latest = daily_df.iloc[0]

        # 3. 转换为统一格式（与 Mock 保持一致）
        return {
            "代码": stock_code,
            "名称": stock_name,
            "最新价": float(latest['close']),
            "涨跌幅": float(latest['pct_chg']),
            "成交量": int(latest['vol']),
            "交易日": str(latest['trade_date']),  # 多一个日期字段，方便用户知道是哪天的数据
        }
    except Exception as e:
        return {"error": f"查询失败: {str(e)}"}


def get_stock_price(stock_code: str) -> dict:
    """
    查询 A 股某只股票的最近交易日行情

    根据 USE_REAL_DATA 环境变量自动切换 Mock / Tushare 模式
    """
    if USE_REAL_DATA:
        return _get_stock_price_real(stock_code)
    else:
        return _get_stock_price_mock(stock_code)


# ==================== 其他三个工具暂时保留 Mock 版本 ====================

def get_index_info(index_name: str) -> dict:
    """查询大盘指数（暂用 Mock，后续可改造为 Tushare 的 index_daily 接口）"""
    mock_data = {
        "上证指数": {"名称": "上证指数", "最新点位": 3268.45, "涨跌幅": 0.42, "成交额": "4523 亿"},
        "深证成指": {"名称": "深证成指", "最新点位": 10458.67, "涨跌幅": 0.68, "成交额": "5621 亿"},
        "创业板指": {"名称": "创业板指", "最新点位": 2156.89, "涨跌幅": 1.23, "成交额": "2345 亿"},
        "沪深300": {"名称": "沪深300", "最新点位": 3845.12, "涨跌幅": 0.55, "成交额": "3210 亿"},
    }
    if index_name in mock_data:
        return mock_data[index_name]
    return {"error": f"未找到指数 {index_name}"}


def get_stock_news(stock_code: str, limit: int = 3) -> dict:
    """查询股票新闻（暂用 Mock，Tushare 新闻接口需要更高积分）"""
    mock_news = {
        "600519": [
            {"标题": "贵州茅台一季度净利润同比增长 12%，超预期", "时间": "2026-04-25"},
            {"标题": "茅台集团完成董事会换届，新任董事长上任", "时间": "2026-04-23"},
            {"标题": "白酒板块持续走强，茅台领涨", "时间": "2026-04-22"},
            {"标题": "茅台宣布回购计划，金额上限 60 亿元", "时间": "2026-04-20"},
        ],
        "600036": [
            {"标题": "招商银行公布 2025 年报，净利润增长 8.3%", "时间": "2026-04-25"},
            {"标题": "招行获批发行 500 亿元金融债券", "时间": "2026-04-24"},
            {"标题": "银行板块普涨，招行涨幅居前", "时间": "2026-04-22"},
        ],
        "300750": [
            {"标题": "宁德时代发布新一代麒麟电池，能量密度提升 15%", "时间": "2026-04-25"},
            {"标题": "宁德时代与多家车企签订长期供货协议", "时间": "2026-04-23"},
            {"标题": "新能源板块回暖，宁德时代领涨", "时间": "2026-04-21"},
        ],
    }
    if stock_code in mock_news:
        return {"代码": stock_code, "新闻列表": mock_news[stock_code][:limit]}
    return {"error": f"暂无 {stock_code} 的相关新闻"}


def calculate_compound_interest(principal: float, annual_rate: float, years: int) -> dict:
    """复利计算器（纯计算工具，无需联网）"""
    final_amount = principal * (1 + annual_rate) ** years
    interest = final_amount - principal
    return {
        "本金": principal,
        "年化收益率": f"{annual_rate * 100}%",
        "投资年限": years,
        "本息合计": round(final_amount, 2),
        "总收益": round(interest, 2),
    }


# ==================== 测试 ====================
if __name__ == "__main__":
    print(f"当前模式: {'真实数据 (Tushare)' if USE_REAL_DATA else 'Mock 数据'}")
    print(f"提示: 切换模式请修改 .env 中的 USE_REAL_DATA 值\n")

    # 测试股票行情
    print("--- 测试 get_stock_price (贵州茅台) ---")
    print(get_stock_price("600519"))

    print("\n--- 测试 get_stock_price (招商银行) ---")
    print(get_stock_price("600036"))

    print("\n--- 测试 get_stock_price (宁德时代-深市) ---")
    print(get_stock_price("300750"))