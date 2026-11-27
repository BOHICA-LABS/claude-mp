"""catalog_lib.py - shared helpers of catalog-check.py and catalog-pin.py (Python 3.9+, standard library and git only).

A catalog entry is "pinned" when its source is a git source (github, url or git-subdir) that carries
  ref = a TAG of the plugin repository, and
  sha = the commit that tag points at,
and the plugin's version is declared in the plugin's own plugin.json at that commit (never in the entry).
"""
import json
import os
import re
import shutil
import subprocess
import tempfile

GIT_SOURCES = ("github", "url", "git-subdir")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def git_env(anonymous: bool) -> dict:
    """Environment for git. anonymous=True removes every credential source, so a private repository cannot be read."""
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    if anonymous:
        env["GIT_CONFIG_GLOBAL"] = os.devnull
        env["GIT_CONFIG_NOSYSTEM"] = "1"
        env["GIT_ASKPASS"] = "true"
        env["SSH_ASKPASS"] = "true"
        for name in ("GH_TOKEN", "GITHUB_TOKEN", "GIT_CONFIG_COUNT", "SSH_AUTH_SOCK"):
            env.pop(name, None)
    return env


def git(args, anonymous=False, cwd=None, timeout=180):
    cmd = ["git"]
    if anonymous:
        cmd += ["-c", "credential.helper="]
    cmd += ["-c", "protocol.file.allow=always"] + list(args)
    # Never run inside the catalog checkout: its repository config can carry a token (actions/checkout writes one),
    # which would make an "anonymous" read succeed on a private repository.
    p = subprocess.run(cmd, cwd=cwd or tempfile.gettempdir(), env=git_env(anonymous), capture_output=True, text=True, timeout=timeout)
    return p.returncode, p.stdout, p.stderr.strip()


def source_url(src: dict) -> str:
    """Clone URL of a git plugin source. A github source, and owner/repo shorthand in git-subdir, mean github.com over HTTPS."""
    kind = src.get("source")
    if kind == "github":
        return "https://github.com/%s.git" % src.get("repo", "")
    url = src.get("url", "")
    if kind == "git-subdir" and re.match(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", url):
        return "https://github.com/%s.git" % url
    return url


def manifest_path(src: dict) -> str:
    sub = src.get("path", "").strip("/") if src.get("source") == "git-subdir" else ""
    return (sub + "/" if sub else "") + ".claude-plugin/plugin.json"


def ls_remote(url: str, ref: str, anonymous: bool):
    """Returns (ok, {"tag": sha|None, "branch": sha|None}, error text). A tag's sha is the commit it points at."""
    code, out, err = git(["ls-remote", url, "refs/tags/%s" % ref, "refs/tags/%s^{}" % ref, "refs/heads/%s" % ref], anonymous)
    if code != 0:
        return False, {}, err or "git ls-remote failed"
    found = {"tag": None, "branch": None}
    direct = peeled = None
    for line in out.splitlines():
        sha, _, name = line.partition("\t")
        if name == "refs/tags/%s" % ref:
            direct = sha
        elif name == "refs/tags/%s^{}" % ref:
            peeled = sha
        elif name == "refs/heads/%s" % ref:
            found["branch"] = sha
    found["tag"] = peeled or direct
    return True, found, ""


def read_manifest(url: str, sha: str, path: str, anonymous: bool):
    """Fetches the one commit and returns (plugin.json as dict | None, error text)."""
    tmp = tempfile.mkdtemp(prefix="catalog-check-")
    try:
        git(["init", "-q", tmp], anonymous)
        git(["remote", "add", "origin", url], anonymous, cwd=tmp)
        git(["config", "remote.origin.promisor", "true"], anonymous, cwd=tmp)
        git(["config", "remote.origin.partialclonefilter", "blob:none"], anonymous, cwd=tmp)
        code, _, err = git(["fetch", "-q", "--depth", "1", "--filter=blob:none", "origin", sha], anonymous, cwd=tmp)
        if code != 0:
            code, _, err = git(["fetch", "-q", "--depth", "1", "origin", sha], anonymous, cwd=tmp)
        if code != 0:
            return None, "commit %s cannot be fetched: %s" % (sha[:12], err.splitlines()[-1] if err else "unknown error")
        code, out, err = git(["show", "FETCH_HEAD:%s" % path], anonymous, cwd=tmp)
        if code != 0:
            return None, "%s does not exist at commit %s" % (path, sha[:12])
        try:
            data = json.loads(out)
        except ValueError as exc:
            return None, "%s at commit %s is not valid JSON: %s" % (path, sha[:12], exc)
        if not isinstance(data, dict):
            return None, "%s at commit %s is not a JSON object" % (path, sha[:12])
        return data, ""
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def tag_names(name: str, version: str):
    """The two tag spellings a release may use: v<version>, or <plugin>--v<version> (what `claude plugin tag` creates)."""
    return ("v%s" % version, "%s--v%s" % (name, version))


def load_catalog(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict) or not isinstance(data.get("plugins"), list):
        raise ValueError("%s: not a marketplace file (no plugins array)" % path)
    return data
