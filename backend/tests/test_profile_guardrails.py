from app.services.profile_guardrails import (
    has_sex_mismatch,
    normalize_sex,
    profile_guardrails_payload,
    sex_guardrails,
)


def test_normalize_sex_variants():
    assert normalize_sex("男") == "male"
    assert normalize_sex("male") == "male"
    assert normalize_sex("woman") == "female"
    assert normalize_sex("") == ""


def test_sex_guardrails_payload_contains_expected_fields():
    payload = profile_guardrails_payload(sex="男", birth_year="1990", region_code="hk", locale="zh-CN")
    assert payload["sex_normalized"] == "male"
    assert len(payload["sex_specific_guardrails"]) >= 1
    assert payload["age_group"] == "adult"
    assert payload["region_normalized"] == "HK"


def test_has_sex_mismatch_detects_forbidden_terms():
    assert has_sex_mismatch("最近一次月经是什么时候？", "male") is True
    assert has_sex_mismatch("可以考虑前列腺检查。", "female") is True
    assert has_sex_mismatch("咳嗽从什么时候开始？", "male") is False


def test_sex_guardrails_are_locale_aware():
    assert any("月经" in item for item in sex_guardrails("male", "zh-CN"))
    assert any("prostate" in item for item in sex_guardrails("female", "en-US"))


def test_age_and_region_guardrails_are_included():
    payload = profile_guardrails_payload(sex="女", birth_year="2014", region_code="jp", locale="en-US")
    assert payload["age_group"] in {"child", "adolescent"}
    assert len(payload["age_specific_guardrails"]) >= 1
    assert len(payload["region_specific_guardrails"]) >= 1
