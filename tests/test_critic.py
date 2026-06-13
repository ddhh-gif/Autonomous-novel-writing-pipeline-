import pytest
from unittest.mock import MagicMock
from novel_pipeline.critic import Critic, Reviser
from novel_pipeline.models import CriticReport, CriticIssue


def test_critic_returns_report_on_clean_prose():
    llm = MagicMock()
    llm.call_structured.return_value = CriticReport(issues=[], passed=True)
    critic = Critic(llm=llm)
    report = critic.check(prose="张三勇敢地走入了森林。", state_snapshot={"character_states": {}})
    assert report.passed is True
    assert report.issues == []


def test_critic_returns_rollback_issue_on_dead_character():
    llm = MagicMock()
    llm.call_structured.return_value = CriticReport(
        issues=[CriticIssue(severity="rollback", description="已死角色张三登场", location="张三走入")],
        passed=False,
    )
    critic = Critic(llm=llm)
    report = critic.check(
        prose="张三走入了大厅。",
        state_snapshot={"character_states": {"c1": {"location": "x", "status": "dead", "emotional_state": "x", "knowledge": []}}},
    )
    assert any(i.severity == "rollback" for i in report.issues)


def test_reviser_returns_revised_prose():
    llm = MagicMock()
    llm.call_prose.return_value = "李四走入了大厅。"
    reviser = Reviser(llm=llm)
    issue = CriticIssue(severity="revise", description="用李四替换张三", location="张三走入")
    result = reviser.revise(prose="张三走入了大厅。", issue=issue)
    assert result == "李四走入了大厅。"
