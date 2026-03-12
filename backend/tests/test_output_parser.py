from app.services.output_parser import parse_model_json


def test_parse_model_json_defaults_to_conclusion_stage():
    parsed = parse_model_json('{"summary":"ok","risk_level":"low","next_steps":["a"],"disclaimer":"d"}', "en-US")
    assert parsed["stage"] == "conclusion"
    assert parsed["follow_up_questions"] is None


def test_parse_model_json_intake_fallback_questions():
    parsed = parse_model_json(
        '{"summary":"需要进一步了解","risk_level":"medium","next_steps":[],"disclaimer":"仅供参考","stage":"intake"}',
        "zh-CN",
    )
    assert parsed["stage"] == "intake"
    assert len(parsed["follow_up_questions"]) >= 1
    assert parsed["next_steps"] == []


def test_parse_model_json_intake_fallback_summary_is_doctor_like():
    parsed = parse_model_json(
        '{"summary":"","risk_level":"medium","next_steps":[],"disclaimer":"","stage":"intake","follow_up_questions":[]}',
        "zh-CN",
    )
    assert parsed["stage"] == "intake"
    assert "我先确认" in parsed["summary"] or "问清楚" in parsed["summary"]


def test_parse_model_json_preserves_advice_sections_on_conclusion():
    parsed = parse_model_json(
        '{"summary":"结论","risk_level":"medium","next_steps":["观察"],"disclaimer":"仅供参考","stage":"conclusion","advice_sections":{"visit_guidance":{"title":"挂号建议","items":["预约全科"],"priority":"primary"}}}',
        "zh-CN",
    )
    assert parsed["stage"] == "conclusion"
    assert parsed["advice_sections"] is not None
    assert parsed["advice_sections"]["visit_guidance"]["title"] == "挂号建议"
