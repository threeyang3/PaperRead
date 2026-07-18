# {{ date }} Paper Brief

> Generated at {{ generated_at }} Asia/Shanghai

## Run summary

- Candidates: {{ stats.candidates }}
- After rule filtering: {{ stats.rule_filtered }}
- After lightweight AI filtering: {{ stats.ai_filtered }}
- Imported: {{ stats.imported }}
- Existing: {{ stats.existing }}
- Updated versions: {{ stats.updated }}
- Manual requests: {{ stats.manual }}
- Failed: {{ stats.failed }}
- Manual review: {{ stats.manual_review }}

## Today's priorities
{% for paper in papers %}- [[{{ paper.note }}|{{ paper.title }}]] ({{ paper.score }})
{% endfor %}
## Failures and errors
{% for error in errors %}- {{ error }}
{% endfor %}
## Run information

- run_id: {{ run_id }}
