"""Deterministic budget allocation; these are planning limits, not live prices."""


def allocate_budget(total_inr: int) -> dict:
    if total_inr <= 0:
        raise ValueError("Budget must be greater than zero.")
    transport = total_inr * 25 // 100
    accommodation = total_inr * 35 // 100
    food = total_inr * 25 // 100
    activities = total_inr - transport - accommodation - food
    return {
        "transport": transport,
        "accommodation": accommodation,
        "food": food,
        "activities": activities,
        "total": transport + accommodation + food + activities,
        "note": (
            "Planning allocations derived from your total budget (25% transport, 35% accommodation, "
            "25% food, remainder activities); these are not current quotes or verified prices."
        ),
    }
