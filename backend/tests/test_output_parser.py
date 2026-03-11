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
