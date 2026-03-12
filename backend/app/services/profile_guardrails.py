from __future__ import annotations

import re
from datetime import UTC, datetime


SexValue = str
AgeGroup = str


def normalize_sex(value: str | None) -> SexValue:
    raw = str(value or "").strip().lower()
    if raw in {"男", "male", "man", "m"}:
        return "male"
    if raw in {"女", "female", "woman", "f"}:
        return "female"
    return ""


def sex_guardrails(value: str | None, locale: str) -> list[str]:
    normalized = normalize_sex(value)
    if normalized == "male":
        return (
            [
                "该用户为男性，禁止主动追问月经、末次月经、妊娠、妇科检查等女性特异问题。",
                "禁止给出妇科或妊娠相关建议，除非用户自己明确提出相关跨性别/激素治疗背景。",
            ]
            if locale.startswith("zh")
            else [
                "This user is male. Do not ask about menstruation, last menstrual period, pregnancy, or gynecologic testing.",
                "Do not give gynecology or pregnancy-specific advice unless the user explicitly provides relevant transgender or hormone-treatment context.",
            ]
        )
    if normalized == "female":
        return (
            [
                "该用户为女性，禁止主动追问前列腺、睾丸等男性特异器官问题。",
                "禁止给出男性专科器官相关建议，除非用户自己明确提出相关特殊背景。",
            ]
            if locale.startswith("zh")
            else [
                "This user is female. Do not ask about prostate, testes, or other male-specific organ issues.",
                "Do not give male-specific specialty advice unless the user explicitly provides special context.",
            ]
        )
    return []


def normalize_region_code(value: str | None) -> str:
    return str(value or "").strip().upper()


def extract_birth_year(value: str | None) -> int | None:
    text = str(value or "").strip()
    match = re.search(r"(19\d{2}|20\d{2})", text)
    if not match:
        return None
    year = int(match.group(1))
    current_year = datetime.now(UTC).year
    if year < 1900 or year > current_year:
        return None
    return year


def derive_age_group(value: str | None) -> AgeGroup:
    birth_year = extract_birth_year(value)
    if birth_year is None:
        return ""
    age = datetime.now(UTC).year - birth_year
    if age < 13:
        return "child"
    if age < 18:
        return "adolescent"
    if age >= 65:
        return "older_adult"
    return "adult"


def age_guardrails(value: str | None, locale: str) -> list[str]:
    age_group = derive_age_group(value)
    if age_group in {"child", "adolescent"}:
        return (
            [
                "该用户未成年，追问和建议要更谨慎，优先强调监护人参与和线下儿科/全科评估。",
                "避免默认按成年人自我处理路径给出长时间观察或运动建议。",
            ]
            if locale.startswith("zh")
            else [
                "This user is a minor. Keep follow-up and guidance more cautious, and emphasize caregiver involvement and pediatric or primary-care evaluation.",
                "Do not default to adult-style self-management plans or exercise advice.",
            ]
        )
    if age_group == "older_adult":
        return (
            [
                "该用户为老年人，面对发热、胸闷、意识改变、脱水等情况要提高警惕，建议更低阈值线下评估。",
            ]
            if locale.startswith("zh")
            else [
                "This user is an older adult. Use a lower threshold for in-person evaluation when fever, chest symptoms, confusion, or dehydration are present.",
            ]
        )
    return []


def region_guardrails(value: str | None, locale: str) -> list[str]:
    region = normalize_region_code(value)
    phone_map = {
        "US": "911",
        "CA": "911",
        "UK": "999",
        "HK": "999",
        "CN": "120",
        "JP": "119",
        "SG": "995",
        "AU": "000",
    }
    phone = phone_map.get(region)
    if not region:
        return []
    if locale.startswith("zh"):
        items = [f"当前地区代码为 {region}，急症文案与急救号码必须使用该地区上下文。"]
        if phone:
            items.append(f"若出现急症，应使用当地急救电话 {phone}。")
        return items
    items = [f"The current region code is {region}. Emergency wording and emergency contact references must stay aligned to that region."]
    if phone:
        items.append(f"If emergency care is needed, use the local emergency number {phone}.")
    return items


def sex_mismatch_terms(value: str | None) -> list[str]:
    normalized = normalize_sex(value)
    if normalized == "male":
        return ["月经", "经期", "末次月经", "怀孕", "妊娠", "妇科", "menstru", "period", "pregnan", "gyne"]
    if normalized == "female":
        return ["前列腺", "睾丸", "阴囊", "prostate", "testicle", "testes", "scrot"]
    return []


def has_sex_mismatch(text: str, value: str | None) -> bool:
    if not text:
        return False
    lowered = text.lower()
    return any(term in text or term in lowered for term in sex_mismatch_terms(value))


def profile_guardrails_payload(
    *,
    sex: str | None,
    birth_year: str | None,
    region_code: str | None,
    locale: str,
) -> dict[str, object]:
    return {
        "sex_normalized": normalize_sex(sex),
        "sex_specific_guardrails": sex_guardrails(sex, locale),
        "age_group": derive_age_group(birth_year),
        "age_specific_guardrails": age_guardrails(birth_year, locale),
        "region_normalized": normalize_region_code(region_code),
        "region_specific_guardrails": region_guardrails(region_code, locale),
    }
