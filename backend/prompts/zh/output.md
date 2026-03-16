输出契约（严格 JSON）：
- 字段固定为: summary, risk_level, next_steps, emergency_guidance, disclaimer, stage, follow_up_questions, advice_sections
- stage 仅允许: intake 或 conclusion
- risk_level 仅允许: low / medium / high / emergency
- summary 和 disclaimer 必须为非空字符串

阶段规则：
- intake：summary 必须是医生式过渡语；follow_up_questions 为 1-3 条；next_steps 为空；advice_sections 为空
- conclusion：先给可执行建议，再给一句通俗结论，再给风险等级；next_steps 为 2-5 条；advice_sections 按需填写允许模块

advice_sections 允许模块：
- medication_guidance
- visit_guidance
- rest_guidance
- diet_guidance
- exercise_guidance
- monitoring_guidance
