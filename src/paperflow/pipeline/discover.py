from __future__ import annotations
from datetime import timedelta
from ruamel.yaml import YAML
from paperflow.config import Config
from paperflow.models import PaperMetadata
from paperflow.sources.arxiv import ArxivSource
from paperflow.ai.relevance import screen_relevance
from paperflow.utils import now_beijing


def rule_score(paper: PaperMetadata, profile: dict) -> float:
    text = f"{paper.paper_title} {paper.paper_abstract}".lower()
    score = 0.0
    score += sum(1.2 for term in profile["strong_keywords"] if term.lower() in text)
    score += sum(0.6 for term in profile["medium_keywords"] if term.lower() in text)
    score -= sum(1.5 for term in profile["negative_keywords"] if term.lower() in text)
    if set(paper.paper_categories) & set(profile["include_categories"]):
        score += 1.0
    return round(min(5.0, max(0.0, score)), 2)


def discover(cfg: Config) -> tuple[list[PaperMetadata], dict]:
    yaml = YAML(typ="safe")
    profiles = yaml.load((cfg.root / "90 System/Taxonomy/arxiv-query-profiles.yaml").read_text(encoding="utf-8"))["profiles"]
    profile = profiles[cfg.section("discovery")["profile"]]
    query = " OR ".join(f"cat:{category}" for category in profile["include_categories"])
    section = cfg.section("arxiv")
    cache_dir = cfg.root / ".paperflow/cache/arxiv" if cfg.section("retention").get("keep_raw_api_responses", True) else None
    source = ArxivSource(section["timeout_seconds"], section["max_retries"], section["request_interval_seconds"], cache_dir=cache_dir)
    papers = source.discover(query, cfg.section("discovery")["max_candidates"])
    cutoff = now_beijing().date() - timedelta(days=cfg.section("discovery")["lookback_days"])
    recent = [p for p in papers if p.paper_updated_date >= cutoff]
    scored = [(p, rule_score(p, profile)) for p in recent]
    rule_selected = [p for p, score in scored if score >= cfg.section("discovery")["relevance_threshold"]]
    analysis = cfg.section("analysis")
    relevance = screen_relevance(
        cfg.root,
        rule_selected,
        analysis.get("relevance_provider", "codex"),
        analysis.get("relevance_model", analysis.get("model", "gpt-5.4")),
        min(int(analysis["timeout_seconds"]), 600),
        cfg.section("discovery")["relevance_threshold"],
    )
    ai_selected = [paper for paper in rule_selected if relevance[paper.paper_uid]["recommended"] and relevance[paper.paper_uid]["score"] >= cfg.section("discovery")["relevance_threshold"]]
    return ai_selected[:cfg.section("discovery")["max_full_analyses_per_run"]], {
        "candidates": len(papers),
        "rule_filtered": len(rule_selected),
        "ai_filtered": len(ai_selected),
        "rule_scores": {p.paper_uid: score for p, score in scored},
        "ai_relevance": relevance,
    }
