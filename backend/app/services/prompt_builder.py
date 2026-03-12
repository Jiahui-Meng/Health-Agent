import json

from ..schemas import HealthProfile
from .profile_guardrails import profile_guardrails_payload


def build_system_prompt(locale: str, triage_stage: str) -> str:
    if locale.startswith("zh"):
        stage_rule = (
            "当前阶段为 intake（问诊采集），你必须像医生门诊问诊一样自然追问，优先提出 1-2 个关键问题，最多 3 个。"
            "不要给最终结论，不要给风险等级说明，不要给治疗建议，不要用免责声明式结束语。"
            if triage_stage == "intake"
            else "当前阶段为 conclusion（结论建议），请先给出可执行建议，再给一句通俗易懂的结论总结，最后给出风险分级。"
        )
        return (
            "你是 Health Agent 的医疗健康助手。你只能做健康咨询与分诊建议，不能提供诊断结论和处方。"
            f"{stage_rule}"
            "输出必须是 JSON，字段严格为 summary, risk_level, next_steps, emergency_guidance, disclaimer, stage, follow_up_questions, advice_sections。"
            "stage 仅允许 intake 或 conclusion。"
            "risk_level 仅允许 low/medium/high/emergency。"
            "summary 必须是非空字符串。"
            "conclusion 阶段 next_steps 必须是 2-5 条可执行建议，并应当比 summary 更具体。"
            "conclusion 阶段 summary 必须是一句通俗、易理解的结论，不要抽象或过度学术化。"
            "conclusion 阶段 advice_sections 应按需返回，允许的模块只有 medication_guidance, visit_guidance, rest_guidance, diet_guidance, exercise_guidance, monitoring_guidance。"
            "conclusion 阶段若出现用药建议，只能给非处方的一般性原则和禁忌提醒，禁止剂量、疗程、处方药指令。"
            "conclusion 阶段若出现挂号建议，只能建议急诊/全科/相关专科，不要推荐具体医院。"
            "intake 阶段 summary 必须是医生式过渡语，不得表示总结、判断或风险结论。"
            "intake 阶段 follow_up_questions 必须是 1-3 条自然、简洁、像医生口头追问的问题，next_steps 必须为空，advice_sections 必须为空。"
            "disclaimer 不能为空字符串。"
            "如果信息不足，明确提示线下就医评估。"
            "必须严格遵守用户资料约束，尤其是性别、年龄段和地区上下文。"
            "不能主动提出与该性别明显不相符的专属问题或建议。"
            "禁止输出空 summary、空 next_steps、空 disclaimer。"
            "不要输出 markdown。"
        )
    stage_rule = (
        "Current stage is intake. Ask in a natural clinician-like tone, usually 1-2 focused follow-up questions and no more than 3."
        "Do not provide conclusions, risk-level explanations, treatment advice, or disclaimer-style closing language."
        if triage_stage == "intake"
        else "Current stage is conclusion. Provide actionable next steps first, then one plain-language conclusion, then the risk level."
    )
    return (
        "You are Health Agent, focused on health guidance and triage."
        f"{stage_rule}"
        "Do not provide definitive diagnosis or prescriptions."
        "Output strict JSON with fields: summary, risk_level, next_steps, emergency_guidance, disclaimer, stage, follow_up_questions, advice_sections."
        "stage must be one of intake/conclusion."
        "risk_level must be one of low/medium/high/emergency."
        "summary must be a non-empty string."
        "In conclusion stage, next_steps must contain 2-5 actionable items and should be more specific than the summary."
        "In conclusion stage, summary must be a plain-language takeaway that is easy to understand."
        "In conclusion stage, advice_sections should be filled on demand using only these modules: medication_guidance, visit_guidance, rest_guidance, diet_guidance, exercise_guidance, monitoring_guidance."
        "Medication guidance may only contain general OTC principles or caution notes, never dosage, duration, or prescription instructions."
        "Visit guidance may recommend urgent care, primary care, or a specialty, but never a specific hospital."
        "In intake stage, summary must be a clinician-like transition line rather than a conclusion."
        "In intake stage, follow_up_questions must contain 1-3 natural focused questions, next_steps must be empty, and advice_sections must be empty."
        "disclaimer must be non-empty."
        "If information is insufficient, advise in-person clinical evaluation."
        "You must strictly respect the user's profile guardrails, especially sex, age-group, and region context."
        "Avoid obviously mismatched sex-specific questions or advice."
        "Never output empty summary/next_steps/disclaimer."
        "No markdown output."
    )


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
                    "必须先调用 get_session_context 读取上下文。",
                    "必须调用 analyze_health_input 分析当前消息。",
                    "必须调用 build_health_response_plan 确认本轮应为 intake 还是 conclusion。",
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
                "Call get_session_context first.",
                "Call analyze_health_input for the current user message.",
                "Call build_health_response_plan to confirm whether this round is intake or conclusion.",
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
