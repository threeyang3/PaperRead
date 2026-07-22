# {{ paper_title_display }}

> [!abstract] One-sentence overview
> {{ ai_summary_short }}

{% if ai_recommendation %}
## Reading recommendation

{{ ai_recommendation }}
{% if ai_relevance_reason is defined and ai_relevance_reason %}

**Relevance to the current research profile:** {{ ai_relevance_reason }}
{% endif %}
{% endif %}

{% if extraction.get('visual_assets', []) %}
## Visual guide

> [!info] Visual coverage
> {{ extraction.get('visual_assets', []) | length }} traceable key figures are included. Original arXiv HTML images are preferred, with PDF crops used as fallback.

{% set architecture_visuals = extraction.get('visual_assets', []) | selectattr('kind', 'equalto', 'architecture') | list %}
{% set result_visuals = extraction.get('visual_assets', []) | selectattr('kind', 'equalto', 'result') | list %}
{% set other_visuals = extraction.get('visual_assets', []) | selectattr('kind', 'equalto', 'figure') | list %}
{% for heading, visuals in [('Architecture, systems, and methods', architecture_visuals), ('Experiments and key results', result_visuals), ('Tasks, hardware, and other figures', other_visuals)] %}
{% if visuals %}
### {{ heading }}

{% for visual in visuals %}
#### Figure {{ visual.figure_number }} · PDF page {{ visual.page }}

![[{{ visual.path }}|950]]

> [!quote]- Original caption
> {{ visual.caption }}
>
> Source: {% if visual.get('source_type') == 'arxiv-html' %}[original arXiv HTML image]({{ visual.get('source_url') }}); {% else %}PDF crop; {% endif %}[[{{ paper_pdf_path }}#page={{ visual.page }}|open the original PDF page]]

{% endfor %}
{% endif %}
{% endfor %}
{% endif %}

{% if sections.get('problem') %}
## Problem

{{ sections.get('problem') }}
{% endif %}

{% if sections.get('contributions') %}
## Contributions

{% for item in sections.get('contributions', []) %}- {{ item }}
{% endfor %}
{% endif %}

{% if sections.get('method') %}
## Method

{{ sections.get('method') }}
{% endif %}

{% if sections.get('experiments') %}
## Experiments

{{ sections.get('experiments') }}
{% endif %}

{% if sections.get('results') %}
## Key results

{{ sections.get('results') }}
{% endif %}

## Research quality assessment

- **Novelty {{ ai_novelty_score }}/5:** {{ ai_novelty_reason }}
- **Completeness {{ ai_completeness_score }}/5:** {{ ai_completeness_reason }}
- **Reproducibility {{ ai_reproducibility_score }}/5:** {{ ai_reproducibility_reason }}

{% if sections.get('limitations') %}
## Limitations

{{ sections.get('limitations') }}
{% endif %}

{% if paper_cites or ai_related_papers or ai_method_links or ai_dataset_links %}
## Relations and backlinks

{% if paper_cites %}
### Verified citations

{% for item in paper_cites %}- {{ item }}
{% endfor %}
{% endif %}
{% if ai_related_papers %}
### Semantically related papers

{% for item in ai_related_papers %}- {{ item }} (semantic relation)
{% endfor %}
{% endif %}
{% if ai_method_links %}
### Method entities

{{ ai_method_links | join(', ') }}
{% endif %}
{% if ai_dataset_links %}
### Dataset entities

{{ ai_dataset_links | join(', ') }}
{% endif %}
{% endif %}

> [!info]- Version and AI provenance
> {{ version_change_note }}
> Provider: {{ ai_analysis_provider }}; model: {{ ai_analysis_model }}; prompt: {{ ai_analysis_prompt_version }}; time: {{ ai_analyzed_at }}.

<!-- USER_NOTES_START -->

## My notes

## Questions

## Ideas to reuse

## Next actions

<!-- USER_NOTES_END -->
