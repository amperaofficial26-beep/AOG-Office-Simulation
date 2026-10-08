"""Integrasi GitHub: repo, commit, file, issue, dan PR — semuanya live via REST API.

Memakai urllib supaya tidak menambah dependensi. Semua hasil di-cache sebentar
(CACHE_TTL detik) agar tidak menembak rate limit GitHub saat Streamlit rerun.
"""
from __future__ import annotations

import base64
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .config import CACHE_TTL, get_key
from .state import load_cache, save_cache

API = "https://api.github.com"


class GitHubError(RuntimeError):
    pass


def token() -> str:
    return get_key("github")


def has_token() -> bool:
    return bool(token())


def _get(path: str, use_cache: bool = True, accept: str = "application/vnd.github+json") -> Any:
    key = f"gh::{path}"
    if use_cache:
        cached = load_cache(key, ttl=CACHE_TTL)
        if cached is not None:
            return cached
    url = path if path.startswith("http") else f"{API}{path}"
    headers = {
        "Accept": accept,
        "User-Agent": "AOG-Virtual-Office",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token():
        headers["Authorization"] = f"Bearer {token()}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
            payload = json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:  # pragma: no cover - bergantung jaringan
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise GitHubError(f"GitHub HTTP {exc.code} untuk {url} — {detail}") from exc
    except Exception as exc:  # pragma: no cover - bergantung jaringan
        raise GitHubError(f"{type(exc).__name__}: {exc}") from exc
    if use_cache:
        save_cache(key, payload, ttl=CACHE_TTL)
    return payload


# ----------------------------------------------------------------------------- repo
def list_repos(owner: str, limit: int = 100) -> list[dict[str, Any]]:
    rows = _get(f"/users/{owner}/repos?per_page={min(limit, 100)}&sort=updated")
    out = []
    for row in rows if isinstance(rows, list) else []:
        out.append(
            {
                "name": row.get("name", ""),
                "full_name": row.get("full_name", ""),
                "description": row.get("description") or "",
                "language": row.get("language") or "-",
                "stars": row.get("stargazers_count", 0),
                "forks": row.get("forks_count", 0),
                "open_issues": row.get("open_issues_count", 0),
                "updated_at": row.get("updated_at", ""),
                "pushed_at": row.get("pushed_at", ""),
                "default_branch": row.get("default_branch", "main"),
                "html_url": row.get("html_url", ""),
                "size_kb": row.get("size", 0),
                "archived": bool(row.get("archived")),
            }
        )
    return out


def repo_detail(owner: str, repo: str) -> dict[str, Any]:
    row = _get(f"/repos/{owner}/{repo}")
    return {
        "name": row.get("name", repo),
        "full_name": row.get("full_name", f"{owner}/{repo}"),
        "default_branch": row.get("default_branch", "main"),
        "language": row.get("language") or "-",
        "stars": row.get("stargazers_count", 0),
        "open_issues": row.get("open_issues_count", 0),
        "pushed_at": row.get("pushed_at", ""),
        "html_url": row.get("html_url", ""),
        "topics": row.get("topics", []),
    }


def commits(owner: str, repo: str, limit: int = 10, branch: str = "") -> list[dict[str, Any]]:
    qs = f"?per_page={limit}" + (f"&sha={urllib.parse.quote(branch)}" if branch else "")
    rows = _get(f"/repos/{owner}/{repo}/commits{qs}")
    out = []
    for row in rows if isinstance(rows, list) else []:
        commit = row.get("commit") or {}
        author = commit.get("author") or {}
        out.append(
            {
                "sha": (row.get("sha") or "")[:7],
                "message": (commit.get("message") or "").splitlines()[0][:120],
                "author": author.get("name") or (row.get("author") or {}).get("login", "-"),
                "date": author.get("date", ""),
                "url": row.get("html_url", ""),
            }
        )
    return out


def file_tree(owner: str, repo: str, branch: str = "", limit: int = 300) -> list[dict[str, str]]:
    ref = f"/repos/{owner}/{repo}/git/trees/{urllib.parse.quote(branch)}?recursive=1" if branch else (
        f"/repos/{owner}/{repo}/git/trees/HEAD?recursive=1"
    )
    data = _get(ref)
    rows = data.get("tree", []) if isinstance(data, dict) else []
    out = []
    for row in rows[:limit]:
        if row.get("type") != "blob":
            continue
        out.append({"path": row.get("path", ""), "size": int(row.get("size") or 0)})
    return out


def read_file(owner: str, repo: str, path: str, branch: str = "") -> str:
    ref = f"?ref={urllib.parse.quote(branch)}" if branch else ""
    data = _get(f"/repos/{owner}/{repo}/contents/{urllib.parse.quote(path)}{ref}")
    if isinstance(data, dict) and data.get("content"):
        try:
            return base64.b64decode(data["content"]).decode("utf-8", errors="replace")
        except Exception:  # pragma: no cover
            return ""
    return ""


def issues(owner: str, repo: str, limit: int = 10) -> list[dict[str, Any]]:
    rows = _get(f"/repos/{owner}/{repo}/issues?state=open&per_page={limit}")
    return [
        {
            "number": row.get("number"),
            "title": row.get("title", ""),
            "labels": [l.get("name", "") for l in row.get("labels", [])],
            "url": row.get("html_url", ""),
            "is_pr": "pull_request" in row,
            "updated_at": row.get("updated_at", ""),
        }
        for row in (rows if isinstance(rows, list) else [])
    ]


def pull_requests(owner: str, repo: str, limit: int = 10) -> list[dict[str, Any]]:
    rows = _get(f"/repos/{owner}/{repo}/pulls?state=open&per_page={limit}")
    return [
        {
            "number": row.get("number"),
            "title": row.get("title", ""),
            "author": (row.get("user") or {}).get("login", "-"),
            "url": row.get("html_url", ""),
            "updated_at": row.get("updated_at", ""),
        }
        for row in (rows if isinstance(rows, list) else [])
    ]


def languages(owner: str, repo: str) -> dict[str, int]:
    data = _get(f"/repos/{owner}/{repo}/languages")
    return data if isinstance(data, dict) else {}


def create_issue(owner: str, repo: str, title: str, body: str, labels: list[str] | None = None) -> dict[str, Any]:
    """Tulis nyata ke repo: membuat issue (butuh token dengan izin repo)."""
    if not token():
        raise GitHubError("GITHUB_TOKEN belum diisi di Secrets, tidak bisa menulis ke GitHub.")
    payload = json.dumps({"title": title, "body": body, "labels": labels or []}).encode()
    req = urllib.request.Request(
        f"{API}/repos/{owner}/{repo}/issues",
        data=payload,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token()}",
            "User-Agent": "AOG-Virtual-Office",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
            data = json.loads(resp.read().decode())
        from .state import clear_cache

        clear_cache("gh::")
        return data
    except urllib.error.HTTPError as exc:  # pragma: no cover
        raise GitHubError(f"GitHub HTTP {exc.code}: {exc.read().decode()[:300]}") from exc


# ----------------------------------------------------------------------------- konteks
def build_context(
    owner: str,
    repo: str,
    *,
    branch: str = "",
    include_files: list[str] | None = None,
    max_chars: int = 6000,
) -> str:
    """Susun konteks repo untuk disuntikkan ke prompt karyawan."""
    parts: list[str] = []
    try:
        detail = repo_detail(owner, repo)
        parts.append(
            f"REPO: {detail['full_name']} | bahasa utama: {detail['language']} | "
            f"branch: {detail['default_branch']} | issue terbuka: {detail['open_issues']}"
        )
    except GitHubError as exc:
        return f"(konteks repo tidak tersedia: {exc})"

    try:
        recent = commits(owner, repo, limit=6, branch=branch or detail["default_branch"])
        if recent:
            parts.append("COMMIT TERAKHIR:")
            parts += [f"- {c['sha']} {c['message']} ({c['author']})" for c in recent]
    except GitHubError:
        pass

    try:
        tree = file_tree(owner, repo, branch or detail["default_branch"], limit=200)
        names = [f"{t['path']} ({t['size']}B)" for t in tree[:40]]
        if names:
            parts.append("STRUKTUR FILE (maks 40):")
            parts += [f"- {n}" for n in names]
    except GitHubError:
        pass

    for path in include_files or []:
        try:
            content = read_file(owner, repo, path, branch or detail["default_branch"])
            if content:
                parts.append(f"ISI FILE {path}:\n```\n{content[:1500]}\n```")
        except GitHubError:
            continue

    text = "\n".join(parts)
    return text[:max_chars]


def whoami() -> dict[str, Any]:
    data = _get("/user", use_cache=True)
    return {
        "login": data.get("login", ""),
        "name": data.get("name", ""),
        "public_repos": data.get("public_repos", 0),
        "avatar": data.get("avatar_url", ""),
        "plan": (data.get("plan") or {}).get("name", ""),
    }


def rate_limit() -> dict[str, Any]:
    data = _get("/rate_limit", use_cache=False)
    core = (data.get("resources") or {}).get("core") or {}
    return {
        "limit": core.get("limit", 0),
        "remaining": core.get("remaining", 0),
        "reset_at": core.get("reset", 0),
    }


def last_checked() -> float:
    return time.time()
