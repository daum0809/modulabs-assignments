"""가짜 LLM으로 그래프 연결을 검사한다. langgraph가 설치돼 있어야 하지만 API 키는 필요 없다."""
import unittest
from unittest.mock import patch

try:
    from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
    from langchain_core.messages import AIMessage

    import graph
except ImportError:  # 표준 라이브러리만 있는 환경에서는 건너뛴다
    graph = None


def fake_llm(*replies):
    class FakeToolModel(GenericFakeChatModel):
        def bind_tools(self, tools, **kwargs):
            return self

    return FakeToolModel(messages=iter(replies))


def tool_call(name, args):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": "call_1"}])


@unittest.skipIf(graph is None, "langgraph 미설치")
class GraphWiringTest(unittest.TestCase):
    def run_graph(self, question, *replies):
        with patch.object(graph, "get_llm", return_value=fake_llm(*replies)):
            return graph.build_graph("rule").invoke({"question": question})

    def test_tool_result_backs_the_answer(self):
        result = self.run_graph(
            "MD-1001 주문 언제 도착하나요?",
            tool_call("get_order", {"order_id": "MD-1001"}),
            AIMessage(content="현재 배송중이며 송장번호는 6012-3456-7890입니다."),
        )
        self.assertTrue(result["guard_ok"])
        self.assertFalse(result.get("escalated", False))
        self.assertIn("6012", result["answer"])

    def test_invented_number_escalates(self):
        result = self.run_graph(
            "환불은 언제 들어와요?",
            AIMessage(content="환불은 5영업일 안에 들어옵니다."),
        )
        self.assertTrue(result["escalated"])
        self.assertEqual(result["unsupported_numbers"], ["5"])
        self.assertEqual(result["answer"], graph.ESCALATE_MESSAGE)
        self.assertIn("5영업일", result["draft_answer"])

    def test_low_confidence_skips_answer(self):
        # LLM 응답을 하나도 주지 않는다. answer 노드에 가면 실패한다.
        result = self.run_graph("사장님 연락처 좀 알려주세요")
        self.assertTrue(result["escalated"])
        self.assertEqual(result["escalate_reason"], "매뉴얼 범위 밖 문의")


if __name__ == "__main__":
    unittest.main()
