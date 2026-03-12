from __future__ import annotations

import re

from .profile_guardrails import derive_age_group, has_sex_mismatch, normalize_region_code, normalize_sex


SECTION_ORDER = [
    "visit_guidance",
    "medication_guidance",
    "rest_guidance",
    "diet_guidance",
    "exercise_guidance",
    "monitoring_guidance",
]

PRIMARY_RISK_LEVELS = {"high", "emergency"}
EMERGENCY_PHONE_MAP = {
    "US": "911",
    "CA": "911",
    "UK": "999",
    "HK": "999",
    "CN": "120",
    "JP": "119",
    "SG": "995",
    "AU": "000",
}


def build_advice_sections(
    *,
    locale: str,
    message: str,
    answer: dict,
    health_profile: dict | None,
    region_code: str | None = None,
) -> dict | None:
    if answer.get("stage") != "conclusion":
        return None

    text_blob = " ".join(
        [
            message or "",
            str(answer.get("summary") or ""),
            " ".join(str(item) for item in (answer.get("next_steps") or [])),
        ]
    ).lower()
    risk_level = str(answer.get("risk_level") or "medium")
    profile = health_profile or {}
    sex = normalize_sex(profile.get("sex"))
    age_group = derive_age_group(profile.get("age_range"))
    normalized_region = normalize_region_code(region_code)
    advice: dict[str, dict] = {}

    flags = _detect_flags(text_blob)
    force_in_person = risk_level in PRIMARY_RISK_LEVELS or _contains_any(
        text_blob,
        [
            "线下就医",
            "门诊",
            "急诊",
            "in-person",
            "urgent care",
            "er",
            "emergency room",
            "clinical evaluation",
        ],
    )

    visit_section = _build_visit_guidance(
        locale,
        flags,
        risk_level,
        force_in_person,
        profile,
        age_group=age_group,
        region_code=normalized_region,
    )
    if visit_section:
        advice["visit_guidance"] = visit_section

    medication_section = _build_medication_guidance(
        locale,
        flags,
        risk_level,
        force_in_person,
        profile,
        age_group=age_group,
    )
    if medication_section:
        advice["medication_guidance"] = medication_section

    rest_section = _build_rest_guidance(locale, flags, risk_level, age_group=age_group)
    if rest_section:
        advice["rest_guidance"] = rest_section

    diet_section = _build_diet_guidance(locale, flags)
    if diet_section:
        advice["diet_guidance"] = diet_section

    exercise_section = _build_exercise_guidance(locale, flags, risk_level, age_group=age_group)
    if exercise_section:
        advice["exercise_guidance"] = exercise_section

    monitoring_section = _build_monitoring_guidance(
        locale,
        flags,
        risk_level,
        age_group=age_group,
    )
    if monitoring_section:
        advice["monitoring_guidance"] = monitoring_section

    advice = _sanitize_advice_sections(advice, locale=locale, risk_level=risk_level, sex=sex)
    return advice or None


def advice_sections_to_next_steps(advice_sections: dict | None, fallback_steps: list[str], limit: int = 5) -> list[str]:
    if not advice_sections:
        return [str(item) for item in fallback_steps][:limit]

    steps: list[str] = []
    for priority in ("primary", "secondary"):
        for section_name in SECTION_ORDER:
            section = advice_sections.get(section_name)
            if not isinstance(section, dict) or section.get("priority") != priority:
                continue
            for item in section.get("items") or []:
                text = str(item).strip()
                if text and text not in steps:
                    steps.append(text)
                if len(steps) >= limit:
                    return steps[:limit]
    return steps[:limit] or [str(item) for item in fallback_steps][:limit]


