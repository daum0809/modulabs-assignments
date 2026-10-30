"""LLM 생성 지점. 모델 교체는 MODUMALL_MODEL 환경변수로 한다."""
from functools import lru_cache

from langchain.chat_models import init_chat_model

import config


@lru_cache
def get_llm():
    # 최신 Claude 모델은 temperature 지정을 거부하므로 기본값을 쓴다
    return init_chat_model(config.MODEL)
