from __future__ import annotations

import pytest
from typer.testing import CliRunner

from paperflow.versioning import (
    APPLICATION_VERSION,
    DataTooNewError,
    MigrationRequiredError,
    VERSIONS,
    check_reader_version,
    check_schema_version,
)


def test_version_contract_is_explicit_and_independent() -> None:
    assert APPLICATION_VERSION == "1.3.1"
    assert VERSIONS.workspace_schema_version == 1
    assert VERSIONS.raw_data_schema_version == 1
    assert VERSIONS.ai_analysis_schema_version == 1
    assert VERSIONS.user_data_schema_version == 1
    assert VERSIONS.public_feed_schema_version == 1
    assert VERSIONS.template_bundle_version == 2
    assert VERSIONS.form_flow_integration_version == 1


def test_schema_compatibility_requires_migration_or_upgrade() -> None:
    check_schema_version("raw", 1, 1)
    with pytest.raises(MigrationRequiredError):
        check_schema_version("raw", 0, 1)
    with pytest.raises(DataTooNewError):
        check_schema_version("raw", 2, 1)


def test_minimum_reader_version_is_enforced() -> None:
    check_reader_version("1.0.0")
    with pytest.raises(DataTooNewError):
        check_reader_version("999.0.0")


def test_cli_exposes_application_version() -> None:
    from paperflow.cli import app

    result = CliRunner().invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == "1.3.1"


def test_cli_does_not_offer_windows_scheduler_install_or_run() -> None:
    from paperflow.cli import app

    result = CliRunner().invoke(app, ["schedule", "--help"])
    assert result.exit_code == 0
    assert "status" in result.stdout
    assert "uninstall" in result.stdout
    assert "run-now" not in result.stdout
    assert " install " not in result.stdout

    refused = CliRunner().invoke(app, ["schedule", "install"])
    assert refused.exit_code == 2
    assert "安装已停用" in refused.stderr