def _build_visit_guidance(
    locale: str,
    flags: dict[str, bool],
    risk_level: str,
    force_in_person: bool,
    profile: dict,
    *,
    age_group: str,
    region_code: str,
) -> dict | None:
    needs_visit = force_in_person or risk_level in {"medium", "high", "emergency"} or flags["worsening"]
    department = _recommend_department(locale, flags, age_group=age_group)
    emergency_phone = EMERGENCY_PHONE_MAP.get(region_code, "")
    if locale.startswith("zh"):
        if not needs_visit:
            items = [
                "目前没有明确必须马上去医院的信号，可先在家观察、休息并按监测建议记录变化。",
                "如果症状持续不缓解、再次明显加重，或出现胸痛、气促、持续高热、剧烈腹痛、意识异常等情况，再尽快改为线下就医。",
            ]
        elif risk_level == "emergency":
            items = [
                f"请立即前往急诊；如无法自行前往，马上呼叫当地急救服务。",
                "不要继续等待症状自行缓解，也不要自行开车前往医院。",
            ]
            if emergency_phone:
                items.insert(1, f"请直接使用当地急救电话 {emergency_phone} 寻求帮助。")
        elif risk_level == "high":
            items = [
                f"建议当天尽快到{department}或急诊就诊，完成查体和必要检查。",
                "就诊时带上症状开始时间、变化过程，以及既往病史和用药信息。",
            ]
        else:
            items = [
                f"如果症状持续不缓解、反复出现或明显加重，建议预约{department}就诊。",
                "若出现高热不退、明显气促、持续呕吐、严重腹痛或意识异常，请改为急诊处理。",
            ]
        if age_group in {"child", "adolescent"}:
            items.append("未成年人建议由监护人陪同就诊，优先选择儿科或全科进行线下评估。")
        elif age_group == "older_adult":
            items.append("老年人一旦出现反应变慢、脱水、行走不稳或食欲明显下降，建议提前线下评估，不要长时间在家观察。")
        title = "挂号 / 就医建议"
    else:
        if not needs_visit:
            items = [
                "There is no clear sign right now that you must go to the hospital immediately; home observation and monitoring are reasonable first steps.",
                "Switch to in-person care promptly if symptoms persist, clearly worsen, or new red flags such as chest pain, breathing difficulty, sustained fever, severe abdominal pain, or confusion appear.",
            ]
        elif risk_level == "emergency":
            items = [
                "Go to the emergency department now. If needed, call local emergency services immediately.",
                "Do not keep waiting for symptoms to settle on their own, and do not drive yourself if you feel unsafe.",
            ]
            if emergency_phone:
                items.insert(1, f"Use the local emergency number {emergency_phone} right away.")
        elif risk_level == "high":
            items = [
                f"Arrange same-day evaluation in {department} or urgent/emergency care for examination and testing.",
                "Bring a short symptom timeline plus your medical history and current medications.",
            ]
        else:
            items = [
                f"If symptoms persist, recur, or clearly worsen, book an appointment with {department}.",
                "Switch to urgent care immediately if high fever, breathing difficulty, persistent vomiting, severe abdominal pain, or confusion develops.",
            ]
        if age_group in {"child", "adolescent"}:
            items.append("A caregiver should stay involved, and pediatric or primary-care review is preferred.")
        elif age_group == "older_adult":
            items.append("Use a lower threshold for in-person review if there is slowing down, dehydration, poor intake, or mobility decline.")
        title = "Visit Guidance"
    return {
        "title": title,
        "items": items,
        "priority": "primary" if risk_level in PRIMARY_RISK_LEVELS else "secondary",
    }


