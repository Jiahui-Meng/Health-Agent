import re
from dataclasses import dataclass


RISK_SCORE = {"low": 1, "medium": 2, "high": 3, "emergency": 4}


EMERGENCY_KEYWORDS_ZH = {
    "胸痛",
    "呼吸困难",
    "昏迷",
    "意识不清",
    "抽搐",
    "中风",
    "大出血",
    "自杀",
    "自伤",
}
EMERGENCY_KEYWORDS_EN = {
    "chest pain",
    "shortness of breath",
    "unconscious",
    "seizure",
    "stroke",
    "heavy bleeding",
    "suicide",
    "self harm",
}

HIGH_KEYWORDS_ZH = {"高烧", "剧烈头痛", "持续呕吐", "血便", "黑便", "严重脱水"}
HIGH_KEYWORDS_EN = {"high fever", "severe headache", "persistent vomiting", "blood in stool", "black stool"}

DIAGNOSIS_PATTERNS = [
    re.compile(r"\bdiagnosed?\b", re.IGNORECASE),
    re.compile(r"\byou have\b", re.IGNORECASE),
    re.compile(r"\bdefinitely\b", re.IGNORECASE),
    re.compile(r"\b确诊\b"),
    re.compile(r"\b你得了\b"),
]

PRESCRIPTION_PATTERNS = [
    re.compile(r"\b\d+\s?mg\b", re.IGNORECASE),
    re.compile(r"\btake\s+\d+", re.IGNORECASE),
    re.compile(r"\b处方\b"),
    re.compile(r"\b服用\s*\d+"),
]


@dataclass
class RiskResult:
    risk_level: str
    triggers: list[str]


def classify_risk(text: str) -> RiskResult:
    normalized = text.lower().strip()
    triggers: list[str] = []

    for keyword in EMERGENCY_KEYWORDS_ZH:
        if keyword in text:
            triggers.append(keyword)
    for keyword in EMERGENCY_KEYWORDS_EN:
        if keyword in normalized:
            triggers.append(keyword)
    if triggers:
        return RiskResult("emergency", triggers)

    for keyword in HIGH_KEYWORDS_ZH:
        if keyword in text:
            triggers.append(keyword)
    for keyword in HIGH_KEYWORDS_EN:
        if keyword in normalized:
            triggers.append(keyword)
    if triggers:
        return RiskResult("high", triggers)

    if any(token in normalized for token in ["pain", "fever", "headache", "cough", "dizzy"]):
        return RiskResult("medium", [])

    return RiskResult("low", [])


def emergency_phone(region_code: str) -> str:
    mapping = {
        "US": "911",
        "CA": "911",
        "UK": "999",
        "HK": "999",
        "CN": "120",
        "JP": "119",
        "SG": "995",
        "AU": "000",
    }
    return mapping.get(region_code.upper(), "当地急救电话")


def build_emergency_guidance(locale: str, region_code: str, triggers: list[str]) -> str:
    phone = emergency_phone(region_code)
    trigger_text = ", ".join(triggers) if triggers else "high-risk symptoms"
    if locale.startswith("zh"):
        return (
            f"检测到高危信号（{trigger_text}）。请立即停止线上咨询并拨打 {phone} 或前往最近急诊。"
            "若有意识障碍、持续胸痛、呼吸困难或大量出血，请立即求助身边人员。"
        )
    return (
        f"High-risk signals detected ({trigger_text}). Stop online consultation and call {phone} now or go to the nearest ER. "
        "If there is chest pain, breathing difficulty, altered consciousness, or heavy bleeding, seek immediate in-person help."
    )


def enforce_no_diagnosis_or_prescription(answer: dict, locale: str) -> dict:
    summary = answer.get("summary", "")
    next_steps = answer.get("next_steps", [])
    unsafe = any(p.search(summary) for p in DIAGNOSIS_PATTERNS + PRESCRIPTION_PATTERNS)
    unsafe = unsafe or any(
        any(p.search(step) for p in DIAGNOSIS_PATTERNS + PRESCRIPTION_PATTERNS)
        for step in next_steps
    )

    if not unsafe:
        return answer

    if locale.startswith("zh"):
        safe_summary = "基于线上信息无法进行医疗诊断或处方。当前建议以风险监测和线下就医评估为主。"
        safe_steps = [
            "继续观察症状变化，记录体温/疼痛程度/持续时间。",
            "如症状加重或出现胸痛、呼吸困难、意识改变，立即急诊就医。",
            "尽快线下就诊，由医生完成查体和必要检查。",
        ]
    else:
        safe_summary = "A definitive diagnosis or prescription cannot be provided online from limited information."
        safe_steps = [
            "Monitor symptom progression and keep a short log of timing and severity.",
            "Seek urgent care immediately if chest pain, breathing trouble, or confusion appears.",
            "Arrange an in-person clinical evaluation as soon as possible.",
        ]

    answer["summary"] = safe_summary
    answer["next_steps"] = safe_steps
    if RISK_SCORE.get(answer.get("risk_level", "low"), 1) < RISK_SCORE["medium"]:
        answer["risk_level"] = "medium"
    return answer


def enforce_intake_questioning(answer: dict, locale: str) -> dict:
    if answer.get("stage") != "intake":
        return answer

    summary = str(answer.get("summary") or "")
    follow_ups = [str(item).strip() for item in (answer.get("follow_up_questions") or []) if str(item).strip()]
    unsafe_summary = any(p.search(summary) for p in DIAGNOSIS_PATTERNS + PRESCRIPTION_PATTERNS)
    unsafe_summary = unsafe_summary or any(
        token in summary.lower()
        for token in ["low risk", "medium risk", "high risk", "emergency", "初步判断", "中风险", "高风险", "低风险"]
    )

    if not unsafe_summary and follow_ups:
        answer["next_steps"] = []
        return answer

    if locale.startswith("zh"):
        answer["summary"] = "我先把情况问清楚一点，这样后面的判断会更稳妥。"
        answer["follow_up_questions"] = follow_ups[:2] or [
            "这些症状是突然出现的，还是慢慢加重的？",
            "现在最明显的不舒服是什么，严重程度大概几分？",
        ]
    else:
        answer["summary"] = "I want to clarify a few details first so the next step is safer and more accurate."
        answer["follow_up_questions"] = follow_ups[:2] or [
            "Did these symptoms come on suddenly, or have they been getting worse gradually?",
            "What is the main symptom right now, and how severe is it?",
        ]
    answer["next_steps"] = []
    return answer


def max_risk(r1: str, r2: str) -> str:
    return r1 if RISK_SCORE.get(r1, 0) >= RISK_SCORE.get(r2, 0) else r2
