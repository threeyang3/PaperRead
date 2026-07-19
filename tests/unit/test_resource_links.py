from __future__ import annotations

from paperflow.pipeline.resources import find_resource_links


def test_resource_links_reject_generic_and_reference_only_repositories() -> None:
    text = """
    Project page: https://openvla.github.io

    REFERENCES
    An unrelated deployment library is at
    https://github.com/NVIDIA/TensorRT-LLM.
    """

    result = find_resource_links(text)

    assert result["paper_project_url"] == "https://openvla.github.io"
    assert result["paper_code_url"] == ""
    assert result["paper_dataset_url"] == ""


def test_resource_links_accept_specific_repository_before_references() -> None:
    text = """
    Code and trained models are available at
    https://github.com/openvla/openvla.

    REFERENCES
    """

    result = find_resource_links(text)

    assert result["paper_code_url"] == "https://github.com/openvla/openvla"


def test_resource_links_reject_bare_github_homepage() -> None:
    result = find_resource_links("Code and dataset: https://github.com/")

    assert result["paper_code_url"] == ""
    assert result["paper_dataset_url"] == ""


def test_resource_links_accept_dataset_before_references() -> None:
    result = find_resource_links(
        "The dataset is available at https://example.org/data.\n\nREFERENCES\n"
    )

    assert result["paper_dataset_url"] == "https://example.org/data"
