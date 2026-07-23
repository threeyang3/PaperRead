from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from packaging.version import Version
from paperflow._version import __version__


APPLICATION_VERSION = __version__


@dataclass(frozen=True)
class VersionContract:
    application_version: str = APPLICATION_VERSION
    workspace_schema_version: int = 3
    raw_data_schema_version: int = 1
    ai_analysis_schema_version: int = 1
    user_data_schema_version: int = 1
    public_feed_schema_version: int = 2
    annotation_schema_version: int = 1
    community_data_schema_version: int = 1
    template_bundle_version: int = 6
    form_flow_integration_version: int = 1

    def model_dump(self) -> dict[str, Any]:
        return asdict(self)


VERSIONS = VersionContract()


class CompatibilityError(RuntimeError):
    pass


class MigrationRequiredError(CompatibilityError):
    pass


class DataTooNewError(CompatibilityError):
    pass


def check_schema_version(name: str, found: int, supported: int) -> None:
    if found > supported:
        raise DataTooNewError(
            f"{name} schema {found} is newer than supported schema {supported}; "
            "upgrade PaperFlow before reading or writing this data."
        )
    if found < supported:
        raise MigrationRequiredError(
            f"{name} schema {found} is older than required schema {supported}; "
            "run `paperflow migrate plan` and then `paperflow migrate apply`."
        )


def check_reader_version(minimum_reader_version: str) -> None:
    if Version(APPLICATION_VERSION) < Version(minimum_reader_version):
        raise DataTooNewError(
            f"Feed requires PaperFlow >= {minimum_reader_version}; "
            f"current application version is {APPLICATION_VERSION}."
        )
