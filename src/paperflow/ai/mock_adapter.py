from __future__ import annotations
from pathlib import Path
from paperflow.models import Analysis, PaperMetadata


class MockAdapter:
    provider = "mock"
    model = "deterministic-v1"

    def analyze(self, metadata: PaperMetadata, text_path: Path) -> Analysis:
        text = (metadata.paper_title + " " + metadata.paper_abstract).lower()
        topic = "Tactile Sensing" if "tactile" in text else "Vision Language Action" if "vision" in text and "action" in text else "Embodied Intelligence"
        reproducibility = 4 if metadata.paper_code_url else 3
        return Analysis(
            ai_relevance_score=4.2, ai_relevance_reason="标题与摘要符合默认具身智能检索领域。",
            ai_topic_primary=topic, ai_topics=[topic], ai_method_family=["robot learning"], ai_task_types=["manipulation"],
            ai_novelty_score=3, ai_novelty_confidence=0.7, ai_novelty_reason="提供了明确、可检验的技术贡献。",
            ai_completeness_score=3, ai_completeness_confidence=0.7, ai_completeness_reason="实验基本支持主要结论。",
            ai_reproducibility_score=reproducibility, ai_reproducibility_confidence=0.65, ai_reproducibility_reason="方法细节可用；公开资源状态需人工复核。",
            ai_overall_confidence=0.68, ai_recommendation="建议精读方法与实验章节。", ai_summary_short=f"{metadata.paper_title} 的结构化 Mock 分析。",
            ai_estimated_reading_priority=4,
            sections={"problem": "研究机器人学习与操作问题。", "contributions": ["提出并验证方法"], "method": "详见论文方法章节。", "experiments": "详见论文实验章节。", "results": "结果支持主要主张。", "limitations": "需要进一步核验泛化性与公开资源。"},
        )

