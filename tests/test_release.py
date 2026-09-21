import hashlib
import tempfile
import unittest
from pathlib import Path

from lvren_jev.release import (
    ReleaseDecisionEngine,
    ReleaseLevel,
    ReleaseResult,
    collect_release_evidence,
    next_version,
)
from lvren_jev.release.git import GitRepository
from lvren_jev.release.publisher import ReleaseExecutor, ReleaseStepError
from lvren_jev.release.publisher import ReleasePlanner


def git(repo: Path, *args: str) -> str:
    import subprocess

    completed = subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    )
    return completed.stdout.strip()


def make_repo(*, with_release_tag: bool = True) -> Path:
    path = Path(tempfile.mkdtemp(prefix="lvren-jev-release-"))
    git(path, "init", "-q")
    git(path, "config", "user.email", "test@example.invalid")
    git(path, "config", "user.name", "Release Test")
    (path / "src.txt").write_text("before\n", encoding="utf-8")
    git(path, "add", ".")
    git(path, "commit", "-qm", "feat: initial release")
    if with_release_tag:
        git(path, "tag", "v1.2.3")
    (path / "src.txt").write_text("before\nafter\n", encoding="utf-8")
    git(path, "add", ".")
    git(
        path,
        "commit",
        "-qm",
        "feat(api): add export endpoint\n\nAdds a backward-compatible endpoint for exports.",
    )
    return path


class FakeRuntime:
    def __init__(self, answers):
        self.answers = list(answers)
        self.requests = []

    def execute(self, request):
        self.requests.append(request)
        return {"answers": {"release_decision": self.answers.pop(0)}}


class ReleaseEvidenceTests(unittest.TestCase):
    def test_collects_commit_body_and_full_diff_from_latest_version_tag(self):
        repo = make_repo()
        evidence = collect_release_evidence(GitRepository(repo))

        self.assertTrue(evidence.ready)
        self.assertEqual(evidence.baseline_tag, "v1.2.3")
        self.assertIn("Adds a backward-compatible endpoint", evidence.commits[0].body)
        self.assertIn("+after", evidence.diff)
        self.assertEqual(
            evidence.diff_sha256,
            hashlib.sha256(evidence.diff.encode("utf-8")).hexdigest(),
        )

    def test_non_version_tags_do_not_become_release_baseline(self):
        repo = make_repo(with_release_tag=False)
        git(repo, "tag", "internal-test")

        result = collect_release_evidence(GitRepository(repo))

        self.assertFalse(result.ready)
        self.assertEqual(result.code, "NO_RELEASE_TAG")

    def test_dirty_worktree_is_rejected_before_semantic_decisions(self):
        repo = make_repo()
        (repo / "uncommitted.txt").write_text("dirty\n", encoding="utf-8")

        result = collect_release_evidence(GitRepository(repo))

        self.assertFalse(result.ready)
        self.assertEqual(result.code, "DIRTY_WORKTREE")

    def test_large_diff_is_reported_as_insufficient_evidence_without_truncation(self):
        repo = make_repo()
        result = collect_release_evidence(GitRepository(repo), max_diff_bytes=1)

        self.assertFalse(result.ready)
        self.assertEqual(result.code, "EVIDENCE_TOO_LARGE")

    def test_targeting_the_release_commit_is_reported_as_no_changes(self):
        repo = make_repo()
        result = collect_release_evidence(
            GitRepository(repo), target=git(repo, "rev-parse", "v1.2.3")
        )

        self.assertFalse(result.ready)
        self.assertEqual(result.code, "NO_CHANGES")


class ReleaseDecisionTests(unittest.TestCase):
    def test_rejected_suitability_does_not_request_version_decision(self):
        repo = make_repo()
        evidence = collect_release_evidence(GitRepository(repo))
        runtime = FakeRuntime([{"choice": "reject", "confidence": 0.99}])

        result = ReleaseDecisionEngine(runtime=runtime).assess(evidence)

        self.assertEqual(result.status, "rejected")
        self.assertEqual(result.code, "SEMANTIC_REJECTED")
        self.assertEqual(len(runtime.requests), 1)

    def test_uncertain_suitability_is_not_treated_as_publishable(self):
        repo = make_repo()
        evidence = collect_release_evidence(GitRepository(repo))
        runtime = FakeRuntime([{"choice": "publish", "confidence": 0.1}])

        result = ReleaseDecisionEngine(runtime=runtime).assess(evidence)

        self.assertEqual(result.status, "rejected")
        self.assertEqual(result.code, "SEMANTIC_UNCERTAIN")

    def test_highest_level_from_separate_changes_is_merged_by_program_logic(self):
        repo = make_repo()
        evidence = collect_release_evidence(GitRepository(repo))
        runtime = FakeRuntime(
            [
                {"choice": "publish", "confidence": 0.99},
                {"choice": "patch", "confidence": 0.99},
            ]
        )
        result = ReleaseDecisionEngine(runtime=runtime).assess(evidence)

        self.assertEqual(result.status, "ready")
        self.assertEqual(result.level, ReleaseLevel.PATCH)
        self.assertEqual(len(runtime.requests), 2)

    def test_ambiguous_change_stops_the_whole_release(self):
        repo = make_repo()
        evidence = collect_release_evidence(GitRepository(repo))
        runtime = FakeRuntime(
            [
                {"choice": "publish", "confidence": 0.99},
                {"choice": "pending_review", "confidence": 0.1},
            ]
        )

        result = ReleaseDecisionEngine(runtime=runtime).assess(evidence)

        self.assertEqual(result.status, "rejected")
        self.assertEqual(result.code, "SEMANTIC_UNCERTAIN")


