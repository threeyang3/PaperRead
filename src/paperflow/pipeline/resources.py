from __future__ import annotations

import re
from urllib.parse import urlsplit

URL_RE = re.compile(r"https?://[^\s<>\]\[{}]+", re.I)
BARE_DOMAIN_RE = re.compile(r"(?<![/@\w.-])(?:www\.)?[a-z0-9][a-z0-9-]*(?:\.[a-z0-9-]+)+\.[a-z]{2,}(?:/[\w./-]*)?", re.I)
GENERIC_HOSTS = {"openreview.net", "doi.org", "github.com", "arxiv.org"}
REFERENCE_HEADING_RE = re.compile(
    r"(?im)^\s*(?:\d+[\s.]*)?(?:references|bibliography)\s*$"
)
CODE_CONTEXT_WORDS = (
    "code",
    "source",
    "implementation",
    "repository",
    "github",
    "gitlab",
    "available at",
)


def _repository_path_is_specific(url: str) -> bool:
    parsed = urlsplit(url)
    host = parsed.netloc.casefold().split(":", 1)[0]
    if host not in {"github.com", "www.github.com", "gitlab.com", "www.gitlab.com"}:
        return False
    segments = [segment for segment in parsed.path.split("/") if segment]
    return len(segments) >= 2


def _code_link_score(text: str, url: str, reference_start: int) -> int:
    position = text.find(url)
    if position < 0:
        return -100
    nearby = text[max(0, position - 180) : position + len(url) + 80].casefold()
    score = 6 if position < reference_start else -6
    score += sum(2 for word in CODE_CONTEXT_WORDS if word in nearby)
    return score


def find_resource_links(text: str) -> dict[str, str]:
    urls = []
    for match in URL_RE.finditer(text):
        url = match.group(0).rstrip(".,;:)'\"")
        if url not in urls and "arxiv.org" not in urlsplit(url).netloc.casefold():
            urls.append(url)
    for match in BARE_DOMAIN_RE.finditer(text):
        value = match.group(0).rstrip(".,;:)'\"")
        url = "https://" + value
        if url not in urls and "arxiv.org" not in urlsplit(url).netloc.casefold():
            urls.append(url)
    reference_match = REFERENCE_HEADING_RE.search(text)
    reference_start = reference_match.start() if reference_match else len(text)
    code_candidates = [
        url for url in urls if _repository_path_is_specific(url)
    ]
    ranked_code = sorted(
        code_candidates,
        key=lambda url: (_code_link_score(text, url, reference_start), -urls.index(url)),
        reverse=True,
    )
    code = (
        ranked_code[0]
        if ranked_code
        and _code_link_score(text, ranked_code[0], reference_start) >= 4
        else ""
    )
    dataset = ""
    for url in urls:
        position = text.find(url)
        if position < 0 or position >= reference_start:
            continue
        host = urlsplit(url).netloc.casefold().split(":", 1)[0]
        if host in {"github.com", "www.github.com", "gitlab.com", "www.gitlab.com"}:
            if not _repository_path_is_specific(url):
                continue
        nearby = text[max(0, position - 120) : position].casefold()
        if any(word in nearby for word in ("dataset", "data set", "download data")):
            dataset = url
            break
    project = next((url for url in urls if url != code and urlsplit(url).netloc.casefold() not in GENERIC_HOSTS), "")
    return {"paper_project_url": project, "paper_code_url": code, "paper_dataset_url": dataset}


def plausible_resource_url(value: str) -> bool:
    try:
        host = urlsplit(value).netloc.casefold().split(":", 1)[0]
        tld = host.rsplit(".", 1)[-1]
        return bool(host and tld.isalpha() and len(tld) >= 2)
    except Exception:
        return False
