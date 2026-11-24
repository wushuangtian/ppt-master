#!/usr/bin/env python3
"""将生成完成的 PPT 发布到唯一允许的 GitHub 结果仓库。"""

from __future__ import annotations

import base64
import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

REPO_OWNER = "wushuangtian"
REPO_NAME = "results"
REPO_URL = f"https://github.com/{REPO_OWNER}/{REPO_NAME}.git"
DEFAULT_BRANCH = "main"
MAX_FILE_BYTES = 50 * 1024 * 1024

_API_ROOT = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}"


class PublishError(RuntimeError):
    """发布失败，调用方可以据此返回非零退出码。"""


@dataclass(frozen=True)
class PublishResult:
    repo_url: str
    branch: str
    repo_path: str
    public_url: str
    commit_sha: str
    sha256: str
    size_bytes: int
    public_repo: bool
    overwrote_existing: bool


def _workspace_output_root() -> Path:
    workspace = Path("/workspace") if Path("/workspace").is_dir() else Path.cwd()
    return (workspace / "outputs").resolve()


def _load_requests():
    try:
        import requests
    except ModuleNotFoundError as exc:
        raise PublishError(
            "缺少 requests 依赖；请管理员在沙箱镜像中预装 requests。"
        ) from exc
    return requests


def _github_token() -> str:
    token = os.environ.get("PPT_GITHUB_TOKEN", "").strip()
    if not token:
        raise PublishError(
            "未配置 PPT_GITHUB_TOKEN。请使用仅授权 "
            f"{REPO_OWNER}/{REPO_NAME} Contents: Read and write 权限的 fine-grained PAT。"
        )
    return token


def validate_publish_config() -> None:
    """在生成前快速检查配置，避免生成完成后才发现无法发布。"""
    _github_token()
    if not Path("/workspace").is_dir() and not Path.cwd().is_dir():
        raise PublishError("无法确定工作区输出目录。")


def _validate_source(output_path: str | Path) -> tuple[Path, bytes, str]:
    try:
        source = Path(output_path).resolve(strict=True)
    except FileNotFoundError as exc:
        raise PublishError(f"待发布文件不存在：{output_path}") from exc

    if not source.is_file():
        raise PublishError(f"待发布路径不是文件：{source}")
    if source.suffix.lower() != ".pptx":
        raise PublishError("仅允许发布 .pptx 文件。")

    allowed_root = _workspace_output_root()
    if not source.is_relative_to(allowed_root):
        raise PublishError(f"仅允许发布工作区 outputs/ 下的文件：{allowed_root}")

    size = source.stat().st_size
    if size == 0:
        raise PublishError("待发布 PPT 是空文件。")
    if size > MAX_FILE_BYTES:
        raise PublishError(
            f"文件过大：{size} bytes；安全上限为 {MAX_FILE_BYTES} bytes。"
        )

    content = source.read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    return source, content, digest


def _validate_branch(branch: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,119}", branch):
        raise PublishError(f"非法分支名：{branch!r}")


def _error_message(response, action: str) -> str:
    try:
        message = str(response.json().get("message", "")).strip()
    except (ValueError, AttributeError):
        message = ""
    detail = f"：{message[:300]}" if message else ""
    return f"{action}失败，HTTP {response.status_code}{detail}"


def _create_initial_file(
    session,
    *,
    repo_path: str,
    encoded_content: str,
    message: str,
    branch: str,
) -> tuple[str, bool]:
    """在空仓库中通过 Git Data API 创建首个 main 分支提交。"""

    blob_response = session.post(
        f"{_API_ROOT}/git/blobs",
        json={"content": encoded_content, "encoding": "base64"},
        timeout=(15, 120),
        allow_redirects=False,
    )
    if blob_response.status_code != 201 or not blob_response.json().get("sha"):
        raise PublishError(_error_message(blob_response, "创建初始文件 Blob"))
    blob_sha = str(blob_response.json()["sha"])

    tree_response = session.post(
        f"{_API_ROOT}/git/trees",
        json={
            "tree": [
                {
                    "path": repo_path,
                    "mode": "100644",
                    "type": "blob",
                    "sha": blob_sha,
                }
            ]
        },
        timeout=(15, 60),
        allow_redirects=False,
    )
    if tree_response.status_code != 201 or not tree_response.json().get("sha"):
        raise PublishError(_error_message(tree_response, "创建初始文件 Tree"))
    tree_sha = str(tree_response.json()["sha"])

    commit_response = session.post(
        f"{_API_ROOT}/git/commits",
        json={"message": message, "tree": tree_sha, "parents": []},
        timeout=(15, 60),
        allow_redirects=False,
    )
    if commit_response.status_code != 201 or not commit_response.json().get("sha"):
        raise PublishError(_error_message(commit_response, "创建初始文件 Commit"))
    commit_sha = str(commit_response.json()["sha"])

    ref_response = session.post(
        f"{_API_ROOT}/git/refs",
        json={"ref": f"refs/heads/{branch}", "sha": commit_sha},
        timeout=(15, 60),
        allow_redirects=False,
    )
    if ref_response.status_code != 201:
        raise PublishError(_error_message(ref_response, "创建初始分支"))
    return commit_sha, True


