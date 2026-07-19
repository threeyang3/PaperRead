# {{ paper_title_display }}

> [!abstract] 一句话概述
> {{ ai_summary_short }}

## 基本信息

- 作者：{{ paper_authors | join('、') }}
- arXiv：[{{ paper_arxiv_id }}]({{ paper_abs_url }})
- PDF：[[{{ paper_pdf_path }}]]
- 项目主页：{{ paper_project_url }}
- 代码：{{ paper_code_url }}
- 数据集：{{ paper_dataset_url }}
- 主题：{{ ai_topic_links | join('、') }}
- AI 推荐结论：{{ ai_recommendation }}

## 阅读建议

### 是否值得阅读

{{ ai_recommendation }}

### 推荐阅读对象

具身智能、机器人学习与机器人操作研究者。

### 建议重点阅读章节

方法、实验、局限性。

### 可以快速略过的部分

依据个人背景略过熟悉的相关工作。

{% if extraction.get('visual_assets', []) %}
## 论文视觉导读

> [!info] 图像覆盖
> 已从原 PDF 提取 {{ extraction.get('visual_assets', []) | length }} 张可追溯关键图片。优先阅读架构与方法图，再用实验结果图核对论文结论。

{% set architecture_visuals = extraction.get('visual_assets', []) | selectattr('kind', 'equalto', 'architecture') | list %}
{% set result_visuals = extraction.get('visual_assets', []) | selectattr('kind', 'equalto', 'result') | list %}
{% set other_visuals = extraction.get('visual_assets', []) | selectattr('kind', 'equalto', 'figure') | list %}
{% if architecture_visuals %}
### 架构、系统与方法图

{% for visual in architecture_visuals %}
#### Figure {{ visual.figure_number }} · PDF 第 {{ visual.page }} 页

![[{{ visual.path }}|950]]

> [!quote]- 原文图注
> {{ visual.caption }}
>
> [[{{ paper_pdf_path }}#page={{ visual.page }}|在原 PDF 中打开本页]]

{% endfor %}
{% endif %}
{% if result_visuals %}
### 实验与关键结果图

{% for visual in result_visuals %}
#### Figure {{ visual.figure_number }} · PDF 第 {{ visual.page }} 页

![[{{ visual.path }}|950]]

> [!quote]- 原文图注
> {{ visual.caption }}
>
> [[{{ paper_pdf_path }}#page={{ visual.page }}|在原 PDF 中打开本页]]

{% endfor %}
{% endif %}
{% if other_visuals %}
### 任务、硬件与其他关键图

{% for visual in other_visuals %}
#### Figure {{ visual.figure_number }} · PDF 第 {{ visual.page }} 页

![[{{ visual.path }}|950]]

> [!quote]- 原文图注
> {{ visual.caption }}
>
> [[{{ paper_pdf_path }}#page={{ visual.page }}|在原 PDF 中打开本页]]

{% endfor %}
{% endif %}
{% endif %}
## 论文解决的问题

{{ sections.get('problem', '') }}

## 核心贡献

{% for item in sections.get('contributions', []) %}- {{ item }}
{% endfor %}
## 方法概述

{{ sections.get('method', '') }}

### 输入与输出

### 模型结构

### 训练方式

### 推理与控制流程

## 实验设计

{{ sections.get('experiments', '') }}

### 任务与数据集

### 对比基线

### 主要指标

### 消融实验

### 真机实验

## 关键结果

{{ sections.get('results', '') }}

## 创新性分析

- 评分：{{ ai_novelty_score }}/5
- 评分证据：{{ ai_novelty_reason }}
- 与已有工作的区别：见论文相关工作与方法章节。
- 可能只是工程组合的部分：需结合相关工作复核。

## 完成度分析

- 评分：{{ ai_completeness_score }}/5
- 评分证据：{{ ai_completeness_reason }}
- 实验覆盖：见实验章节。
- 未验证的问题：见局限性。

## 可复现性分析

- 评分：{{ ai_reproducibility_score }}/5
- 评分证据：{{ ai_reproducibility_reason }}
- 是否开源代码：{{ paper_has_code }}
- 是否提供训练配置：无法确认
- 是否提供数据或仿真环境：{{ paper_has_dataset }}
- 是否提供模型权重：无法确认
- 预估复现障碍：需核验依赖、数据和计算资源。

## 局限性与潜在问题

{{ sections.get('limitations', '') }}

## 与我的研究方向的关系

### 对具身智能研究的价值

### 对机器人操作研究的价值

### 对触觉和富接触任务的价值

### 可以借鉴到现有项目的内容

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

## 版本记录

- {{ version_change_note }}

## AI 分析来源与可信度

分析提供方：{{ ai_analysis_provider }}；模型：{{ ai_analysis_model }}；Prompt：{{ ai_analysis_prompt_version }}；时间：{{ ai_analyzed_at }}。

<!-- USER_NOTES_START -->

## 我的笔记

## 我的疑问

## 可借鉴思路

## 后续行动

<!-- USER_NOTES_END -->
