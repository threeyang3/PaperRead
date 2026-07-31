# {{ paper_title_display }}

> [!abstract] 一句话概述
> {{ ai_summary_short }}

## 工作区导航

{% if links.ai_analysis %}- AI 分析：[[{{ links.ai_analysis | replace('.md', '') }}]]{% endif %}
{% if links.user_note %}- 我的笔记：[[{{ links.user_note | replace('.md', '') }}]]{% endif %}
{% if links.annotations %}- 标注：[[{{ links.annotations | replace('.md', '') }}]]{% endif %}
{% if links.review %}- 复盘：[[{{ links.review | replace('.md', '') }}]]{% endif %}
{% if links.community %}- 社区：[[{{ links.community | replace('.md', '') }}]]{% endif %}

{% if ai_recommendation %}
## 阅读建议

{{ ai_recommendation }}
{% if ai_relevance_reason is defined and ai_relevance_reason %}

**与当前研究方向的关联：** {{ ai_relevance_reason }}
{% endif %}
{% endif %}

{% if extraction.get('visual_assets', []) %}
## 论文视觉导读

> [!info] 图像覆盖
> 收录 {{ extraction.get('visual_assets', []) | length }} 张可追溯关键图片；优先采用 arXiv HTML 原图，不可用时回退到 PDF 裁剪。

{% set architecture_visuals = extraction.get('visual_assets', []) | selectattr('kind', 'equalto', 'architecture') | list %}
{% set result_visuals = extraction.get('visual_assets', []) | selectattr('kind', 'equalto', 'result') | list %}
{% set other_visuals = extraction.get('visual_assets', []) | selectattr('kind', 'equalto', 'figure') | list %}
{% for heading, visuals in [('架构、系统与方法图', architecture_visuals), ('实验与关键结果图', result_visuals), ('任务、硬件与其他关键图', other_visuals)] %}
{% if visuals %}
### {{ heading }}

{% for visual in visuals %}
#### Figure {{ visual.figure_number }} · PDF 第 {{ visual.page }} 页

![[{{ visual.path }}|950]]

> [!quote]- 原文图注
> {{ visual.caption }}
>
> 来源：{% if visual.get('source_type') == 'arxiv-html' %}[arXiv HTML 原图]({{ visual.get('source_url') }})；{% else %}PDF 裁剪；{% endif %}[[{{ paper_pdf_path }}#page={{ visual.page }}|在原 PDF 中打开本页]]

{% endfor %}
{% endif %}
{% endfor %}
{% endif %}

{% if sections.get('problem') %}
## 论文解决的问题

{{ sections.get('problem') }}
{% endif %}

{% if sections.get('contributions') %}
## 核心贡献

{% for item in sections.get('contributions', []) %}- {{ item }}
{% endfor %}
{% endif %}

{% if sections.get('method') %}
## 方法概述

{{ sections.get('method') }}
{% endif %}

{% if sections.get('experiments') %}
## 实验设计

{{ sections.get('experiments') }}
{% endif %}

{% if sections.get('results') %}
## 关键结果

{{ sections.get('results') }}
{% endif %}

## 研究质量判断

- 创新性：**{{ ai_novelty_score }}/5** — {{ ai_novelty_reason }}
- 完成度：**{{ ai_completeness_score }}/5** — {{ ai_completeness_reason }}
- 可复现性：**{{ ai_reproducibility_score }}/5** — {{ ai_reproducibility_reason }}

{% if sections.get('limitations') %}
## 局限性与潜在问题

{{ sections.get('limitations') }}
{% endif %}

{% if paper_cites or ai_related_papers or ai_method_links or ai_dataset_links %}
## 关系与双链

{% if paper_cites %}
### 已验证引用

{% for item in paper_cites %}- {{ item }}
{% endfor %}
{% endif %}
{% if ai_related_papers %}
### 语义相关论文

{% for item in ai_related_papers %}- {{ item }}（语义关系）
{% endfor %}
{% endif %}
{% if ai_method_links %}
### 方法实体

{{ ai_method_links | join('、') }}
{% endif %}
{% if ai_dataset_links %}
### 数据集实体

{{ ai_dataset_links | join('、') }}
{% endif %}
{% endif %}

> [!info]- 版本与 AI 来源
> {{ version_change_note }}
> 提供方：{{ ai_analysis_provider }}；模型：{{ ai_analysis_model }}；Prompt：{{ ai_analysis_prompt_version }}；时间：{{ ai_analyzed_at }}。

<!-- USER_NOTES_START -->

## 我的笔记

## 我的疑问

## 可借鉴思路

## 后续行动

<!-- USER_NOTES_END -->
