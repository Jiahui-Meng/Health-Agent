import json


def parse_model_json(raw: str, locale: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:].strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = {
            "summary": text[:300],
            "risk_level": "medium",
            "next_steps": [],
            "emergency_guidance": None,
            "disclaimer": "",
            "stage": "conclusion",
            "follow_up_questions": [],
        }

    stage = str(data.get("stage", "conclusion")).lower()
    if stage not in {"intake", "conclusion"}:
        stage = "conclusion"

    next_steps = data.get("next_steps")
    if not isinstance(next_steps, list):
        next_steps = []
    if stage == "conclusion" and not next_steps:
        if locale.startswith("zh"):
            next_steps = [
                "继续观察症状变化并记录关键指标。",
                "如出现加重或危险信号，立即线下就医。",
            ]
        else:
            next_steps = [
                "Monitor symptoms and record key changes.",
                "Seek in-person care promptly if symptoms worsen.",
            ]

    follow_up_questions = data.get("follow_up_questions")
    if not isinstance(follow_up_questions, list):
        follow_up_questions = []
    follow_up_questions = [str(x).strip() for x in follow_up_questions if str(x).strip()][:3]
    if stage == "intake" and not follow_up_questions:
        if locale.startswith("zh"):
            follow_up_questions = [
                "这些症状是从什么时候开始的？",
                "目前最不舒服的症状是什么，严重程度大约几分（0-10）？",
            ]
        else:
            follow_up_questions = [
                "When did these symptoms start?",
                "Which symptom is most severe now, and how severe is it on a 0-10 scale?",
            ]

    risk_level = str(data.get("risk_level", "medium")).lower()
    if risk_level not in {"low", "medium", "high", "emergency"}:
        risk_level = "medium"

    disclaimer = data.get("disclaimer")
    if not disclaimer:
        disclaimer = (
            "本回答仅用于健康信息参考，不能替代医生诊疗。"
            if locale.startswith("zh")
            else "Informational only; not a replacement for professional medical care."
        )
    summary = str(data.get("summary") or "").strip()
    if not summary:
        summary = "先补充关键信息以便分诊判断。" if locale.startswith("zh") else "Let's gather key details first for safe triage."

    return {
        "summary": summary,
        "risk_level": risk_level,
        "next_steps": [str(x) for x in next_steps][:5],
        "emergency_guidance": data.get("emergency_guidance"),
        "disclaimer": str(disclaimer),
        "stage": stage,
        "follow_up_questions": follow_up_questions if stage == "intake" else None,
    }
