from typing import Optional

try:
    import git as _git
    _GIT_OK = True
except ImportError:
    _GIT_OK = False


def _repo(path: str):
    if not _GIT_OK:
        raise RuntimeError("gitpython not installed — run: pip install gitpython")
    return _git.Repo(path, search_parent_directories=True)


def git_status(repo_path: str) -> str:
    try:
        repo = _repo(repo_path)
        lines = []
        if repo.head.is_valid():
            lines.append(f"Branch: {repo.active_branch.name}")
            lines.append(f"HEAD:   {repo.head.commit.hexsha[:8]} {repo.head.commit.summary}")

        staged    = [i.a_path for i in repo.index.diff("HEAD")] if repo.head.is_valid() else []
        unstaged  = [i.a_path for i in repo.index.diff(None)]
        untracked = repo.untracked_files[:30]

        if staged:    lines += ["\nStaged:"]    + [f"  + {f}" for f in staged]
        if unstaged:  lines += ["\nModified:"]  + [f"  M {f}" for f in unstaged]
        if untracked: lines += ["\nUntracked:"] + [f"  ? {f}" for f in untracked]
        if not staged and not unstaged and not untracked:
            lines.append("\nWorking tree clean")
        return "\n".join(lines)
    except Exception as e:
        return f"git error: {e}"


def git_diff(repo_path: str, file_path: Optional[str] = None) -> str:
    try:
        repo = _repo(repo_path)
        diff = repo.git.diff(file_path) if file_path else repo.git.diff()
        return diff or "No unstaged changes"
    except Exception as e:
        return f"git error: {e}"


def git_log(repo_path: str, n: int = 10) -> str:
    try:
        repo = _repo(repo_path)
        if not repo.head.is_valid():
            return "No commits yet"
        return "\n".join(
            f"{c.hexsha[:8]} {c.committed_datetime.date()} {c.author.name}: {c.summary}"
            for c in repo.iter_commits(max_count=n)
        )
    except Exception as e:
        return f"git error: {e}"


def git_commit(repo_path: str, message: str, files: Optional[list] = None) -> str:
    try:
        repo = _repo(repo_path)
        if files:
            repo.index.add(files)
        else:
            repo.git.add("-u")
        commit = repo.index.commit(message)
        return f"Committed {commit.hexsha[:8]}: {message}"
    except Exception as e:
        return f"git error: {e}"
