from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Protocol

from .decision import ReleaseDecisionEngine
from .git import GitRepository, collect_release_evidence
from .models import ReleaseLevel, ReleaseResult
from .versioning import next_version, parse_version


class ReleaseStepError(RuntimeError):
    def __init__(self, step: str, message: str):
        super().__init__(message)
        self.step = step


class ReleaseActions(Protocol):
    def update_version(self, version: str) -> None: ...
    def run_tests(self) -> None: ...
    def commit_version(self, version: str) -> None: ...
    def build(self, version: str) -> tuple[str, ...]: ...
    def twine_check(self, artifacts: tuple[str, ...]) -> None: ...
    def install_verify(self, artifact: str) -> None: ...
    def push_branch(self) -> None: ...
    def upload(self, artifacts: tuple[str, ...]) -> None: ...
    def create_tag(self, version: str) -> None: ...
    def push_tag(self, version: str) -> None: ...
    def verify_remote(self, version: str, artifacts: tuple[str, ...]) -> None: ...


class ReleaseExecutor:
    """Run deterministic release steps and stop at the first failed gate."""

    def __init__(self, actions: ReleaseActions):
        self.actions = actions

    def execute(self, plan: ReleaseResult) -> ReleaseResult:
        if plan.status != "ready" or not plan.version:
            return ReleaseResult.failed(
                "INVALID_RELEASE_PLAN", "只能执行 ready 且包含版本号的发布计划"
            )

        completed: list[str] = []
        artifacts: tuple[str, ...] = ()
        steps = [
            ("update_version", lambda: self.actions.update_version(plan.version)),
            ("tests", self.actions.run_tests),
            ("commit", lambda: self.actions.commit_version(plan.version)),
            ("build", lambda: _set_artifacts()),
            ("twine_check", lambda: self.actions.twine_check(artifacts)),
            ("install_verify", lambda: self.actions.install_verify(_wheel(artifacts))),
            ("push_branch", self.actions.push_branch),
            ("upload", lambda: self.actions.upload(artifacts)),
            ("create_tag", lambda: self.actions.create_tag(plan.version)),
            ("push_tag", lambda: self.actions.push_tag(plan.version)),
            (
                "verify_remote",
                lambda: self.actions.verify_remote(plan.version, artifacts),
            ),
        ]

        def _set_artifacts() -> None:
            nonlocal artifacts
            artifacts = tuple(self.actions.build(plan.version))
            if len(artifacts) != 2:
                raise ReleaseStepError(
                    "build", "构建必须恰好产生本版本 wheel 和源码分发包"
                )

        for name, operation in steps:
            try:
                operation()
            except ReleaseStepError as error:
                return self._failed(plan, completed, error.step, str(error))
            except Exception as error:
                return self._failed(plan, completed, name, str(error))
            completed.append(name)
        return ReleaseResult.succeeded(
            plan.version,
            "发布完成，PyPI 文件、源码提交、版本 tag 和远端导入验证均通过",
            level=plan.level,
            target_commit=plan.target_commit,
            baseline_tag=plan.baseline_tag,
            completed_actions=tuple(completed),
            links=getattr(self.actions, "links", {}),
            remote_state=getattr(self.actions, "remote_state", {}),
        )

    def _failed(
        self,
        plan: ReleaseResult,
        completed: list[str],
        step: str,
        message: str,
    ) -> ReleaseResult:
        return ReleaseResult.failed(
            "RELEASE_STEP_FAILED",
            f"发布步骤 {step} 失败：{message}",
            version=plan.version,
            level=plan.level,
            target_commit=plan.target_commit,
            baseline_tag=plan.baseline_tag,
            completed_actions=tuple(completed),
            failed_step=step,
            links=getattr(self.actions, "links", {}),
            remote_state=getattr(self.actions, "remote_state", {}),
        )


def _wheel(artifacts: tuple[str, ...]) -> str:
    wheels = [path for path in artifacts if path.endswith(".whl")]
    if len(wheels) != 1:
        raise ReleaseStepError("install_verify", "构建产物中必须恰好有一个 wheel")
    return wheels[0]


class PyPIClient:
    def __init__(self, package: str = "lvren-jev", index_url: str = "https://pypi.org"):
        self.package = package
        self.index_url = index_url.rstrip("/")

    def metadata(self, version: str | None = None) -> dict[str, Any] | None:
        suffix = f"/{version}/json" if version else "/json"
        url = f"{self.index_url}/pypi/{self.package}{suffix}"
        try:
            with urllib.request.urlopen(url, timeout=20) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return None
            raise

    def has_version(self, version: str) -> bool:
        return self.metadata(version) is not None

    def verify_files(self, version: str, artifacts: tuple[str, ...]) -> None:
        metadata = self.metadata(version)
        if metadata is None:
            raise ReleaseStepError("verify_remote", "PyPI 上找不到刚上传的版本")
        by_name = {
            item["filename"]: item.get("digests", {}).get("sha256")
            for item in metadata.get("releases", {}).get(version, [])
        }
        for artifact in artifacts:
            path = Path(artifact)
            expected = by_name.get(path.name)
            if not expected:
                raise ReleaseStepError("verify_remote", f"PyPI 缺少文件 {path.name}")
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest != expected:
                raise ReleaseStepError("verify_remote", f"SHA256 不一致：{path.name}")


