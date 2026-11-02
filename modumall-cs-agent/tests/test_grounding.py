"""카테고리마다 서로 다른 근거만 프롬프트에 들어가는지 검사한다."""
import unittest
from unittest.mock import patch

import config
from tools import ROUTE_TOOLS, load_manual

try:
    from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
    from langchain_core.messages import AIMessage

    import graph
except ImportError:
    graph = None

# 매뉴얼마다 그 문서에만 있는 문장
SIGNATURE = {
    "delivery": "기본 배송비는 3,000원이다",
    "return": "왕복 배송비 6,000원",
    "bundle": "세트 전체로만 반품된다",
    "order": "카드 결제 취소는 3~5영업일",
}


class MappingTest(unittest.TestCase):
    def test_every_route_is_mapped(self):
        self.assertEqual(set(config.ROUTE_MANUALS), set(config.ROUTES))

    def test_each_route_gets_only_its_own_manual(self):
        for route, own in SIGNATURE.items():
            manual = load_manual(route)
            self.assertIn(own, manual, route)
            for other, sentence in SIGNATURE.items():
                if other != route:
                    self.assertNotIn(sentence, manual, f"{route} 매뉴얼에 {other} 정책이 섞임")

    def test_other_has_no_source_and_no_tools(self):
        self.assertEqual(load_manual("other"), "")
        self.assertNotIn("other", ROUTE_TOOLS)


@unittest.skipIf(graph is None, "langgraph 미설치")
class PromptTest(unittest.TestCase):
    def test_answer_prompt_contains_only_routed_manual(self):
        seen = []

        class Recorder(GenericFakeChatModel):
            def bind_tools(self, tools, **kwargs):
                return self

            def invoke(self, messages, *args, **kwargs):
                seen.append(messages[0].content)  # 시스템 프롬프트
                return super().invoke(messages, *args, **kwargs)

        llm = Recorder(messages=iter([AIMessage(content="기본 배송비는 3,000원입니다.")]))
        with patch.object(graph, "get_llm", return_value=llm):
            graph.build_graph("rule").invoke({"question": "배송비 얼마예요?"})

        prompt = seen[0]
        self.assertIn(SIGNATURE["delivery"], prompt)
        for route in ("return", "bundle", "order"):
            self.assertNotIn(SIGNATURE[route], prompt)


if __name__ == "__main__":
    unittest.main()
