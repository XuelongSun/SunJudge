"""Submission-item weights are authoritative; legacy records remain readable."""
import math


def effective_requirements(requirements, program=(), ai=()):
    items = [dict(item) for item in requirements]
    evaluated = {}
    for module in list(program) + list(ai):
        key = str(module.get("input_file_key") or "main")
        evaluated[key] = evaluated.get(key, 0) + float(module.get("score_percent") or 0)
    manual = [item for item in items if item.get("required", True) and item["key"] not in evaluated]
    remaining = max(0, 100 - sum(evaluated.get(item["key"], 0) for item in items if item.get("required", True)))
    for item in items:
        item["weight_percent"] = (float(item.get("weight_percent", evaluated.get(item["key"], remaining / len(manual) if manual else 0)))
                                  if item.get("required", True) else 0)
    return items


def validate_weights(requirements, program, ai):
    explicit = any("weight_percent" in item for item in requirements)
    if not explicit:
        return  # Old API/records use the former allocation until edited with explicit weights.
    required = [item for item in requirements if item.get("required", True)]
    if not required or any("weight_percent" not in item for item in required):
        raise ValueError("请为每个必交项设置权重。")
    if abs(sum(item["weight_percent"] for item in required) - 100) > 0.01:
        raise ValueError("必交项权重合计必须为100%。")
    modules = list(program) + list(ai)
    for item in requirements:
        matched = [module for module in modules if module["input_file_key"] == item["key"]]
        if matched and (not item.get("required", True) or abs(sum(float(module["score_percent"]) for module in matched) - item["weight_percent"]) > 0.01):
            raise ValueError(f"提交项 {item['label']} 的评测占比合计必须与提交项权重一致；非必交项不能配置计分评测。")


def validate_review_weights(assignment, reviews):
    requirements = assignment.submission_requirements_json or []
    by_key = {item["key"]: item for item in effective_requirements(requirements or assignment.to_dict()["submission_requirements"], assignment.program_evaluations_json or [], assignment.ai_evaluations_json or [])}
    explicit = any("weight_percent" in item for item in requirements)
    if not reviews:
        if explicit:
            raise ValueError("请按必交文件完成评分，不能直接指定总分。")
        return reviews
    seen = set()
    for review in reviews:
        key = review["submission_item_key"]
        if key not in by_key or key in seen:
            raise ValueError("批改文件必须对应唯一的提交项。")
        seen.add(key)
        item = by_key[key]
        if not item.get("required", True):
            review.update(score=0, weight_percent=0, max_score=0)
        elif explicit:
            cap = round(assignment.max_score * item["weight_percent"] / 100, 2)
            if not math.isfinite(review["score"]) or not 0 <= review["score"] <= cap:
                raise ValueError(f"{item['label']} 的评分必须在0到{cap}之间。")
            review.update(weight_percent=item["weight_percent"], max_score=cap)
    if explicit and not {item["key"] for item in requirements if item.get("required", True)}.issubset(seen):
        raise ValueError("必须完成所有必交文件的评分。")
    return reviews
