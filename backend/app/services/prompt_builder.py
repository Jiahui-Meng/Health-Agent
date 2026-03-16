import json

from ..schemas import HealthProfile
from .profile_guardrails import profile_guardrails_payload
from .prompt_pack import build_system_prompt_from_pack


def build_system_prompt(locale: str, triage_stage: str, user_card: dict | None = None) -> str:
    user_card = user_card or {}
    context = {
        "locale": locale,
        "triage_stage": triage_stage,
        "stage_rule_zh": (
            "当前阶段为 intake（问诊采集），你必须像医生门诊问诊一样自然追问，优先提出 1-2 个关键问题，最多 3 个。不要给最终结论，不要给风险等级说明，不要给治疗建议。"
            if triage_stage == "intake"
            else "当前阶段为 conclusion（结论建议），请先给出可执行建议，再给一句通俗易懂的结论总结，最后给出风险分级。"
        ),
        "stage_rule_en": (
            "Current stage is intake. Ask in a natural clinician-like tone with 1-2 focused follow-up questions and no more than 3. Do not provide conclusions, risk labels, or treatment advice."
            if triage_stage == "intake"
            else "Current stage is conclusion. Provide actionable next steps first, then one plain-language conclusion, then risk level."
        ),
        "user": {
            "username": user_card.get("username", ""),
            "sex": user_card.get("sex", ""),
            "birth_year": user_card.get("birth_year", ""),
            "region_code": user_card.get("region_code", ""),
            "conditions": user_card.get("conditions", []),
            "medications": user_card.get("medications", []),
            "allergies": user_card.get("allergies", []),
            "core_history_summary": user_card.get("core_history_summary", ""),
        },
    }
    return build_system_prompt_from_pack(locale=locale, context=context)


def build_user_prompt(
    locale: str,
    region_code: str,
    message: str,
    profile: HealthProfile | None,
    long_summary: str,
    recent_messages: list[dict[str, str]],
    graph_context: dict,
    triage_stage: str,
    triage_round_count: int,
    max_rounds: int,
    required_slots: list[str],
) -> str:
    payload = {
        "locale": locale,
        "user_message": message,
        "health_profile": profile.model_dump() if profile else {},
        **profile_guardrails_payload(
            sex=profile.sex if profile else "",
            birth_year=profile.age_range if profile else "",
            region_code=region_code,
            locale=locale,
        ),
        "long_term_summary": long_summary,
        "recent_messages": recent_messages,
        "graph_context": graph_context,
        "triage_stage": triage_stage,
        "triage_round_count": triage_round_count,
        "max_rounds": max_rounds,
        "required_slots": required_slots,
        "requirements": {
            "enforce_safety": True,
            "needs_triage": True,
            "no_diagnosis_no_prescription": True,
            "summary_non_empty": True,
            "next_steps_non_empty": triage_stage == "conclusion",
            "disclaimer_non_empty": True,
            "intake_doctor_style": triage_stage == "intake",
            "advice_sections_required": triage_stage == "conclusion",
        },
    }
    return json.dumps(payload, ensure_ascii=False)


def build_codex_mcp_prompt(
    *,
    locale: str,
    session_id: str,
    device_id: str,
    message: str,
    triage_stage: str,
    triage_round_count: int,
    max_rounds: int,
) -> str:
    if locale.startswith("zh"):
        return json.dumps(
            {
                "task": "你正在为 Health Agent 生成一次受控医疗分诊回复。",
                "rules": [
                    "默认先基于当前消息和已有上下文判断信息是否充分。",
                    "如果关键信息不足、需要历史证据、或风险判断不稳定，必须调用 get_session_context。",
                    "当需要判断危险信号、缺失槽位或急症分流时，调用 analyze_health_input。",
                    "当不确定本轮该继续追问还是进入结论时，调用 build_health_response_plan。",
                    "在 conclusion 阶段，若涉及历史趋势或风险变化，至少调用一次 get_session_context。",
                    "不要调用 persist_chat_turn；宿主应用会在最终 JSON 通过校验后自行落库。",
                    "最终输出必须严格符合 JSON 契约，不要输出 markdown。",
                    "禁止诊断结论、禁止处方和剂量建议。",
                    "如果当前阶段是 intake，只能像医生一样自然追问，不要写风险等级、初步判断、建议观察等结论型内容。",
                    "如果当前阶段是 conclusion，应按需输出 advice_sections，只能包含允许的建议模块。",
                    "必须严格遵守用户性别约束，禁止输出与其性别明显不相符的专属问题或建议。",
                    "还要结合年龄段和地区上下文调整问法、急症阈值和应急文案。",
                ],
                "session_id": session_id,
                "device_id": device_id,
                "locale": locale,
                "current_message": message,
                "triage_stage": triage_stage,
                "triage_round_count": triage_round_count,
                "max_rounds": max_rounds,
                "sex_hint": "Read health_profile.sex and follow its constraints strictly via MCP context.",
                "profile_hint": "Read birth year and region from MCP context and respect profile guardrails before asking questions or giving advice.",
            },
            ensure_ascii=False,
        )
    return json.dumps(
        {
            "task": "Generate one controlled medical triage response for Health Agent.",
            "rules": [
                "First decide whether currently provided context is sufficient.",
                "If key slots are missing, historical evidence is needed, or risk judgment is unstable, call get_session_context.",
                "Call analyze_health_input when danger-signal checks, slot-gaps, or emergency routing are needed.",
                "Call build_health_response_plan when stage decision between intake and conclusion is uncertain.",
                "In conclusion stage, if trend/risk evolution is referenced, call get_session_context at least once.",
                "Do not call persist_chat_turn; the host application persists the final validated response.",
                "Final output must strictly match the JSON contract with no markdown.",
                "Do not provide diagnosis, prescriptions, or dosage instructions.",
                "If the current stage is intake, only ask natural doctor-like follow-up questions and avoid risk labels, preliminary assessments, or advice-style conclusions.",
                "If the current stage is conclusion, populate advice_sections only when relevant and only with the allowed guidance modules.",
                "Strictly respect the user's sex constraints and avoid obviously mismatched sex-specific questions or advice.",
                "Also adapt wording, urgency threshold, and emergency references to age-group and region context.",
            ],
            "session_id": session_id,
            "device_id": device_id,
            "locale": locale,
            "current_message": message,
            "triage_stage": triage_stage,
            "triage_round_count": triage_round_count,
            "max_rounds": max_rounds,
            "sex_hint": "Read health_profile.sex and follow its constraints strictly via MCP context.",
            "profile_hint": "Read birth year and region from MCP context and respect profile guardrails before asking questions or giving advice.",
        },
        ensure_ascii=False,
    )
