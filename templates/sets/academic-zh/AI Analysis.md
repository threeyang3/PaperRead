# AI 分析 · {{ paper.display_title }}

{{ analysis.summary_short or ai_summary_short }}

{% if sections %}{% for name, text in sections.items() %}{% if text %}
## {{ name }}

{{ text }}
{% endif %}{% endfor %}{% endif %}

> [!info]- 来源
> {{ provenance.provider }} / {{ provenance.model }} / {{ provenance.prompt }}
