# {{ paper.display_title }}

> [!abstract] 一句话概述
> {{ analysis.summary_short or ai_summary_short }}

## 工作区

- AI 分析：[[{{ links.ai_analysis | replace('.md', '') }}]]
- 我的笔记：[[{{ links.user_note | replace('.md', '') }}]]
- PDF：[[{{ paper.pdf_path | replace('.pdf', '') }}]]

## 阅读建议

{{ analysis.recommendation or ai_recommendation }}

## 关系

{% for item in relations.related %}- {{ item }}
{% endfor %}
