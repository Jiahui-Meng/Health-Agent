from app.services.prompt_pack import build_system_prompt_from_pack, validate_prompt_pack_files


def test_prompt_pack_files_exist():
    validate_prompt_pack_files()


def test_prompt_pack_renders_user_card_fields():
    prompt = build_system_prompt_from_pack(
        locale="en-US",
        context={
            "stage_rule_en": "Current stage is intake.",
            "user": {
                "username": "demo-user",
                "sex": "male",
                "birth_year": "1988",
                "region_code": "HK",
                "conditions": ["asthma"],
                "medications": ["inhaler"],
                "allergies": ["penicillin"],
                "core_history_summary": "Recurring cough",
            },
        },
    )
    assert "demo-user" in prompt
    assert "Recurring cough" in prompt
    assert "data_availability.md" in prompt