class SubprocessReleaseActions:
    """真实本地发布动作；token 只在 upload 步骤读入子进程环境。"""

    def __init__(
        self,
        repository: GitRepository,
        *,
        version_file: str | Path = "src/lvren_jev/_version.py",
        token_file: str | Path,
        package: str = "lvren-jev",
        pypi: PyPIClient | None = None,
        python: str = sys.executable,
    ) -> None:
        self.repository = repository
        self.version_file = repository.path / version_file
        self.token_file = Path(token_file)
        self.package = package
        self.pypi = pypi or PyPIClient(package)
        self.python = python
        self.remote_state: dict[str, Any] = {}
        self.links: dict[str, str] = {}
        self._build_dir: tempfile.TemporaryDirectory[str] | None = None

    def _run(self, step: str, args: list[str], *, env: dict[str, str] | None = None) -> str:
        completed = subprocess.run(
            args,
            cwd=self.repository.path,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip()
            raise ReleaseStepError(step, detail or f"exit code {completed.returncode}")
        return completed.stdout

    def update_version(self, version: str) -> None:
        text = self.version_file.read_text(encoding="utf-8")
        updated, count = re.subn(
            r'(?m)^(\s*__version__\s*=\s*["\'])[^"\']+(["\']\s*)$',
            rf"\g<1>{version}\g<2>",
            text,
        )
        if count != 1:
            raise ReleaseStepError("update_version", "无法唯一修改版本源 _version.py")
        self.version_file.write_text(updated, encoding="utf-8", newline="")

    def run_tests(self) -> None:
        self._run("tests", [self.python, "-m", "unittest", "discover", "-v"])

    def commit_version(self, version: str) -> None:
        relative = self.version_file.relative_to(self.repository.path).as_posix()
        self._run("commit", ["git", "add", "--", relative])
        self._run("commit", ["git", "commit", "-m", f"chore(release): prepare v{version}"])

    def build(self, version: str) -> tuple[str, ...]:
        self._build_dir = tempfile.TemporaryDirectory(prefix="lvren-jev-dist-")
        output = Path(self._build_dir.name)
        self._run(
            "build",
            [self.python, "-m", "build", "--sdist", "--wheel", "--outdir", str(output)],
        )
        artifacts = tuple(
            str(path)
            for path in sorted(output.iterdir())
            if path.is_file() and version in path.name and path.suffix in {".whl", ".gz"}
        )
        wheels = [path for path in artifacts if path.endswith(".whl")]
        sdists = [path for path in artifacts if path.endswith(".tar.gz")]
        if len(wheels) != 1 or len(sdists) != 1:
            raise ReleaseStepError("build", "未找到且仅找到本版本 wheel 与 sdist")
        return artifacts

    def twine_check(self, artifacts: tuple[str, ...]) -> None:
        self._run("twine_check", [self.python, "-m", "twine", "check", *artifacts])

    def install_verify(self, artifact: str) -> None:
        with tempfile.TemporaryDirectory(prefix="lvren-jev-install-") as directory:
            venv = Path(directory) / "venv"
            self._run("install_verify", [self.python, "-m", "venv", str(venv)])
            python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            self._run(
                "install_verify",
                [str(python), "-m", "pip", "install", "--no-deps", artifact],
            )
            self._run(
                "install_verify",
                [
                    str(python),
                    "-c",
                    f"import lvren_jev; assert lvren_jev.__version__ == '{_artifact_version(artifact)}'",
                ],
            )

    def push_branch(self) -> None:
        self._run("push_branch", ["git", "push", "origin", "HEAD"])
        self.remote_state["branch_pushed"] = True

    def upload(self, artifacts: tuple[str, ...]) -> None:
        if self.pypi.has_version(_artifact_version(artifacts[0])):
            raise ReleaseStepError("upload", "PyPI 已存在该版本，拒绝重复上传")
        token = self.token_file.read_text(encoding="utf-8").strip()
        if not token:
            raise ReleaseStepError("upload", "PyPI token 文件为空")
        env = os.environ.copy()
        env["TWINE_USERNAME"] = "__token__"
        env["TWINE_PASSWORD"] = token
        self._run("upload", [self.python, "-m", "twine", "upload", *artifacts], env=env)
        self.remote_state["pypi_uploaded"] = True

    def create_tag(self, version: str) -> None:
        self._run("create_tag", ["git", "tag", f"v{version}"])
        self.remote_state["tag_created"] = True

    def push_tag(self, version: str) -> None:
        self._run("push_tag", ["git", "push", "origin", f"v{version}"])
        self.remote_state["tag_pushed"] = True

    def verify_remote(self, version: str, artifacts: tuple[str, ...]) -> None:
        self.pypi.verify_files(version, artifacts)
        self.remote_state["pypi_sha256_verified"] = True
        with tempfile.TemporaryDirectory(prefix="lvren-jev-pypi-install-") as directory:
            venv = Path(directory) / "venv"
            self._run("verify_remote", [self.python, "-m", "venv", str(venv)])
            python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            self._run(
                "verify_remote",
                [
                    str(python),
                    "-m",
                    "pip",
                    "install",
                    "--index-url",
                    f"{self.pypi.index_url}/simple",
                    f"{self.package}=={version}",
                ],
            )
            self._run(
                "verify_remote",
                [
                    str(python),
                    "-c",
                    f"import lvren_jev; assert lvren_jev.__version__ == '{version}'",
                ],
            )
        self.remote_state["pypi_install_verified"] = True
        self.links["pypi"] = f"https://pypi.org/project/{self.package}/{version}/"
        remote = self.repository.remote_url()
        if remote:
            github = _github_url(remote)
            if github:
                self.links["github"] = github
                self.links["tag"] = f"{github}/releases/tag/v{version}"


def _artifact_version(path: str) -> str:
    match = re.search(r"-(\d+\.\d+\.\d+)(?:-|\.)", Path(path).name)
    if match is None:
        raise ReleaseStepError("upload", f"无法从构建产物名解析版本：{path}")
    return match.group(1)


def _github_url(remote: str) -> str | None:
    value = remote.strip()
    if value.startswith("git@github.com:"):
        value = "https://github.com/" + value.removeprefix("git@github.com:")
    if value.startswith("https://github.com/") or value.startswith("http://github.com/"):
        return value.removesuffix(".git")
    return None


def read_version(version_file: str | Path) -> str:
    text = Path(version_file).read_text(encoding="utf-8")
    match = re.search(r'(?m)^\s*__version__\s*=\s*["\']([^"\']+)["\']\s*$', text)
    if match is None:
        raise ValueError(f"version source does not contain __version__: {version_file}")
    return match.group(1)


class ReleasePlanner:
    def __init__(
        self,
        repository: GitRepository,
        decisions: ReleaseDecisionEngine,
        *,
        version_file: str | Path = "src/lvren_jev/_version.py",
        pypi: PyPIClient | None = None,
    ) -> None:
        self.repository = repository
        self.decisions = decisions
        self.version_file = repository.path / version_file
        self.pypi = pypi

    def plan(self, *, target: str = "HEAD", max_diff_bytes: int = 2_000_000) -> ReleaseResult:
        evidence = collect_release_evidence(
            self.repository, target=target, max_diff_bytes=max_diff_bytes
        )
        decision = self.decisions.assess(evidence)
        if decision.status != "ready" or decision.level is None:
            return decision
        try:
            current = read_version(self.version_file)
            baseline = (evidence.baseline_tag or "").removeprefix("v")
            expected = next_version(baseline, decision.level)
            if current == baseline:
                version = expected
            elif current == expected:
                # A prior local release preparation already made the exact
                # deterministic change; do not increment it a second time.
                version = current
            else:
                parse_version(current)
                return ReleaseResult.rejected(
                    "VERSION_SOURCE_MISMATCH",
                    f"_version.py 为 {current}，但基于基线 {baseline} 的预期版本为 {expected}",
                    target_commit=evidence.target_commit,
                    baseline_tag=evidence.baseline_tag,
                    level=decision.level,
                )
        except (OSError, ValueError) as error:
            return ReleaseResult.rejected("INVALID_VERSION_SOURCE", str(error))
        if any(
            tag.name in {f"v{version}", version}
            for tag in self.repository.all_version_tags()
        ):
            return ReleaseResult.rejected(
                "VERSION_ALREADY_TAGGED",
                f"Git 已存在版本 {version} 的发布 tag",
                target_commit=evidence.target_commit,
                baseline_tag=evidence.baseline_tag,
                level=decision.level,
            )
        if self.pypi is not None:
            try:
                if self.pypi.has_version(version):
                    return ReleaseResult.rejected(
                        "VERSION_ALREADY_PUBLISHED",
                        f"PyPI 已存在版本 {version}，拒绝复用",
                        target_commit=evidence.target_commit,
                        baseline_tag=evidence.baseline_tag,
                        level=decision.level,
                    )
            except Exception as error:
                return ReleaseResult.failed("PYPI_CHECK_FAILED", str(error))
        return ReleaseResult.ready_result(
            version=version,
            level=decision.level,
            message=f"发布计划就绪：{current} -> {version}",
            target_commit=evidence.target_commit,
            baseline_tag=evidence.baseline_tag,
            observations=decision.observations,
        )
