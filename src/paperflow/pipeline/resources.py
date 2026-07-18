from __future__ import annotations

import re
from urllib.parse import urlsplit

URL_RE = re.compile(r"https?://[^\s<>\]\[{}]+", re.I)
BARE_DOMAIN_RE = re.compile(r"(?<![/@\w.-])(?:www\.)?[a-z0-9][a-z0-9-]*(?:\.[a-z0-9-]+)+\.[a-z]{2,}(?:/[\w./-]*)?", re.I)
GENERIC_HOSTS = {"openreview.net", "doi.org", "github.com", "arxiv.org"}


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
    code = next((url for url in urls if "github.com" in url.casefold() or "gitlab.com" in url.casefold()), "")
    dataset = ""
    for url in urls:
        position = text.find(url)
        nearby = text[max(0, position - 100):position].casefold()
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