def publish_ppt(
    output_path: str | Path,
    *,
    branch: str = DEFAULT_BRANCH,
    confirm_public: bool = False,
) -> PublishResult:
    """
    将 PPT 发布到固定 GitHub 仓库。

    目标仓库目前是 public。调用方必须显式传入 confirm_public=True。
    远端路径使用本地 PPT 的真实文件名；同名文件会被强制替换，Git 历史仍然保留。
    """

    if not confirm_public:
        raise PublishError("目标仓库为 public，必须显式确认后再发布。")

    _validate_branch(branch)
    source, content, digest = _validate_source(output_path)
    token = _github_token()
    requests = _load_requests()

    session = requests.Session()
    session.headers.update(
        {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "ppt-generator-skill/1.0.4",
            "X-GitHub-Api-Version": "2022-11-28",
        }
    )

    try:
        repo_response = session.get(
            _API_ROOT,
            timeout=(10, 30),
            allow_redirects=False,
        )
        if repo_response.status_code != 200:
            raise PublishError(_error_message(repo_response, "读取目标仓库"))
        repo_data = repo_response.json()
        full_name = str(repo_data.get("full_name", ""))
        if full_name.lower() != f"{REPO_OWNER}/{REPO_NAME}".lower():
            raise PublishError(
                f"仓库身份不匹配，拒绝发布：期望 {REPO_OWNER}/{REPO_NAME}，实际 {full_name!r}"
            )

        public_repo = not bool(repo_data.get("private", False))
        repo_path = f"ppt-results/{source.name}"
        endpoint = f"{_API_ROOT}/contents/{quote(repo_path, safe='/')}"
        encoded_content = base64.b64encode(content).decode("ascii")
        overwrote_existing = False
        commit_sha = ""

        for attempt in range(3):
            existing_response = session.get(
                endpoint,
                params={"ref": branch},
                timeout=(10, 30),
                allow_redirects=False,
            )
            payload = {
                "message": f"Publish or replace {source.name} ({digest[:12]})",
                "content": encoded_content,
                "branch": branch,
            }
            overwrote_existing = existing_response.status_code == 200
            if existing_response.status_code == 200:
                existing_data = existing_response.json()
                if not isinstance(existing_data, dict) or not existing_data.get("sha"):
                    raise PublishError("远端同名 PPT 返回了无法识别的文件信息。")
                payload["sha"] = existing_data["sha"]
            elif existing_response.status_code != 404:
                raise PublishError(_error_message(existing_response, "读取远端同名 PPT"))

            upload_response = session.put(
                endpoint,
                json=payload,
                timeout=(15, 120),
                allow_redirects=False,
            )
            if upload_response.status_code in (200, 201):
                break
            if upload_response.status_code == 404 and existing_response.status_code == 404:
                commit_sha, _initialized = _create_initial_file(
                    session,
                    repo_path=repo_path,
                    encoded_content=encoded_content,
                    message=payload["message"],
                    branch=branch,
                )
                break
            if upload_response.status_code == 409 and attempt < 2:
                continue
            raise PublishError(_error_message(upload_response, "强制替换远端同名 PPT"))
        else:
            raise PublishError("远端同名 PPT 连续发生更新冲突，强制替换失败。")

        if not commit_sha:
            upload_data = upload_response.json()
            commit_sha = str(upload_data.get("commit", {}).get("sha", ""))
        if not re.fullmatch(r"[0-9a-f]{40}", commit_sha):
            raise PublishError("GitHub 返回结果缺少有效 Commit SHA。")
    except PublishError:
        raise
    except Exception as exc:
        raise PublishError(f"GitHub 发布请求失败：{type(exc).__name__}: {exc}") from exc
    finally:
        session.close()

    public_url = (
        f"https://github.com/{REPO_OWNER}/{REPO_NAME}/blob/"
        f"{quote(branch, safe='/')}/{quote(repo_path, safe='/')}"
    )
    return PublishResult(
        repo_url=REPO_URL,
        branch=branch,
        repo_path=repo_path,
        public_url=public_url,
        commit_sha=commit_sha,
        sha256=digest,
        size_bytes=len(content),
        public_repo=public_repo,
        overwrote_existing=overwrote_existing,
    )
