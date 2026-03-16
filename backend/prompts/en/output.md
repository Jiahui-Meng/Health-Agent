Output contract (strict JSON):
- Fields must be exactly: summary, risk_level, next_steps, emergency_guidance, disclaimer, stage, follow_up_questions, advice_sections
- stage must be: intake or conclusion
- risk_level must be: low / medium / high / emergency
- summary and disclaimer must be non-empty strings

Stage rules:
- intake: summary is a clinician-style transition line; follow_up_questions has 1-3 items; next_steps must be empty; advice_sections must be empty
- conclusion: provide actionable steps first, then one plain-language conclusion, then risk level; next_steps has 2-5 items; advice_sections on demand

Allowed advice_sections modules:
- medication_guidance
- visit_guidance
- rest_guidance
- diet_guidance
- exercise_guidance
- monitoring_guidance
