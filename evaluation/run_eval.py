"""
评测脚本：跑评测集，统计路由准确率和工具调用准确率
"""
import json
import os
import sys
from pathlib import Path

# 把项目根目录加入 Python path（这样能 import 上层的模块）
sys.path.insert(0, str(Path(__file__).parent.parent))

from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from langgraph_multi_agent import graph


def load_test_cases(path: str) -> list:
    """加载评测集"""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def extract_actual_routing(final_state) -> tuple:
    """
    从最终的 state 里提取：
      - 实际调用了哪些子 Agent（Supervisor 的 tool_calls）
      - 实际调用了哪些底层工具（子 Agent 内部的工具调用——通过日志记录）

    注意：子 Agent 内部的工具调用不在主图的 messages 里，
    我们目前只能从 Supervisor 层面统计——这是一个已知限制。
    """
    actual_agents = []

    for msg in final_state["messages"]:
        if isinstance(msg, AIMessage) and msg.tool_calls:
            for tc in msg.tool_calls:
                actual_agents.append(tc["name"])

    return actual_agents


def normalize_to_set(value) -> set:
    """把字符串或列表统一转成 set 方便比较"""
    if isinstance(value, str):
        return {value}
    if isinstance(value, list):
        return set(value)
    return set()


def evaluate_one(case: dict) -> dict:
    """跑一条评测样例，返回评测结果"""
    print(f"\n{'─' * 60}")
    print(f"📝 [{case['category']}] {case['query']}")

    try:
        # 抑制子 Agent 的详细日志（让评测输出更清爽）
        # 这里我们让它正常输出，调试期方便看
        initial_state = {
            "messages": [HumanMessage(content=case["query"])]
        }
        final_state = graph.invoke(initial_state)

        # 提取实际路由
        actual_agents = extract_actual_routing(final_state)

        # 比较 expected_agent
        expected_set = normalize_to_set(case["expected_agent"])
        actual_set = set(actual_agents)

        routing_correct = expected_set == actual_set

        result = {
            "category": case["category"],
            "query": case["query"],
            "expected_agent": case["expected_agent"],
            "actual_agent": actual_agents,
            "routing_correct": routing_correct,
            "error": None,
        }

        # 打印结果
        status = "✅" if routing_correct else "❌"
        print(f"  期望 Agent: {expected_set}")
        print(f"  实际 Agent: {actual_set}")
        print(f"  路由结果: {status}")

        return result

    except Exception as e:
        print(f"  ❌ 执行异常: {e}")
        return {
            "category": case["category"],
            "query": case["query"],
            "expected_agent": case["expected_agent"],
            "actual_agent": [],
            "routing_correct": False,
            "error": str(e),
        }


def summarize(results: list) -> None:
    """汇总评测结果"""
    print("\n" + "=" * 60)
    print("📊 评测汇总")
    print("=" * 60)

    total = len(results)
    correct = sum(1 for r in results if r["routing_correct"])
    error = sum(1 for r in results if r["error"] is not None)

    print(f"\n总样例数: {total}")
    print(f"路由正确: {correct}")
    print(f"路由错误: {total - correct - error}")
    print(f"执行异常: {error}")
    print(f"\n🎯 路由准确率: {correct / total * 100:.1f}%")

    # 按 category 分类统计
    print("\n📂 按场景分类:")
    by_category = {}
    for r in results:
        cat = r["category"]
        by_category.setdefault(cat, []).append(r)

    for cat, items in by_category.items():
        cat_correct = sum(1 for r in items if r["routing_correct"])
        print(f"  {cat}: {cat_correct}/{len(items)}")

    # 列出失败的样例
    failed = [r for r in results if not r["routing_correct"]]
    if failed:
        print(f"\n❌ 失败样例（{len(failed)} 条）:")
        for r in failed:
            print(f"  - [{r['category']}] {r['query']}")
            print(f"    期望: {r['expected_agent']}")
            print(f"    实际: {r['actual_agent']}")
            if r["error"]:
                print(f"    错误: {r['error']}")


def main():
    test_cases_path = Path(__file__).parent / "test_cases.json"
    test_cases = load_test_cases(test_cases_path)

    print(f"加载评测集: {test_cases_path}")
    print(f"共 {len(test_cases)} 条样例")

    results = []
    for i, case in enumerate(test_cases, 1):
        print(f"\n[{i}/{len(test_cases)}]", end="")
        result = evaluate_one(case)
        results.append(result)

    summarize(results)

    # 保存详细结果
    output_path = Path(__file__).parent / "eval_results.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n💾 详细结果已保存到: {output_path}")


if __name__ == "__main__":
    main()