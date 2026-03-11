from ..models import MessageRecord


def build_summary(
    existing_summary: str,
    health_profile: dict | None,
    recent_messages: list[MessageRecord],
    locale: str,
) -> str:
    profile = health_profile or {}
    conditions = ", ".join(profile.get("conditions", []))
    meds = ", ".join(profile.get("medications", []))
    allergies = ", ".join(profile.get("allergies", []))

    symptom_notes = [m.content for m in recent_messages if m.role == "user"][-4:]
    symptoms_text = " | ".join(symptom_notes)

    if locale.startswith("zh"):
        chunks = [
            f"既往摘要: {existing_summary}" if existing_summary else "",
            f"慢病史: {conditions}" if conditions else "",
            f"当前用药: {meds}" if meds else "",
            f"过敏史: {allergies}" if allergies else "",
            f"近期症状: {symptoms_text}" if symptoms_text else "",
        ]
    else:
        chunks = [
            f"Previous summary: {existing_summary}" if existing_summary else "",
            f"Conditions: {conditions}" if conditions else "",
            f"Medications: {meds}" if meds else "",
            f"Allergies: {allergies}" if allergies else "",
            f"Recent symptoms: {symptoms_text}" if symptoms_text else "",
        ]

    merged = "\n".join(part for part in chunks if part).strip()
    return merged[:1200]
