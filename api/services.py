"""
业务服务层
对应 Spring Boot 的 @Service
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from langchain_core.messages import HumanMessage, AIMessage
from langgraph_multi_agent import graph

from .schemas import ChatResponse

import asyncio
import json
from typing import AsyncGenerator

from .schemas import StreamEvent, StreamEventType


class ChatService:
    """对话服务：封装 LangGraph 调用逻辑"""

    def chat(self, user_message: str, history: list = None) -> ChatResponse:
        """
        处理一次对话请求

        Args:
            user_message: 用户当前输入
            history: 历史对话消息（可选）

        Returns:
            ChatResponse
        """
        # 1. 把历史 + 当前消息组装成 LangGraph 需要的格式
        messages = self._build_messages(history, user_message)

        # 2. 构造初始 state
        initial_state = {"messages": messages}

        # 3. 调用 LangGraph
        final_state = graph.invoke(initial_state)

        # 4. 解析最终结果
        reply = self._extract_final_reply(final_state)
        agents_used = self._extract_agents_used(final_state)
        iterations = self._count_supervisor_iterations(final_state)

        return ChatResponse(
            reply=reply,
            agents_used=agents_used,
            iterations=iterations,
        )

    @staticmethod
    def _build_messages(history: list, current_message: str) -> list:
        """
        把历史 + 当前消息组装为 LangGraph 需要的格式

        Args:
            history: [{"role": "user"|"assistant", "content": "..."}, ...]
            current_message: 当前用户消息

        Returns:
            LangChain 消息列表
        """
        messages = []

        # 1. 把历史转成 LangChain 消息对象
        if history:
            for msg in history:
                role = msg.get("role") if isinstance(msg, dict) else msg.role
                content = msg.get("content") if isinstance(msg, dict) else msg.content

                if role == "user":
                    messages.append(HumanMessage(content=content))
                elif role == "assistant":
                    messages.append(AIMessage(content=content))

        # 2. 加上当前用户消息
        messages.append(HumanMessage(content=current_message))

        return messages

    @staticmethod
    def _extract_final_reply(final_state) -> str:
        """从 state 中提取最终回复——找最后一条不带 tool_calls 的 AIMessage"""
        for msg in reversed(final_state["messages"]):
            if isinstance(msg, AIMessage) and not msg.tool_calls:
                return msg.content
        return "（未能生成回复）"

    @staticmethod
    def _extract_agents_used(final_state) -> list:
        """从 state 中提取被调用的 Agent 列表"""
        agents = []
        for msg in final_state["messages"]:
            if isinstance(msg, AIMessage) and msg.tool_calls:
                for tc in msg.tool_calls:
                    agents.append(tc["name"])
        return agents

    @staticmethod
    def _count_supervisor_iterations(final_state) -> int:
        """统计 Supervisor 思考了几轮"""
        count = 0
        for msg in final_state["messages"]:
            if isinstance(msg, AIMessage):
                count += 1
        return count

    async def chat_stream(self, user_message: str, history: list = None) -> AsyncGenerator[str, None]:
        """
        流式对话：通过 LangGraph 的 astream API 实时推送 Agent 执行过程
        """
        from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
        import time

        # 构造初始 state（用 _build_messages 复用历史拼接逻辑）
        messages = self._build_messages(history, user_message)
        initial_state = {"messages": messages}

        start_time = time.time()
        final_reply = ""

        try:
            async for chunk in graph.astream(initial_state):
                # chunk 长这样：{"节点名": {"messages": [...]}}
                for node_name, node_output in chunk.items():

                    # 处理 Supervisor 节点的输出
                    if node_name == "supervisor":
                        # 看 Supervisor 这次输出了啥
                        new_messages = node_output.get("messages", [])
                        for msg in new_messages:
                            if isinstance(msg, AIMessage):
                                if msg.tool_calls:
                                    # 路由决策：要调度某些 Agent
                                    for tc in msg.tool_calls:
                                        yield self._format_sse_event(
                                            StreamEventType.AGENT_ROUTING,
                                            {
                                                "agent": tc["name"],
                                                "task": tc["args"].get("task", ""),
                                            }
                                        )
                                else:
                                    # Supervisor 给出最终回复
                                    final_reply = msg.content
                                    yield self._format_sse_event(
                                        StreamEventType.FINAL_REPLY,
                                        {"content": msg.content}
                                    )

                    # 处理 agent_executor 节点的输出
                    elif node_name == "agent_executor":
                        new_messages = node_output.get("messages", [])
                        for msg in new_messages:
                            if isinstance(msg, ToolMessage):
                                # 子 Agent 完成工作
                                # 截取 content 前 100 字符作为 summary
                                summary = msg.content[:100] + "..." if len(msg.content) > 100 else msg.content
                                yield self._format_sse_event(
                                    StreamEventType.AGENT_COMPLETED,
                                    {
                                        "tool_call_id": msg.tool_call_id,
                                        "summary": summary,
                                    }
                                )

            # 流式结束事件
            duration_ms = int((time.time() - start_time) * 1000)
            yield self._format_sse_event(
                StreamEventType.DONE,
                {"total_duration_ms": duration_ms}
            )

        except Exception as e:
            # 异常事件
            yield self._format_sse_event(
                StreamEventType.ERROR,
                {"error": str(e)}
            )

    @staticmethod
    def _format_sse_event(event_type: StreamEventType, data: dict) -> str:
        """把事件格式化为 SSE 字符串"""
        event = StreamEvent(type=event_type, data=data)
        # SSE 格式：data: {json}\n\n
        return f"data: {event.model_dump_json()}\n\n"


# 单例服务对象
chat_service = ChatService()