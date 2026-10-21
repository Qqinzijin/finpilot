"""
LangGraph 多 Agent 系统：Supervisor + Market + Planning

架构：
  - Supervisor 节点：理解用户意图，决定调用哪个子 Agent
  - Market 节点：包装 market_analyst_agent，处理行情类问题
  - Planning 节点：包装 planning_agent，处理理财类问题
  - 子 Agent 完成后回到 Supervisor，让 Supervisor 判断是否还需继续
"""
from typing import Annotated, TypedDict, Literal
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from langchain_core.tools import tool
from dotenv import load_dotenv
import os
import json

# 复用之前 agents.py 里的子 Agent
from agents import market_analyst_agent, planning_agent

load_dotenv()


# ============================================================
# 1. 定义 State
# ============================================================
class SupervisorState(TypedDict):
    """
    多 Agent 系统的全局状态
    messages: 用户与 Supervisor 之间的对话历史
              （子 Agent 的内部 messages 不放这里——它们各自管理）
    """
    messages: Annotated[list, add_messages]


# ============================================================
# 2. 准备 Supervisor 的 LLM 与"工具"
# ============================================================
# Supervisor 看到的"工具"，其实是两个子 Agent 的入口

@tool
def call_market_analyst(task: str) -> str:
    """
    把任务交给【行情分析师】Agent。
    适用场景：用户问股票实时行情、个股分析、大盘指数、相关新闻。
    例如：'茅台多少钱'、'上证指数怎么样'、'宁德时代最近有什么消息'。

    参数 task: 要交给行情分析师的具体任务描述。
    """
    print(f"\n   ▶ Supervisor 调度 Market Agent")
    return market_analyst_agent(task)


@tool
def call_planning_agent(task: str) -> str:
    """
    把任务交给【理财规划师】Agent。
    适用场景：用户问储蓄目标、复利计算、定投方案、未来收益预测。
    例如：'存 5 万 10 年是多少'、'每年 6% 复利能赚多少'。

    参数 task: 要交给理财规划师的具体任务描述。
    """
    print(f"\n   ▶ Supervisor 调度 Planning Agent")
    return planning_agent(task)


# 把两个子 Agent 当作 Supervisor 的工具
supervisor_tools = [call_market_analyst, call_planning_agent]
supervisor_tool_map = {t.name: t for t in supervisor_tools}

# 创建 Supervisor 的 LLM 并绑定工具
supervisor_llm = ChatOpenAI(
    model="deepseek-chat",
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com/v1",
).bind_tools(supervisor_tools)

# ============================================================
# 3. 定义节点
# ============================================================
SUPERVISOR_PROMPT = """你是 FinPilot 的调度中心，负责理解用户意图并把任务交给合适的专业 Agent 处理。

可用的专业 Agent：
- call_market_analyst：行情分析师，处理股票、指数、新闻类问题
- call_planning_agent:理财规划师，处理复利、定投、收益规划类问题

工作流程：
1. 分析用户问题涉及哪些领域
2. 判断是否在系统能力范围内
3. 把问题（或拆分后的子任务）交给合适的 Agent
4. 收集所有 Agent 的回答后，整合成对用户的最终回复

【系统能力边界 - 重要】
你的系统**仅支持**以下场景：
- 实时股票行情、指数点位、相关新闻查询
- 基于已知参数的复利、定投、收益计算

你的系统**不支持**以下场景，遇到此类请求时**不要调度任何 Agent**，直接礼貌说明原因：
- 交易下单、买卖操作（如"帮我买入"、"下单"等）
- 历史持仓收益计算（如"去年买的现在赚多少"——缺少历史成本工具）
- 汇率换算（系统无汇率工具）
- 与金融完全无关的问题（如天气、生活、闲聊）

【投资建议安全边界 - 重要】
对于"该不该买"、"建议买入还是卖出"这类**主观投资决策**问题：
- 可以调度 Market Agent 查询客观行情数据
- **不要**调度 Planning Agent（它是计算工具，不是决策工具）
- 在最终回复中，应当**只陈述事实、提示风险**，**不直接给出买卖建议**
- 鼓励用户基于自身风险承受能力自行决策

【整合输出原则】
- 你自己不直接回答专业问题，只做调度和整合
- 一个问题可能需要多个 Agent 协作（比如同时涉及行情和复利计算）
- 收到 Agent 的回答后，请用自然语言整合给用户
- 涉及不确定数据时（如"过去3年平均涨幅"），明确说明数据来源和局限
"""


