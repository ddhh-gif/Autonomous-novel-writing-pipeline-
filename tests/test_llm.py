import json
import pytest
from unittest.mock import MagicMock, patch
from novel_pipeline.llm import LLMClient, LLMParseError
from novel_pipeline.config import LLMConfig
from novel_pipeline.models import StateChangeProposal


@pytest.fixture
def cfg():
    return LLMConfig(model="claude-sonnet-4-6", max_retries=2)


def _make_response(content: str):
    msg = MagicMock()
    msg.content = [MagicMock(text=content)]
    return msg


def test_call_prose_returns_text(cfg):
    with patch("anthropic.Anthropic") as MockAnth:
        instance = MockAnth.return_value
        instance.messages.create.return_value = _make_response("好的故事")
        client = LLMClient(cfg)
        result = client.call_prose(system="你是作家", prompt="写一句话")
        assert result == "好的故事"


def test_call_structured_parses_json(cfg):
    payload = {"changes": []}
    with patch("anthropic.Anthropic") as MockAnth:
        instance = MockAnth.return_value
        instance.messages.create.return_value = _make_response(json.dumps(payload))
        client = LLMClient(cfg)
        result = client.call_structured(
            system="返回JSON", prompt="提取变化", response_model=StateChangeProposal
        )
        assert isinstance(result, StateChangeProposal)
        assert result.changes == []


def test_call_structured_strips_markdown_fences(cfg):
    payload = {"changes": []}
    raw = f"```json\n{json.dumps(payload)}\n```"
    with patch("anthropic.Anthropic") as MockAnth:
        instance = MockAnth.return_value
        instance.messages.create.return_value = _make_response(raw)
        client = LLMClient(cfg)
        result = client.call_structured(
            system="返回JSON", prompt="x", response_model=StateChangeProposal
        )
        assert isinstance(result, StateChangeProposal)


def test_call_structured_retries_on_bad_json(cfg):
    good = json.dumps({"changes": []})
    responses = [_make_response("not json"), _make_response(good)]
    with patch("anthropic.Anthropic") as MockAnth:
        instance = MockAnth.return_value
        instance.messages.create.side_effect = responses
        client = LLMClient(cfg)
        result = client.call_structured(
            system="s", prompt="p", response_model=StateChangeProposal
        )
        assert isinstance(result, StateChangeProposal)
        assert instance.messages.create.call_count == 2


def test_call_structured_raises_after_max_retries(cfg):
    with patch("anthropic.Anthropic") as MockAnth:
        instance = MockAnth.return_value
        instance.messages.create.return_value = _make_response("bad json always")
        client = LLMClient(cfg)
        with pytest.raises(LLMParseError):
            client.call_structured(system="s", prompt="p", response_model=StateChangeProposal)
