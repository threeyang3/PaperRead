# {{ date }} 论文简报

> 生成时间：中国北京时间 {{ generated_at }}

## 运行摘要

- 检索候选：{{ stats.candidates }}
- 规则筛选后：{{ stats.rule_filtered }}
- AI 初筛后：{{ stats.ai_filtered }}
- 完整导入：{{ stats.imported }}
- 已存在：{{ stats.existing }}
- 更新版本：{{ stats.updated }}
- 手动请求：{{ stats.manual }}
- 失败：{{ stats.failed }}
- 等待人工审核：{{ stats.manual_review }}

## 今日优先推荐
{% for paper in papers %}- [[{{ paper.note }}|{{ paper.title }}]]（{{ paper.score }}）
{% endfor %}
## 高创新性论文

## 高可复现性论文

## 与触觉和富接触操作最相关

## 与 VLA 和世界模型最相关

## 不建议优先阅读

## 失败与异常
{% for error in errors %}- {{ error }}
{% endfor %}
## 运行信息

- run_id: {{ run_id }}

