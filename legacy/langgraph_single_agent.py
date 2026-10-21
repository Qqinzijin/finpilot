"""
用 LangGraph 重写单 Agent：
  保留之前 chat_with_tools 的所有功能（多步推理、工具调用）
  但用图的方式来表达流程
"""
from typing import Annotated, TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage
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


# ============================================================
# 1. 定义 State
# ============================================================
class AgentState(TypedDict):
    """Agent 的全局状态"""
    messages: Annotated[list, add_messages]   # 用 add_messages reducer，自动累积


# ============================================================
# 2. 准备 LLM 和工具
# ============================================================
# LangChain 风格的 LLM 客户端
# 它会自动把工具列表"绑定"到 LLM 上，不用每次手动传 tools_schema
llm = ChatOpenAI(
    model="deepseek-chat",
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com/v1",
)

# 工具列表（LangChain 风格——直接传函数即可，会自动从 docstring 生成 schema）
from langchain_core.tools import tool

@tool
def get_stock_price_tool(stock_code: str) -> dict:
    """查询 A 股某只股票的最新行情。stock_code 是 6 位股票代码。"""
    return get_stock_price(stock_code)

@tool
def get_index_info_tool(index_name: str) -> dict:
    """查询大盘指数最新点位与涨跌幅。index_name 支持：上证指数、深证成指、创业板指、沪深300。"""
    return get_index_info(index_name)

@tool
def get_stock_news_tool(stock_code: str, limit: int = 3) -> dict:
    """查询某只股票的相关新闻。stock_code 是 6 位股票代码，limit 是返回条数。"""
    return get_stock_news(stock_code, limit)

@tool
def calculate_compound_interest_tool(principal: float, annual_rate: float, years: int) -> dict:
    """复利计算：本金、年化收益率（小数）、年限，返回本息合计。"""
    return calculate_compound_interest(principal, annual_rate, years)


tools = [
    get_stock_price_tool,
    get_index_info_tool,
    get_stock_news_tool,
    calculate_compound_interest_tool,
]

# 把工具绑定到 LLM——这一步替代了你之前手写的 tools_schema
llm_with_tools = llm.bind_tools(tools)

# 工具名 → 函数 的映射（用于工具节点执行时查找）
tool_map = {t.name: t for t in tools}


# ============================================================
# 3. 定义节点
# ============================================================
def llm_node(state: AgentState) -> dict:
    """LLM 节点：调用大模型，返回它的回复（可能含工具调用请求）"""
    print("\n  [LLM 节点] 思考中...")
    response = llm_with_tools.invoke(state["messages"])
    print(f"  [LLM 节点] 输出: {'调用工具' if response.tool_calls else '生成最终回复'}")
    return {"messages": [response]}   # 返回更新指令——把这条 message 追加到 state


def tool_node(state: AgentState) -> dict:
    """工具节点：执行 LLM 请求的所有工具调用"""
    last_message = state["messages"][-1]
    tool_messages = []

    for tool_call in last_message.tool_calls:
        tool_name = tool_call["name"]
        tool_args = tool_call["args"]
        print(f"  [工具节点] 调用 {tool_name}({tool_args})")

        # 找到工具并执行
        tool_func = tool_map[tool_name]
        result = tool_func.invoke(tool_args)

        # 构造 ToolMessage
        tool_messages.append(
            ToolMessage(
                content=json.dumps(result, ensure_ascii=False),
                tool_call_id=tool_call["id"],
            )
        )

    return {"messages": tool_messages}


# ============================================================
# 4. 决策函数（条件边的核心）
# ============================================================
def should_continue(state: AgentState) -> str:
    """看 state 最后一条消息——LLM 是否还想调工具"""
    last_message = state["messages"][-1]
    if last_message.tool_calls:
        return "use_tool"
    return "end"


# ============================================================
# 5. 构建图
# ============================================================
graph_builder = StateGraph(AgentState)

# 加节点
graph_builder.add_node("llm", llm_node)
graph_builder.add_node("tools", tool_node)

# 加边
graph_builder.add_edge(START, "llm")           # 入口：从 START 进 llm 节点

# 条件边：从 llm 节点出来后，根据 should_continue 决定去哪
graph_builder.add_conditional_edges(
    "llm",
    should_continue,
    {
        "use_tool": "tools",   # 要调工具 → 去 tools 节点
        "end": END,            # 不调工具 → 结束
    }
)

graph_builder.add_edge("tools", "llm")         # 工具节点执行完后回到 llm 节点（形成循环！）

graph = graph_builder.compile()


# ============================================================
# 6. 运行
# ============================================================
def run(user_message: str):
    print(f"\n{'='*60}")
    print(f"👤 用户: {user_message}")
    print('='*60)

    initial_state = {
        "messages": [
            SystemMessage(content="你是一个专业的金融助手，可以查询股票、指数、新闻，也能做理财计算。如果一个问题需要多步骤完成，请逐步思考、调用工具，最终给出完整答案。"),
            HumanMessage(content=user_message),
        ]
    }

    final_state = graph.invoke(initial_state)
    final_reply = final_state["messages"][-1].content
    print(f"\n💬 最终回复: {final_reply}\n")
    return final_reply


if __name__ == "__main__":
    # 测试 1：简单查询
    run("贵州茅台现在多少钱？")

    # 测试 2：多步推理
    run("我有 10 万本金，按上证指数最近的涨跌幅做复利投资 10 年，最后是多少？")

    # 打印流程图
    print("\n" + "=" * 60)
    print("流程图：")
    print("=" * 60)
    print(graph.get_graph().draw_mermaid())