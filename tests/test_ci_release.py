"""The release path in ci.yml: a pushed version tag drafts, builds and publishes.

Until 3.10.0 the build jobs listened only for `release: published`, so pushing a
tag on its own built nothing. These tests hold the tag-driven path in place.
They read the workflow as text, like test_macos_packaging.py: the project does
not depend on a YAML parser.
"""

from __future__ import annotations

from pathlib import Path

CI_WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml"


def _workflow() -> str:
    return CI_WORKFLOW.read_text()


def _triggers() -> str:
    workflow = _workflow()
    return workflow[workflow.index("on:\n") : workflow.index("\nenv:\n")]


def _job(job: str, next_job: str | None = None) -> str:
    workflow = _workflow()
    start = workflow.index(f"\n  {job}:\n")
    if next_job is None:
        return workflow[start:]
    return workflow[start : workflow.index(f"\n  {next_job}:\n", start)]


def test_a_version_tag_push_runs_the_workflow() -> None:
    triggers = _triggers()

    assert "    tags: [ 'v*' ]\n" in triggers
    assert "  workflow_dispatch:\n" in triggers
    # A published release would build a second time on top of the tag push.
    assert "\n  release:\n" not in triggers


def test_the_release_tag_is_the_tag_the_run_is_on() -> None:
    assert "  FPDB_RELEASE_TAG: ${{ startsWith(github.ref, 'refs/tags/v') && github.ref_name || '' }}\n" in _workflow()


def test_a_tag_drafts_its_release_with_the_release_notes() -> None:
    job = _job("release", "build")

    assert "    if: startsWith(github.ref, 'refs/tags/v')\n" in job
    assert "      contents: write\n" in job
    assert 'gh release view "$FPDB_RELEASE_TAG"' in job
    assert "--draft --verify-tag" in job
    assert 'notes="docs/RELEASE_NOTES_${version}.md"' in job
    assert "--notes-file" in job
    assert "--prerelease" in job
    assert 'echo "drafted=true" >> "$GITHUB_OUTPUT"' in job


def test_both_builds_run_on_a_tag_or_by_hand_after_the_draft() -> None:
    # `release` is skipped on a branch; without a status check the builds
    # would be skipped with it on a workflow_dispatch.
    condition = (
        "    if: ${{ !cancelled() && !failure() && (startsWith(github.ref, 'refs/tags/v') "
        "|| github.event_name == 'workflow_dispatch') }}\n"
    )
    for job in (_job("build", "build-pyoxidizer"), _job("build-pyoxidizer", "publish-release")):
        assert "    needs: release\n" in job
        assert condition in job
        assert "          RELEASE_TAG: ${{ env.FPDB_RELEASE_TAG }}\n" in job
        assert 'gh release upload "$RELEASE_TAG"' in job


def test_only_a_drafted_release_is_published_and_only_once_everything_passed() -> None:
    job = _job("publish-release")

    assert "    needs: [ release, build, build-pyoxidizer, quality, test ]\n" in job
    assert "    if: needs.release.outputs.drafted == 'true'\n" in job
    assert "--draft=false" in job


def test_nothing_still_waits_for_a_release_event() -> None:
    workflow = _workflow()

    assert "github.event_name == 'release'" not in workflow
    assert "github.event.release" not in workflow
