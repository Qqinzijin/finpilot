"""
Supervisor Agent：调度中心
负责理解用户意图，把任务路由给合适的子 Agent
"""
from openai import OpenAI
from dotenv import load_dotenv
import os
import json
from agents import market_analyst_agent, planning_agent

load_dotenv()

client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com/v1"
)


# ============================================================
# 1. 把"子 Agent"包装成 Supervisor 的"工具"
# ============================================================
# 注意：这里的 description 决定了 Supervisor 怎么选 Agent
# 写得越清晰，路由准确率越高——这是 Supervisor 的核心 prompt 工程
SUPERVISOR_TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "market_analyst_agent",
            "description": "把任务交给【行情分析师】。当用户的问题涉及股票实时行情、个股分析、大盘指数、相关新闻时使用此 Agent。例如：'茅台多少钱'、'上证指数怎么样'、'宁德时代最近有什么消息'。",
            "parameters": {
                "type": "object",
                "properties": {
                    "task": {
                        "type": "string",
                        "description": "要交给行情分析师的具体任务描述。要把用户原始意图清晰转述。"
                    }
                },
                "required": ["task"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "planning_agent",
            "description": "把任务交给【理财规划师】。当用户的问题涉及储蓄目标、复利计算、定投方案、未来收益预测时使用此 Agent。例如：'存 5 万 10 年是多少'、'每年 6% 复利能赚多少'。",
            "parameters": {
                "type": "object",
                "properties": {
                    "task": {
                        "type": "string",
                        "description": "要交给理财规划师的具体任务描述。"
                    }
                },
                "required": ["task"]
            }
        }
    }
]

SUPERVISOR_AVAILABLE_AGENTS = {
    "market_analyst_agent": market_analyst_agent,
    "planning_agent": planning_agent,
}


# ============================================================
# 2. Supervisor 主流程
# ============================================================
SUPERVISOR_PROMPT = """你是 FinPilot 的调度中心，负责理解用户意图并把任务交给合适的专业 Agent 处理。

可用的专业 Agent：
- market_analyst_agent：行情分析师，处理股票、指数、新闻类问题
- planning_agent：理财规划师，处理复利、定投、收益规划类问题

工作流程：
1. 分析用户问题涉及哪些领域
2. 把问题（或拆分后的子任务）交给合适的 Agent
3. 收集所有 Agent 的回答后，整合成对用户的最终回复

注意：
- 你自己不直接回答专业问题，只做调度和整合
- 一个问题可能需要多个 Agent 协作（比如同时涉及行情和复利计算）
- 收到 Agent 的回答后，用自然语言总结给用户，不要罗列原始回答
"""


def supervisor(user_message: str, max_iterations: int = 6):
    """Supervisor 主入口：接收用户问题，调度子 Agent，返回最终回复"""

    messages = [
        {"role": "system", "content": SUPERVISOR_PROMPT},
        {"role": "user", "content": user_message}
    ]

    print(f"\n{'='*70}")
    print(f"👤 用户: {user_message}")
    print('='*70)

    for iteration in range(1, max_iterations + 1):
        print(f"\n[Supervisor] 第 {iteration} 轮决策")

        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            tools=SUPERVISOR_TOOLS_SCHEMA,
        )
        msg = response.choices[0].message

        # 终止条件：Supervisor 决定直接回复用户
        if not msg.tool_calls:
            print(f"\n💬 最终回复: {msg.content}\n")
            return msg.content

        # 否则：Supervisor 想调度某个子 Agent
        print(f"[Supervisor] 决定调度 {len(msg.tool_calls)} 个 Agent")
        messages.append(msg)

        for tc in msg.tool_calls:
            agent_name = tc.function.name
            agent_args = json.loads(tc.function.arguments)
            print(f"   → 路由到: {agent_name}")
            print(f"      子任务: {agent_args.get('task')}")

            # 调用对应的子 Agent
            agent_func = SUPERVISOR_AVAILABLE_AGENTS[agent_name]
            agent_result = agent_func(**agent_args)

            print(f"   ← {agent_name} 返回结果")

            # 把子 Agent 的结果作为 tool result 加入对话
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": agent_result,
            })

    print(f"\n⚠️  Supervisor 达到最大迭代次数")
    return "处理超时"


# ============================================================
# 3. 测试
# ============================================================
if __name__ == "__main__":
    # 测试 1：纯行情问题——只需要 Market Agent
    supervisor("贵州茅台现在多少钱？")

    # 测试 2：纯理财问题——只需要 Planning Agent
    supervisor("我有 10 万元，按 5% 年化做 20 年复利，最后是多少？")

    # 测试 3：跨领域问题——需要两个 Agent 协作
    supervisor("我想了解一下宁德时代现在的行情，再帮我算一下如果我现在投 5 万、按 8% 年化定投 15 年是多少？")