def _build_medication_guidance(
    locale: str,
    flags: dict[str, bool],
    risk_level: str,
    force_in_person: bool,
    profile: dict,
    *,
    age_group: str,
) -> dict | None:
    allergies = profile.get("allergies") or []
    has_history = bool(profile.get("conditions") or profile.get("medications") or allergies)
    items: list[str] = []

    if risk_level in PRIMARY_RISK_LEVELS or flags["chest_pain"] or flags["short_breath"]:
        if locale.startswith("zh"):
            items = [
                "当前不建议自行加用药物掩盖症状，先按就医建议尽快线下评估。",
            ]
            title = "用药建议"
        else:
            items = [
                "Do not add self-directed medication just to mask symptoms right now; follow the visit guidance and get in-person assessment first.",
            ]
            title = "Medication Guidance"
        return {"title": title, "items": items, "priority": "secondary"}

    if not any([flags["fever"], flags["pain"], flags["cough"], flags["sore_throat"], flags["gastro"]]):
        if locale.startswith("zh"):
            items = [
                "目前不一定需要吃药，可先以休息、补水和观察为主。",
            ]
            title = "用药建议"
        else:
            items = [
                "Medication may not be necessary right now; rest, hydration, and observation are reasonable first steps.",
            ]
            title = "Medication Guidance"
        return {"title": title, "items": items, "priority": "secondary"}

    if locale.startswith("zh"):
        if flags["fever"] or flags["pain"] or flags["sore_throat"]:
            items.append("如果你平时可安全使用非处方药，可只选一种常见退烧止痛药，例如对乙酰氨基酚或布洛芬，并严格按说明书使用，不要叠加同类成分。")
        if flags["cough"] or flags["sore_throat"]:
            items.append("咽痛或咳嗽明显时，可先考虑润喉含片；如果主要是干咳，可向药师咨询右美沙芬类非处方止咳药是否合适。")
        if flags["gastro"]:
            items.append("腹泻或呕吐时，可优先考虑口服补液盐，重点先纠正脱水风险；一般不建议先自行叠加止泻药。")
        if has_history:
            items.append("如你本身有慢病、长期用药或药物过敏史，购买或服用任何非处方药前先咨询药师或医生。")
        if age_group in {"child", "adolescent"}:
            items.append("未成年人使用任何非处方药前，建议先由监护人核对标签，必要时咨询药师或医生。")
        if force_in_person or risk_level == "medium":
            items.append("如果症状持续不缓解或越来越重，需要线下就诊，由医生判断是否需要处方治疗。")
        title = "用药建议"
    else:
        if flags["fever"] or flags["pain"] or flags["sore_throat"]:
            items.append("If OTC medication is usually safe for you, choose only one common fever or pain reliever such as acetaminophen or ibuprofen, and follow the label closely without doubling similar ingredients.")
        if flags["cough"] or flags["sore_throat"]:
            items.append("For cough or sore throat, start with lozenges; if the main issue is dry cough, ask a pharmacist whether an OTC dextromethorphan product is appropriate.")
        if flags["gastro"]:
            items.append("With vomiting or diarrhea, focus first on oral rehydration salts or electrolyte replacement rather than layering extra symptom-suppression medicines.")
        if has_history:
            items.append("If you have chronic conditions, regular medications, or drug allergies, check with a pharmacist or clinician before taking any OTC medication.")
        if age_group in {"child", "adolescent"}:
            items.append("For minors, a caregiver should review OTC labels first and pharmacist or clinician advice is preferred before use.")
        if force_in_person or risk_level == "medium":
            items.append("If symptoms are not settling or keep worsening, seek in-person care to decide whether prescription treatment is needed.")
        title = "Medication Guidance"

    items = _dedupe(items)
    return {"title": title, "items": items[:4], "priority": "secondary"}


def _build_rest_guidance(locale: str, flags: dict[str, bool], risk_level: str, *, age_group: str) -> dict | None:
    if not any([flags["fever"], flags["cough"], flags["sore_throat"], flags["fatigue"], flags["headache"], flags["gastro"]]):
        return None
    if locale.startswith("zh"):
        items = [
            "这几天尽量保证睡眠，先把高强度工作、熬夜和饮酒暂停下来。",
            "若有发热、乏力或明显不适，优先在家休息，避免带病运动或长时间外出。",
        ]
        if age_group in {"child", "adolescent"}:
            items.append("如为学生儿童，建议暂时减少上学、补习或体育活动负荷，优先恢复休息。")
        title = "作息调整"
    else:
        items = [
            "Prioritize sleep for the next few days and pause late nights, heavy workload, and alcohol.",
            "If fever, fatigue, or obvious discomfort is present, favor home rest instead of pushing through normal activity.",
        ]
        if age_group in {"child", "adolescent"}:
            items.append("For a child or teenager, reduce school and sports load for now and prioritize recovery time.")
        title = "Rest Guidance"
    return {"title": title, "items": items, "priority": "primary" if risk_level in {"medium", "high"} else "secondary"}


