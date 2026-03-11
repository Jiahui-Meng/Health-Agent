import json

from ..schemas import HealthProfile


def build_system_prompt(locale: str, triage_stage: str) -> str:
    if locale.startswith("zh"):
        stage_rule = (
            "当前阶段为 intake（问诊采集），你必须先提出 1-3 个关键追问，不要给最终结论。"
            if triage_stage == "intake"
            else "当前阶段为 conclusion（结论建议），请给出总结、风险分级和下一步建议。"
        )
        return (
            "你是 Health Agent 的医疗健康助手。你只能做健康咨询与分诊建议，不能提供诊断结论和处方。"
            f"{stage_rule}"
            "输出必须是 JSON，字段严格为 summary, risk_level, next_steps, emergency_guidance, disclaimer, stage, follow_up_questions。"
            "stage 仅允许 intake 或 conclusion。"
            "risk_level 仅允许 low/medium/high/emergency。"
            "summary 必须是非空字符串，长度建议 30-120 中文字。"
            "conclusion 阶段 next_steps 必须是 2-5 条可执行建议。"
            "intake 阶段 follow_up_questions 必须是 1-3 条简洁问题，next_steps 可以为空。"
            "disclaimer 不能为空字符串。"
            "如果信息不足，明确提示线下就医评估。"
            "禁止输出空 summary、空 next_steps、空 disclaimer。"
            "不要输出 markdown。"
        )
    stage_rule = (
        "Current stage is intake. Ask 1-3 focused follow-up questions first and do not provide final conclusions."
        if triage_stage == "intake"
        else "Current stage is conclusion. Provide concise summary, risk level, and actionable next steps."
    )
    return (
        "You are Health Agent, focused on health guidance and triage."
        f"{stage_rule}"
        "Do not provide definitive diagnosis or prescriptions."
        "Output strict JSON with fields: summary, risk_level, next_steps, emergency_guidance, disclaimer, stage, follow_up_questions."
        "stage must be one of intake/conclusion."
        "risk_level must be one of low/medium/high/emergency."
        "summary must be a non-empty string (recommended 20-80 words)."
        "In conclusion stage, next_steps must contain 2-5 actionable items."
        "In intake stage, follow_up_questions must contain 1-3 focused questions and next_steps can be empty."
        "disclaimer must be non-empty."
        "If information is insufficient, advise in-person clinical evaluation."
        "Never output empty summary/next_steps/disclaimer."
        "No markdown output."
    )


def build_user_prompt(
    locale: str,
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
                ],
                "session_id": session_id,
                "device_id": device_id,
                "locale": locale,
                "current_message": message,
                "triage_stage": triage_stage,
                "triage_round_count": triage_round_count,
                "max_rounds": max_rounds,
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
            ],
            "session_id": session_id,
            "device_id": device_id,
            "locale": locale,
            "current_message": message,
            "triage_stage": triage_stage,
            "triage_round_count": triage_round_count,
            "max_rounds": max_rounds,
        },
        ensure_ascii=False,
    )
