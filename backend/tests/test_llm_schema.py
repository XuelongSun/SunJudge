import copy
import json
from types import SimpleNamespace

import pytest

from app.services import llm_grading
from app.services.llm_schema import ModuleGradingOutput, rubric_specs, validate_grading_output


def output():
    return {"criteria_results": [
        {"criterion_id": 2, "score": 18, "reason": "状态迁移解释较完整"},
        {"criterion_id": 1, "score": 8, "reason": "概念正确但缺少例子"},
    ], "total_score": 99, "summary": "主要概念准确，需要补充实例。"}


def specs():
    return rubric_specs([{"content": "概念", "weight": 1}, {"content": "状态迁移", "weight": 3}], 40)


def test_rubric_relative_weights_and_ai_item_ids_determine_authoritative_total():
    result = validate_grading_output(output(), specs())
    assert result["score"] == 26
    assert result["model_total_score"] == 99
    assert [item["content"] for item in result["criteria_results"]] == ["概念", "状态迁移"]
    assert [item["max_score"] for item in result["criteria_results"]] == [10, 30]
    assert result["criteria_results"][0]["reason"] == "概念正确但缺少例子"
    assert result["summary"] == output()["summary"]


def test_rubric_rounding_preserves_module_maximum_and_is_deterministic():
    criteria = [{"content": str(index), "weight": 1} for index in range(3)]
    assert [item["max_score"] for item in rubric_specs(criteria, 10)] == [3.34, 3.33, 3.33]
    assert [item["max_score"] for item in rubric_specs(criteria, 0.01)] == [0.01, 0, 0]


@pytest.mark.parametrize("change", [
    lambda data: data["criteria_results"].pop(),
    lambda data: data["criteria_results"].append(copy.deepcopy(data["criteria_results"][0])),
    lambda data: data["criteria_results"][0].update(criterion_id=3),
    lambda data: data["criteria_results"][0].update(criterion_id=True),
    lambda data: data["criteria_results"][0].update(score=31),
    lambda data: data["criteria_results"][0].update(score=-1),
    lambda data: data["criteria_results"][0].update(score=float("nan")),
    lambda data: data["criteria_results"][0].update(score=float("inf")),
    lambda data: data["criteria_results"][0].update(score="18"),
    lambda data: data["criteria_results"][0].update(score=True),
    lambda data: data["criteria_results"][0].update(reason=" "),
    lambda data: data.update(summary=""),
    lambda data: data.update(total_score=float("inf")),
    lambda data: data.update(extra="invented"),
])
def test_invalid_or_incomplete_model_scores_are_rejected(change):
    data = output()
    change(data)
    with pytest.raises(ValueError):
        validate_grading_output(data, specs())


@pytest.mark.parametrize("content", ["not JSON", "[]", "{}", "", json.dumps({"score": 40, "summary": "总分"})])
def test_bad_llm_output_degrades_to_reviewable_error_without_a_score(content, monkeypatch):
    monkeypatch.setattr(llm_grading, "_post_chat_completion", lambda *_: {"choices": [{"message": {"content": content}}]})
    assignment = SimpleNamespace(max_score=100, title="测试", code="hw1", description="说明")
    config = SimpleNamespace(model="test-model")
    report = llm_grading._call_module(config, assignment, None, "report.md", "# 正文", {
        "score_percent": 40, "criteria_items": [{"content": "内容准确", "weight": 100}],
    })
    assert report["status"] == "error"
    assert report["score"] == 0
    assert report["criteria_results"] == []
    assert report["prompt_version"] == "rubric-v2"


def test_prompt_embeds_typed_schema_rubric_caps_and_marks_truncation():
    assignment = SimpleNamespace(title="状态分析", code="hw1", description="报告要求")
    prompt = llm_grading._build_prompt(assignment, None, "report.md", "x" * 20001, {}, 40, specs())
    assert "评分上下文" in prompt
    assert '"content_truncated": true' in prompt
    assert '"max_score": 30.0' in prompt
    assert '"reason"' in prompt
    assert ModuleGradingOutput.model_json_schema()["additionalProperties"] is False