class VersionTests(unittest.TestCase):
    def test_next_version_uses_semver_and_resets_lower_components(self):
        self.assertEqual(next_version("1.2.3", ReleaseLevel.PATCH), "1.2.4")
        self.assertEqual(next_version("1.2.3", ReleaseLevel.MINOR), "1.3.0")
        self.assertEqual(next_version("1.2.3", ReleaseLevel.MAJOR), "2.0.0")


class ReleaseResultTests(unittest.TestCase):
    def test_result_is_structured_for_machine_consumption(self):
        result = ReleaseResult.rejected("NO_CHANGES", "没有待发布变更")

        payload = result.to_dict()

        self.assertEqual(payload["status"], "rejected")
        self.assertEqual(payload["code"], "NO_CHANGES")
        self.assertIn("message", payload)


class FakeActions:
    def __init__(self, fail_at=None):
        self.fail_at = fail_at
        self.calls = []
        self.remote_state = {}

    def call(self, name):
        self.calls.append(name)
        if name == "upload":
            self.remote_state["pypi_uploaded"] = True
        if name == "create_tag":
            self.remote_state["tag_created"] = True
        if name == self.fail_at:
            raise ReleaseStepError(name, f"fake failure at {name}")

    def update_version(self, version):
        self.call("update_version")

    def run_tests(self):
        self.call("tests")

    def commit_version(self, version):
        self.call("commit")

    def build(self, version):
        self.call("build")
        return ("dist/lvren_jev-1.2.4-py3-none-any.whl", "dist/lvren-jev-1.2.4.tar.gz")

    def twine_check(self, artifacts):
        self.call("twine_check")

    def install_verify(self, artifact):
        self.call("install_verify")

    def push_branch(self):
        self.call("push_branch")

    def upload(self, artifacts):
        self.call("upload")

    def create_tag(self, version):
        self.call("create_tag")

    def push_tag(self, version):
        self.call("push_tag")

    def verify_remote(self, version, artifacts):
        self.call("verify_remote")


class ReleaseExecutionTests(unittest.TestCase):
    def _plan(self):
        return ReleaseResult.ready_result(
            version="1.2.4",
            level=ReleaseLevel.PATCH,
            message="ready",
            target_commit="target",
            baseline_tag="v1.2.3",
        )

    def test_build_failure_stops_before_upload_and_reports_completed_actions(self):
        actions = FakeActions(fail_at="build")

        result = ReleaseExecutor(actions).execute(self._plan())

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.failed_step, "build")
        self.assertEqual(
            result.completed_actions,
            ("update_version", "tests", "commit"),
        )
        self.assertNotIn("upload", actions.calls)
        self.assertNotIn("create_tag", actions.calls)

    def test_success_runs_tag_and_remote_verification_after_upload(self):
        actions = FakeActions()

        result = ReleaseExecutor(actions).execute(self._plan())

        self.assertEqual(result.status, "succeeded")
        self.assertEqual(result.version, "1.2.4")
        self.assertEqual(actions.calls[-3:], ["create_tag", "push_tag", "verify_remote"])

    def test_tag_push_failure_reports_partial_remote_state(self):
        actions = FakeActions(fail_at="push_tag")

        result = ReleaseExecutor(actions).execute(self._plan())

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.failed_step, "push_tag")
        self.assertEqual(result.remote_state["pypi_uploaded"], True)
        self.assertEqual(result.remote_state["tag_created"], True)
        self.assertNotIn("verify_remote", actions.calls)


class ReleasePlannerTests(unittest.TestCase):
    def test_existing_tag_for_computed_version_is_rejected_before_mutation(self):
        repo = make_repo()
        main_branch = git(repo, "branch", "--show-current")
        baseline = git(repo, "rev-parse", "v1.2.3")
        git(repo, "switch", "-qc", "side-release", baseline)
        (repo / "side.txt").write_text("side\n", encoding="utf-8")
        git(repo, "add", "side.txt")
        git(repo, "commit", "-qm", "chore: unrelated future")
        git(repo, "tag", "v1.2.4")
        git(repo, "switch", main_branch)
        (repo / "src/lvren_jev").mkdir(parents=True)
        (repo / "src/lvren_jev/_version.py").write_text(
            '__version__ = "1.2.3"\n', encoding="utf-8"
        )
        git(repo, "add", ".")
        git(repo, "commit", "-qm", "chore: add version source")
        runtime = FakeRuntime(
            [
                {"choice": "publish", "confidence": 0.99},
                {"choice": "patch", "confidence": 0.99},
                {"choice": "patch", "confidence": 0.99},
            ]
        )

        result = ReleasePlanner(
            GitRepository(repo), ReleaseDecisionEngine(runtime=runtime)
        ).plan()

        self.assertEqual(result.status, "rejected")
        self.assertEqual(result.code, "VERSION_ALREADY_TAGGED")

    def test_already_prepared_expected_version_is_not_incremented_again(self):
        repo = make_repo()
        (repo / "src/lvren_jev").mkdir(parents=True)
        (repo / "src/lvren_jev/_version.py").write_text(
            '__version__ = "1.2.4"\n', encoding="utf-8"
        )
        git(repo, "add", ".")
        git(repo, "commit", "-qm", "chore(release): prepare v1.2.4")
        runtime = FakeRuntime(
            [
                {"choice": "publish", "confidence": 0.99},
                {"choice": "patch", "confidence": 0.99},
                {"choice": "patch", "confidence": 0.99},
            ]
        )

        result = ReleasePlanner(
            GitRepository(repo), ReleaseDecisionEngine(runtime=runtime)
        ).plan()

        self.assertEqual(result.status, "ready")
        self.assertEqual(result.version, "1.2.4")


if __name__ == "__main__":
    unittest.main()