def supervisor_node(state: SupervisorState) -> dict:
    """Supervisor 节点：思考下一步——是调度子 Agent，还是回复用户？"""
    print("\n[Supervisor 节点] 思考中...")

    # 第一次调用时，messages 里只有 user message——加上 system prompt
    messages = state["messages"]
    if not isinstance(messages[0], SystemMessage):
        messages = [SystemMessage(content=SUPERVISOR_PROMPT)] + messages

    response = supervisor_llm.invoke(messages)

    if response.tool_calls:
        print(f"[Supervisor 节点] 决定调度 {len(response.tool_calls)} 个 Agent")
    else:
        print(f"[Supervisor 节点] 决定结束并回复用户")

    return {"messages": [response]}


def agent_executor_node(state: SupervisorState) -> dict:
    """
    执行 Supervisor 请求的所有子 Agent 调用
    （等价于之前的 tool_node，只是这里的"工具"是子 Agent）
    """
    last_message = state["messages"][-1]
    tool_messages = []

    for tool_call in last_message.tool_calls:
        tool_name = tool_call["name"]
        tool_args = tool_call["args"]

        # 调用对应的子 Agent（其实就是调用包装好的 tool 函数）
        agent_func = supervisor_tool_map[tool_name]
        result = agent_func.invoke(tool_args)

        # 把子 Agent 的回答作为 ToolMessage 写回 state
        tool_messages.append(
            ToolMessage(
                content=result,
                tool_call_id=tool_call["id"],
            )
        )

    return {"messages": tool_messages}


# ============================================================
# 4. 决策函数（条件边）
# ============================================================
def supervisor_should_continue(state: SupervisorState) -> Literal["dispatch", "end"]:
    """看 Supervisor 最后一条消息——是要调度子 Agent，还是结束？"""
    last_message = state["messages"][-1]
    if last_message.tool_calls:
        return "dispatch"
    return "end"


# ============================================================
# 5. 构建图
# ============================================================
graph_builder = StateGraph(SupervisorState)

# 加节点
graph_builder.add_node("supervisor", supervisor_node)
graph_builder.add_node("agent_executor", agent_executor_node)

# 入口：START → Supervisor
graph_builder.add_edge(START, "supervisor")

# Supervisor 的条件边：要调子 Agent 就去 executor，否则结束
graph_builder.add_conditional_edges(
    "supervisor",
    supervisor_should_continue,
    {
        "dispatch": "agent_executor",
        "end": END,
    }
)

# Agent 执行完后回到 Supervisor，让它判断下一步
graph_builder.add_edge("agent_executor", "supervisor")

graph = graph_builder.compile()


# ============================================================
# 6. 运行
# ============================================================
def run(user_message: str):
    print(f"\n{'=' * 70}")
    print(f"👤 用户: {user_message}")
    print('=' * 70)

    initial_state = {
        "messages": [HumanMessage(content=user_message)]
    }

    final_state = graph.invoke(initial_state)

    # 找到最后一条 AIMessage 作为最终回复
    final_reply = ""
    for msg in reversed(final_state["messages"]):
        if isinstance(msg, AIMessage) and not msg.tool_calls:
            final_reply = msg.content
            break

    print(f"\n💬 最终回复: {final_reply}\n")
    return final_reply


if __name__ == "__main__":
    # 测试 1：纯行情问题
    run("贵州茅台现在多少钱？")

    # 测试 2：纯理财问题
    run("我有 10 万元，按 5% 年化做 20 年复利，最后是多少？")

    # 测试 3：跨领域协作
    run("我想了解一下宁德时代现在的行情，再帮我算一下如果我现在投 5 万、按 8% 年化定投 15 年是多少？")

    # 打印流程图
    print("\n" + "=" * 70)
    print("流程图：")
    print("=" * 70)
    print(graph.get_graph().draw_mermaid())