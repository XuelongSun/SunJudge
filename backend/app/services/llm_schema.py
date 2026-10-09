"""Versioned AI output contract and authoritative rubric score calculation."""
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP

from pydantic import BaseModel, ConfigDict, Field

PROMPT_VERSION = "rubric-v2"
SCHEMA_VERSION = 1
CENT = Decimal("0.01")


class CriterionScore(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False, str_strip_whitespace=True)

    criterion_id: int = Field(ge=1)
    score: float = Field(ge=0)
    reason: str = Field(min_length=1)


class ModuleGradingOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False, str_strip_whitespace=True)

    criteria_results: list[CriterionScore] = Field(min_length=1)
    total_score: float = Field(ge=0)
    summary: str = Field(min_length=1)


def rubric_specs(criteria: list[object], max_score: float) -> list[dict]:
    """Normalize relative weights; distribute rounding cents so caps sum exactly."""
    maximum = Decimal(str(max_score)).quantize(CENT, rounding=ROUND_HALF_UP)
    weights = [Decimal(str(item["weight"])) for item in criteria if isinstance(item, dict)]
    if (not weights or len(weights) != len(criteria) or not maximum.is_finite() or maximum <= 0
            or any(not weight.is_finite() or weight <= 0 for weight in weights)):
        raise ValueError("Invalid rubric weights or module maximum score.")
    total_weight = sum(weights)
    exact = [maximum * weight / total_weight for weight in weights]
    caps = [value.quantize(CENT, rounding=ROUND_DOWN) for value in exact]
    remaining = int((maximum - sum(caps)) / CENT)
    order = sorted(range(len(caps)), key=lambda index: exact[index] - caps[index], reverse=True)
    for index in order[:remaining]:
        caps[index] += CENT
    return [
        {"criterion_id": index + 1, "content": str(item["content"]),
         "weight": float(weights[index]), "max_score": float(caps[index])}
        for index, item in enumerate(criteria)
    ]


def validate_grading_output(parsed: dict, specs: list[dict]) -> dict:
    output = ModuleGradingOutput.model_validate(parsed)
    by_id = {result.criterion_id: result for result in output.criteria_results}
    if len(by_id) != len(output.criteria_results) or set(by_id) != {item["criterion_id"] for item in specs}:
        raise ValueError("AI must score every rubric item exactly once.")
    results = []
    total = Decimal(0)
    for spec in specs:
        result = by_id[spec["criterion_id"]]
        score = Decimal(str(result.score))
        if score > Decimal(str(spec["max_score"])):
            raise ValueError(f"Criterion {result.criterion_id} score exceeds its maximum.")
        score = score.quantize(CENT, rounding=ROUND_HALF_UP)
        total += score
        results.append({**spec, "score": float(score), "reason": result.reason, "comment": result.reason})
    # Never trust the model's arithmetic. Keep its proposed total for diagnostics.
    return {"score": float(total), "summary": output.summary, "criteria_results": results,
            "model_total_score": output.total_score, "raw": output.model_dump()}
