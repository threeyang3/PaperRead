# {{ paper_title }}

> [!abstract] One-sentence overview
> {{ ai_summary_short }}

## Paper information

- Authors: {{ paper_authors | join(', ') }}
- arXiv: [{{ paper_arxiv_id }}]({{ paper_abs_url }})
- PDF: [[{{ paper_pdf_path }}]]
- Project: {{ paper_project_url }}
- Code: {{ paper_code_url }}
- Dataset: {{ paper_dataset_url }}
- Topics: {{ ai_topics | join(', ') }}
- AI recommendation: {{ ai_recommendation }}

## Reading guide

### Is it worth reading?

{{ ai_recommendation }}

### Suggested audience

Researchers in embodied intelligence, robot learning, and robot manipulation.

### Sections to prioritize

Methods, experiments, and limitations.

## Problem

{{ sections.get('problem', '') }}

## Contributions

{% for item in sections.get('contributions', []) %}- {{ item }}
{% endfor %}
## Method

{{ sections.get('method', '') }}

## Experiments

{{ sections.get('experiments', '') }}

## Key results

{{ sections.get('results', '') }}

## Novelty

- Score: {{ ai_novelty_score }}/5
- Evidence: {{ ai_novelty_reason }}

## Completeness

- Score: {{ ai_completeness_score }}/5
- Evidence: {{ ai_completeness_reason }}

## Reproducibility

- Score: {{ ai_reproducibility_score }}/5
- Evidence: {{ ai_reproducibility_reason }}
- Open-source code: {{ paper_has_code }}
- Dataset or environment: {{ paper_has_dataset }}

## Limitations

{{ sections.get('limitations', '') }}

## Related papers

## Version history

- {{ version_change_note }}

## AI analysis provenance

Provider: {{ ai_analysis_provider }}; model: {{ ai_analysis_model }}; prompt: {{ ai_analysis_prompt_version }}; time: {{ ai_analyzed_at }}.

<!-- USER_NOTES_START -->

## My notes

## Questions

## Ideas to reuse

## Next actions

<!-- USER_NOTES_END -->
