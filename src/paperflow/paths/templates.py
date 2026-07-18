from __future__ import annotations

import re
import unicodedata
from pathlib import Path, PurePosixPath
from typing import Any


ALLOWED_VARIABLES = {
    "source",
    "paper_id",
    "arxiv_id",
    "version",
    "year",
    "month",
    "day",
    "title",
    "first_author",
    "primary_category",
    "category",
    "categories",
    "type",
    "primary_topic",
    "topics",
    "method_family",
    "analysis_profile",
    "analysis_id",
    "date",
}

ALLOWED_FILTERS = {
    "slug",
    "lower",
    "upper",
    "truncate",
    "replace",
    "default",
    "first",
    "join",
}

WINDOWS_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}

TOKEN_RE = re.compile(r"{{\s*([^{}]+?)\s*}}")
ILLEGAL_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


class PathTemplateError(ValueError):
    pass


def safe_component(value: Any, *, max_length: int = 100) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).strip()
    text = ILLEGAL_RE.sub("-", text)
    text = re.sub(r"\s+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip(" .-")
    if not text:
        text = "Unclassified"
    stem = text.split(".", 1)[0].upper()
    if stem in WINDOWS_RESERVED:
        text = "_" + text
    text = text.rstrip(" .")
    if len(text) > max_length:
        text = text[:max_length].rstrip(" .-")
    return text or "Unclassified"


def _parse_filter(token: str) -> tuple[str, list[str]]:
    name, separator, raw_args = token.partition(":")
    name = name.strip()
    if name not in ALLOWED_FILTERS:
        raise PathTemplateError(f"Unsupported path template filter: {name}")
    if not separator:
        return name, []
    if name == "replace":
        args = [part for part in raw_args.split(",", 1)]
        if len(args) != 2:
            raise PathTemplateError("replace filter requires `replace:old,new`")
        return name, args
    return name, [raw_args]


def _apply_filter(value: Any, name: str, args: list[str], missing: str) -> Any:
    if name == "default":
        return value if value not in (None, "", []) else (args[0] if args else missing)
    if name == "first":
        if isinstance(value, (list, tuple)):
            return value[0] if value else missing
        return str(value)[0] if str(value) else missing
    if name == "join":
        separator = args[0] if args else "-"
        if isinstance(value, (list, tuple)):
            return separator.join(str(item) for item in value)
        return str(value)
    text = str(value if value not in (None, "") else missing)
    if name == "slug":
        return safe_component(text)
    if name == "lower":
        return text.lower()
    if name == "upper":
        return text.upper()
    if name == "truncate":
        try:
            length = int(args[0])
        except (IndexError, ValueError) as exc:
            raise PathTemplateError("truncate filter requires an integer") from exc
        if length < 1 or length > 500:
            raise PathTemplateError("truncate length must be between 1 and 500")
        return text[:length]
    if name == "replace":
        return text.replace(args[0], args[1])
    raise PathTemplateError(f"Unsupported filter: {name}")


class SafePathTemplate:
    def __init__(
        self,
        template: str,
        *,
        missing_value: str = "Unclassified",
        max_path_length: int = 240,
    ):
        self.template = template.replace("\\", "/")
        self.missing_value = missing_value
        self.max_path_length = max_path_length
        self.variables = self._validate()

    def _validate(self) -> set[str]:
        if not self.template or self.template.startswith("/"):
            raise PathTemplateError("Path template must be a non-empty relative path")
        if re.match(r"^[A-Za-z]:", self.template):
            raise PathTemplateError("Drive-qualified paths are forbidden")
        variables: set[str] = set()
        for expression in TOKEN_RE.findall(self.template):
            parts = [part.strip() for part in expression.split("|")]
            variable = parts[0]
            if (
                variable not in ALLOWED_VARIABLES
                or any(character in variable for character in ".[]()")
            ):
                raise PathTemplateError(
                    f"Unsupported or unsafe path template variable: {variable}"
                )
            variables.add(variable)
            for item in parts[1:]:
                _parse_filter(item)
        remainder = TOKEN_RE.sub("", self.template)
        if "{{" in remainder or "}}" in remainder:
            raise PathTemplateError("Malformed path template expression")
        if ".." in PurePosixPath(remainder).parts:
            raise PathTemplateError("Parent traversal is forbidden")
        return variables

    def render(self, values: dict[str, Any]) -> str:
        def replace(match: re.Match[str]) -> str:
            parts = [part.strip() for part in match.group(1).split("|")]
            variable = parts[0]
            value: Any = values.get(variable, self.missing_value)
            for raw_filter in parts[1:]:
                name, args = _parse_filter(raw_filter)
                value = _apply_filter(value, name, args, self.missing_value)
            if isinstance(value, (list, tuple)):
                value = "-".join(str(item) for item in value)
            # Component-level sanitation must not discard a literal extension
            # before the full rendered path is length-limited below.
            return safe_component(value, max_length=4096)

        rendered = TOKEN_RE.sub(replace, self.template)
        parts = [
            safe_component(part, max_length=max(4096, self.max_path_length))
            for part in PurePosixPath(rendered).parts
        ]
        if not parts or any(part in {"", ".", ".."} for part in parts):
            raise PathTemplateError("Rendered path is empty or unsafe")
        result = PurePosixPath(*parts).as_posix()
        if len(result) > self.max_path_length:
            suffix = Path(result).suffix
            parent = PurePosixPath(result).parent.as_posix()
            budget = max(1, self.max_path_length - len(parent) - len(suffix) - 1)
            name = safe_component(Path(result).stem, max_length=budget) + suffix
            result = (
                PurePosixPath(parent, name).as_posix()
                if parent != "."
                else name
            )
        if len(result) > self.max_path_length:
            raise PathTemplateError(
                f"Rendered path exceeds max length {self.max_path_length}: {result}"
            )
        return result


def resolve_inside(root: Path, relative: str) -> Path:
    base = root.resolve()
    candidate = (base / Path(relative)).resolve()
    try:
        candidate.relative_to(base)
    except ValueError as exc:
        raise PathTemplateError(
            f"Rendered path escapes configured root: {relative}"
        ) from exc
    return candidate
