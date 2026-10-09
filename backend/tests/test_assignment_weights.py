from types import SimpleNamespace

import pytest

from app.services.assignment_weights import effective_requirements, validate_weights, validate_review_weights
from app.services.file_validation import normalize_submission_requirements


def requirements():
    return [{"key": "code", "label": "程序", "required": True, "weight_percent": 60},
            {"key": "report", "label": "报告", "required": True, "weight_percent": 40},
            {"key": "extra", "label": "附件", "required": False, "weight_percent": 0}]


def test_required_weights_match_combined_modules_and_optional_has_no_points():
    validate_weights(requirements(), [{"input_file_key": "code", "score_percent": 60}], [{"input_file_key": "report", "score_percent": 40}])
    legacy = [{"key": "code", "required": True}, {"key": "report", "required": True}, {"key": "extra", "required": False}]
    assert [item["weight_percent"] for item in effective_requirements(legacy, [{"input_file_key": "code", "score_percent": 60}])] == [60, 40, 0]


@pytest.mark.parametrize("module", [
    {"input_file_key": "code", "score_percent": 50},
    {"input_file_key": "report", "score_percent": 60},
    {"input_file_key": "extra", "score_percent": 10},
])
def test_module_scores_cannot_differ_from_submission_item_weight(module):
    with pytest.raises(ValueError):
        validate_weights(requirements(), [], [module])


@pytest.mark.parametrize("value", [-1, 101, float("nan"), float("inf"), "bad"])
def test_submission_weights_reject_invalid_numbers(value):
    with pytest.raises(ValueError):
        normalize_submission_requirements([{"key": "a", "required": True, "weight_percent": value}], "homework")


def test_required_sum_and_optional_weight_validation():
    items = requirements()
    items[0]["weight_percent"] = 59
    with pytest.raises(ValueError):
        validate_weights(items, [], [])
    with pytest.raises(ValueError):
        normalize_submission_requirements([{"key": "a", "required": False, "weight_percent": 1}], "homework")


def test_review_uses_server_caps_and_excludes_optional_points():
    assignment = SimpleNamespace(max_score=200, submission_requirements_json=requirements(), program_evaluations_json=[], ai_evaluations_json=[])
    reviews = [{"submission_item_key": key, "score": score, "weight_percent": 999, "max_score": 999}
               for key, score in [("code", 100), ("report", 70), ("extra", 50)]]
    result = validate_review_weights(assignment, reviews)
    assert [(item["score"], item["max_score"]) for item in result] == [(100, 120), (70, 80), (0, 0)]
    assert sum(item["score"] for item in result) == 170
    with pytest.raises(ValueError):
        validate_review_weights(assignment, [{"submission_item_key": "code", "score": 121}])
    with pytest.raises(ValueError):
        validate_review_weights(assignment, [{"submission_item_key": "code", "score": 100}])
    with pytest.raises(ValueError):
        validate_review_weights(assignment, [])
