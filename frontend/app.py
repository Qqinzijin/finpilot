"""
FinPilot Streamlit 前端 - 阶段 1 基础版
特性：
- 聊天式输入框
- 消息气泡显示
- 调用 /chat 端点（非流式）
"""
import streamlit as st
import requests
import json

# ============================================================
# 1. 配置
# ============================================================
import os
API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8888")

# 页面元信息
st.set_page_config(
    page_title="FinPilot",
    page_icon="💰",
    layout="centered",
)

# ============================================================
# 2. 标题区
# ============================================================
st.title("💰 FinPilot")
st.caption("基于 LangGraph 的多 Agent 个人理财助手")

# ============================================================
# 3. 初始化对话历史
# ============================================================
# 第一次运行时初始化
if "messages" not in st.session_state:
    st.session_state.messages = []

# ============================================================
# 4. 渲染历史消息
# ============================================================
# 每次脚本重跑都会重新画一遍所有消息——所以必须从 session_state 读
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        # 如果是助手消息，显示元信息
        if msg["role"] == "assistant" and "meta" in msg:
            with st.expander("📊 调用详情"):
                st.json(msg["meta"])

# ============================================================
# 5. 输入框 + 处理用户提交
# ============================================================
user_input = st.chat_input("问点什么？比如：贵州茅台现在多少钱？")

def stream_chat_with_visualization(user_input: str, history: list):
    """
    用 SSE 流式调用后端，并实时展示思考过程

    Args:
        user_input: 当前用户消息
        history: 前面对话历史

    Returns:
        dict: {"reply": str, "agents_used": list, "iterations": int}
    """
    # 创建一个可展开的"思考过程"区域
    with st.status("🤔 FinPilot 正在思考...", expanded=True) as status:
        # 创建一个占位符给最终回复用——但先放在 status 外面会更好看
        # 暂时记录中间状态
        agents_used = []
        iterations = 0
        final_reply = ""

        try:
            response = requests.post(
                f"{API_BASE_URL}/chat/stream",
                json={"message": user_input, "history": history},
                stream=True,  # 关键：开启流式接收
                timeout=120,  # SSE 长连接，超时给宽一点
            )
            response.raise_for_status()

            # 逐行读取 SSE
            for line in response.iter_lines(decode_unicode=True):
                if not line:
                    continue

                # 跳过非 data 行（虽然我们后端没发别的，但稳妥起见）
                if not line.startswith("data:"):
                    continue

                # 解析 SSE 数据
                payload = line[5:].strip()  # 去掉 "data:" 前缀
                try:
                    event = json.loads(payload)
                except json.JSONDecodeError:
                    continue

                event_type = event.get("type")
                event_data = event.get("data", {})

                # 根据事件类型展示不同信息
                if event_type == "agent_routing":
                    agent_name = event_data.get("agent", "")
                    task = event_data.get("task", "")
                    iterations += 1

                    # 友好的展示
                    display_name = _humanize_agent_name(agent_name)
                    st.markdown(f"📍 **调度 {display_name}**")
                    if task:
                        st.caption(f"   任务：{task}")

                    if agent_name not in agents_used:
                        agents_used.append(agent_name)

                elif event_type == "agent_completed":
                    summary = event_data.get("summary", "")
                    st.markdown(f"✅ **Agent 完成**")
                    st.caption(f"   摘要：{summary[:80]}...")

                elif event_type == "final_reply":
                    final_reply = event_data.get("content", "")
                    # 不在 status 里显示——我们一会儿在外面渲染

                elif event_type == "done":
                    duration_ms = event_data.get("total_duration_ms", 0)
                    st.markdown(f"⏱️ **耗时：{duration_ms / 1000:.1f} 秒**")

                elif event_type == "error":
                    error_msg = event_data.get("error", "未知错误")
                    st.error(f"❌ 流处理出错：{error_msg}")

            # 流结束后，更新 status 状态
            status.update(
                label="✅ 思考完成",
                state="complete",
                expanded=False,  # 自动收起
            )

        except requests.exceptions.RequestException as e:
            status.update(label="❌ 请求失败", state="error")
            st.error(f"后端调用失败: {e}")
            return None

    # 最终回复在 status 外面渲染——这样收起 status 后用户依然能看到
    if final_reply:
        st.markdown(final_reply)

    return {
        "reply": final_reply,
        "agents_used": agents_used,
        "iterations": iterations,
    }


def _humanize_agent_name(agent_name: str) -> str:
    """把内部 Agent 名字转成对用户友好的展示名"""
    mapping = {
        "call_market_analyst": "市场分析 Agent",
        "call_planning_agent": "理财规划 Agent",
    }
    return mapping.get(agent_name, agent_name)

if user_input:
    # 5.1 把用户消息加到历史
    st.session_state.messages.append({
        "role": "user",
        "content": user_input,
    })

    # 5.2 立刻渲染用户消息（让用户立即看到自己输入的内容）
    with st.chat_message("user"):
        st.markdown(user_input)

    # 5.3 调用后端 + 流式展示思考过程
    with st.chat_message("assistant"):
        # 构造 history（排除当前消息）
        history = [
            {"role": m["role"], "content": m["content"]}
            for m in st.session_state.messages[:-1]
        ]

        # 调用流式函数
        result = stream_chat_with_visualization(user_input, history)

        if result and result["reply"]:
            # 显示元信息（折叠展示）
            meta = {
                "agents_used": result["agents_used"],
                "iterations": result["iterations"],
                "history_length": len(history),
            }
            with st.expander("📊 调用详情"):
                st.json(meta)

            # 把助手回复加到历史
            st.session_state.messages.append({
                "role": "assistant",
                "content": result["reply"],
                "meta": meta,
            })

# ============================================================
# 6. 侧边栏：清空对话按钮
# ============================================================
with st.sidebar:
    st.header("⚙️ 设置")

    if st.button("🗑️ 清空对话"):
        st.session_state.messages = []
        st.rerun()  # 立刻重跑脚本，让界面刷新

    st.markdown("---")
    st.markdown("**关于 FinPilot**")
    st.caption("多 Agent 协作的金融助手，覆盖行情查询、理财规划等场景。")