def _build_diet_guidance(locale: str, flags: dict[str, bool]) -> dict | None:
    if not any([flags["gastro"], flags["fever"], flags["sore_throat"]]):
        return None
    if locale.startswith("zh"):
        if flags["gastro"]:
            items = [
                "饮食先以清淡、少量多次为主，优先米粥、面、汤、水果泥等容易消化的食物。",
                "先避免油腻、辛辣、生冷、酒精和高糖饮料，防止肠胃刺激加重。",
            ]
        else:
            items = [
                "发热或咽痛时多补充温水、清汤或电解质饮品，避免太烫、太辣和过于刺激的食物。",
                "如果食欲差，先选择软食和容易吞咽的食物，保证基本补水即可。",
            ]
        title = "饮食建议"
    else:
        if flags["gastro"]:
            items = [
                "Use a bland, easy-to-digest diet in small frequent portions, such as rice, noodles, soup, toast, or applesauce.",
                "Avoid greasy, spicy, raw, alcoholic, or very sugary foods while the stomach is unsettled.",
            ]
        else:
            items = [
                "With fever or sore throat, favor warm fluids, soup, and softer foods that are easy to swallow.",
                "Avoid very spicy, very hot, or highly irritating foods until symptoms settle.",
            ]
        title = "Diet Guidance"
    return {"title": title, "items": items, "priority": "secondary"}


def _build_exercise_guidance(locale: str, flags: dict[str, bool], risk_level: str, *, age_group: str) -> dict | None:
    if risk_level in PRIMARY_RISK_LEVELS or any([flags["fever"], flags["chest_pain"], flags["short_breath"], flags["gastro"]]):
        return None
    if age_group in {"child", "adolescent"}:
        return None
    if locale.startswith("zh"):
        items = [
            "这几天先不要做高强度运动；如果精神状态允许，只保留轻量散步或简单拉伸。",
            "等到症状明显减轻、体温恢复稳定后，再逐步恢复日常运动量。",
        ]
        if age_group == "older_adult":
            items.append("如果本身有跌倒风险、头晕或基础慢病，恢复活动前先以室内短距离轻量活动为主。")
        title = "每日运动建议"
    else:
        items = [
            "Avoid intense exercise for now. If you feel well enough, keep activity light with short walks or gentle stretching only.",
            "Return to your normal exercise routine gradually once symptoms have clearly eased and temperature is stable.",
        ]
        if age_group == "older_adult":
            items.append("If baseline mobility is limited or dizziness is present, restart activity cautiously with short indoor movement first.")
        title = "Daily Activity Guidance"
    return {"title": title, "items": items, "priority": "secondary"}


def _build_monitoring_guidance(locale: str, flags: dict[str, bool], risk_level: str, *, age_group: str) -> dict:
    items: list[str] = []
    if locale.startswith("zh"):
        if flags["fever"]:
            items.append("每天记录体温变化以及退热后是否再次升高。")
        if flags["cough"] or flags["short_breath"]:
            items.append("留意咳嗽是否加重、是否出现胸闷气促，若家里有血氧仪可同步观察血氧变化。")
        if flags["gastro"]:
            items.append("记录腹泻/呕吐次数、是否能进水、尿量是否减少，以便判断脱水风险。")
        if flags["pain"]:
            items.append("记录疼痛部位、强度和是否影响睡眠或日常活动。")
        if age_group in {"child", "adolescent"}:
            items.append("未成年人建议由监护人一起观察精神状态、进食进水和夜间症状变化。")
        elif age_group == "older_adult":
            items.append("老年人建议额外留意精神反应、尿量、步态变化和是否出现明显乏力。")
        items.append("如果出现明显加重、持续高热、呼吸困难、胸痛、意识异常或无法进食进水，请立即线下就医。")
        title = "监测与复诊"
    else:
        if flags["fever"]:
            items.append("Track temperature through the day and note whether fever returns after settling.")
        if flags["cough"] or flags["short_breath"]:
            items.append("Watch for worsening cough, chest tightness, or breathlessness; if available, monitor oxygen saturation.")
        if flags["gastro"]:
            items.append("Record vomiting/diarrhea frequency, fluid intake, and urine output to watch for dehydration.")
        if flags["pain"]:
            items.append("Keep a short note of pain location, severity, and whether it is affecting sleep or normal activity.")
        if age_group in {"child", "adolescent"}:
            items.append("For minors, a caregiver should help monitor energy level, fluid intake, and overnight symptom changes.")
        elif age_group == "older_adult":
            items.append("For older adults, also watch mental status, urine output, gait change, and marked weakness.")
        items.append("Seek urgent in-person care immediately if symptoms clearly worsen or if chest pain, breathing trouble, confusion, or inability to keep fluids down appears.")
        title = "Monitoring and Follow-up"
    priority = "primary" if risk_level in {"medium", "high", "emergency"} else "secondary"
    return {"title": title, "items": _dedupe(items)[:4], "priority": priority}


