"""
专业子 Agent 集合
每个 Agent 都是一个"特化的 LLM 调用"——
有自己的 system prompt 和专属工具集
"""
from openai import OpenAI
from dotenv import load_dotenv
import os
import json
from tools import (
    get_stock_price,
    get_index_info,
    get_stock_news,
    calculate_compound_interest,
)

load_dotenv()

client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com/v1"
)


# ============================================================
# 通用 Agent Loop（之前 main.py 里的逻辑，抽到这里复用）
# ============================================================
def _run_agent_loop(
        system_prompt: str,
        user_message: str,
        tools_schema: list,
        available_tools: dict,
        max_iterations: int = 5,
        agent_name: str = "Agent",
) -> str:
    """
    通用 Agent 循环。任何子 Agent 都可以复用这个函数，
    只需传入不同的 system prompt 和工具集。
    """
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    for iteration in range(1, max_iterations + 1):
        print(f"      [{agent_name}] 第 {iteration} 轮思考")

        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            tools=tools_schema,
        )
        msg = response.choices[0].message

        # 终止条件：不再调用工具
        if not msg.tool_calls:
            print(f"      [{agent_name}] 完成思考，输出回答")
            return msg.content

        # 否则执行工具
        messages.append(msg)
        for tc in msg.tool_calls:
            fn_name = tc.function.name
            fn_args = json.loads(tc.function.arguments)
            print(f"      [{agent_name}] 调用工具: {fn_name}({fn_args})")

            fn = available_tools[fn_name]
            result = fn(**fn_args)

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(result, ensure_ascii=False),
            })

    return f"[{agent_name}] 达到最大思考次数，未能完成任务"


# ============================================================
# Agent 1：Market Analyst（行情分析师）
# ============================================================
MARKET_ANALYST_PROMPT = """你是一名专业的 A 股行情分析师，专注于股票、指数、相关新闻的查询与分析。

你的工作风格：
- 数据驱动，所有结论都基于工具查询的真实数据
- 客观中立，不做投资建议，只做数据陈述与事实分析
- 简洁清晰，重点突出价格、涨跌幅、关键消息

如果用户问到本职工作之外的问题（如理财规划、复利计算），请明确说明这超出你的专业范围。
"""

MARKET_TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "get_stock_price",
            "description": "查询 A 股某只股票的最新行情",
            "parameters": {
                "type": "object",
                "properties": {
                    "stock_code": {"type": "string", "description": "6 位股票代码"}
                },
                "required": ["stock_code"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_index_info",
            "description": "查询大盘指数最新点位与涨跌幅",
            "parameters": {
                "type": "object",
                "properties": {
                    "index_name": {"type": "string", "description": "指数名，如：上证指数、深证成指、创业板指、沪深300"}
                },
                "required": ["index_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_stock_news",
            "description": "查询某只股票的最近相关新闻",
            "parameters": {
                "type": "object",
                "properties": {
                    "stock_code": {"type": "string", "description": "6 位股票代码"},
                    "limit": {"type": "integer", "description": "返回新闻条数，默认 3"}
                },
                "required": ["stock_code"]
            }
        }
    },
]

MARKET_TOOLS = {
    "get_stock_price": get_stock_price,
    "get_index_info": get_index_info,
    "get_stock_news": get_stock_news,
}


def market_analyst_agent(task: str) -> str:
    """Market Analyst Agent 入口"""
    print(f"   ▶ Market Analyst 接到任务: {task}")
    return _run_agent_loop(
        system_prompt=MARKET_ANALYST_PROMPT,
        user_message=task,
        tools_schema=MARKET_TOOLS_SCHEMA,
        available_tools=MARKET_TOOLS,
        agent_name="Market",
    )


# ============================================================
# Agent 2：Planning Agent（理财规划师）
# ============================================================
PLANNING_PROMPT = """你是一名专业的个人理财规划师，专注于储蓄目标、复利计算、定投方案等理财规划场景。

你的工作风格：
- 数学严谨，所有数字结论都通过工具计算得出，不做心算
- 强调假设前提，对收益率、年限等不确定参数明确说明
- 风险提醒，复利结果只是理论数字，需提示实际投资的不确定性

如果用户问到行情查询、个股分析等问题，请明确说明这超出你的专业范围。
"""

PLANNING_TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "calculate_compound_interest",
            "description": "复利计算：已知本金、年化收益率、年限，计算本息合计",
            "parameters": {
                "type": "object",
                "properties": {
                    "principal": {"type": "number", "description": "本金"},
                    "annual_rate": {"type": "number", "description": "年化收益率（小数，如 0.05）"},
                    "years": {"type": "integer", "description": "投资年限"}
                },
                "required": ["principal", "annual_rate", "years"]
            }
        }
    }
]

PLANNING_TOOLS = {
    "calculate_compound_interest": calculate_compound_interest,
}


def planning_agent(task: str) -> str:
    """Planning Agent 入口"""
    print(f"   ▶ Planning Agent 接到任务: {task}")
    return _run_agent_loop(
        system_prompt=PLANNING_PROMPT,
        user_message=task,
        tools_schema=PLANNING_TOOLS_SCHEMA,
        available_tools=PLANNING_TOOLS,
        agent_name="Planning",
    )


# ============================================================
# 测试：单独跑一下两个 Agent，确认它们能独立工作
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("测试 Market Analyst")
    print("=" * 60)
    result = market_analyst_agent("帮我看看贵州茅台现在的股价和最近的新闻")
    print(f"\n   最终输出: {result}\n")

    print("=" * 60)
    print("测试 Planning Agent")
    print("=" * 60)
    result = planning_agent("我有 5 万本金，按 6% 年化做 10 年复利，最后是多少？")
    print(f"\n   最终输出: {result}\n")