def _recommend_department(locale: str, flags: dict[str, bool], *, age_group: str) -> str:
    zh = locale.startswith("zh")
    if flags["chest_pain"] or flags["short_breath"]:
        return "急诊" if zh else "the emergency department"
    if age_group in {"child", "adolescent"}:
        if flags["gastro"]:
            return "儿科或全科" if zh else "pediatrics or primary care"
        if flags["cough"] or flags["sore_throat"] or flags["fever"]:
            return "儿科或全科" if zh else "pediatrics or primary care"
        return "儿科或全科" if zh else "pediatrics or primary care"
    if flags["gastro"]:
        return "全科或消化内科" if zh else "primary care or gastroenterology"
    if flags["cough"] or flags["sore_throat"] or flags["fever"]:
        return "全科或呼吸内科" if zh else "primary care or respiratory medicine"
    return "全科" if zh else "primary care"


def _sanitize_advice_sections(advice_sections: dict[str, dict], *, locale: str, risk_level: str, sex: str) -> dict[str, dict]:
    unsafe_re = re.compile(r"\b\d+\s?mg\b|\b处方\b|\b服用\s*\d+|\btake\s+\d+", re.IGNORECASE)
    cleaned: dict[str, dict] = {}
    for key, section in advice_sections.items():
        items = [str(item).strip() for item in (section.get("items") or []) if str(item).strip()]
        items = [item for item in items if not unsafe_re.search(item)]
        items = [item for item in items if not has_sex_mismatch(item, sex)]
        if key == "exercise_guidance" and risk_level in PRIMARY_RISK_LEVELS:
            continue
        if not items:
            continue
        cleaned[key] = {
            "title": str(section.get("title") or key),
            "items": items[:4],
            "priority": "primary" if section.get("priority") == "primary" else "secondary",
        }
    if risk_level in PRIMARY_RISK_LEVELS and "exercise_guidance" in cleaned:
        cleaned.pop("exercise_guidance", None)
    return cleaned


def _detect_flags(text_blob: str) -> dict[str, bool]:
    worsening = _contains_any(text_blob, ["加重", "更严重", " worsening", "worse", "worsen"])
    if _contains_any(text_blob, ["没有加重", "未加重", "没有明显加重", "not worsening", "not worse", "no worse"]):
        worsening = False
    flags = {
        "fever": _contains_any(text_blob, ["发烧", "发热", "fever", "high temperature"]),
        "cough": _contains_any(text_blob, ["咳嗽", "cough"]),
        "sore_throat": _contains_any(text_blob, ["喉咙痛", "咽痛", "sore throat", "throat pain"]),
        "chest_pain": _contains_any(text_blob, ["胸痛", "chest pain"]),
        "short_breath": _contains_any(text_blob, ["呼吸困难", "气短", "shortness of breath", "breathing trouble"]),
        "headache": _contains_any(text_blob, ["头痛", "headache"]),
        "abdominal_pain": _contains_any(text_blob, ["腹痛", "肚子痛", "胃痛", "abdominal pain", "stomach pain"]),
        "diarrhea": _contains_any(text_blob, ["腹泻", "拉肚子", "diarrhea"]),
        "vomiting": _contains_any(text_blob, ["呕吐", "恶心", "vomit", "vomiting", "nausea"]),
        "fatigue": _contains_any(text_blob, ["乏力", "疲劳", "fatigue", "tired"]),
        "pain": _contains_any(text_blob, ["疼", "痛", "pain", "ache"]),
        "worsening": worsening,
        "gastro": False,
    }
    flags["gastro"] = flags["abdominal_pain"] or flags["diarrhea"] or flags["vomiting"]
    return flags


def _contains_any(text: str, needles: list[str]) -> bool:
    return any(needle in text for needle in needles)


def _dedupe(items: list[str]) -> list[str]:
    deduped: list[str] = []
    for item in items:
        if item not in deduped:
            deduped.append(item)
    return deduped
