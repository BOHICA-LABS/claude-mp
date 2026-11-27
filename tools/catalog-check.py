#!/usr/bin/env python3
"""catalog-check.py - the checks `claude plugin validate` does not make on a catalog of pinned plugins.

Run from the catalog repository:
    python3 tools/catalog-check.py --audience public                      (the public catalog: no credentials are used)
    python3 tools/catalog-check.py --audience private                     (the private catalog: git's stored credentials)
    python3 tools/catalog-check.py --audience public --base-file old.json (also compare with the previous catalog file)

Exit 0 = every rule holds for every entry. Exit 1 = at least one FAIL line. Exit 2 = the catalog file cannot be read.

Rules (one FAIL line per broken rule and entry):
  R1  the entry's source is a git source: github, url or git-subdir (no relative path, no other type)
  R2  the entry has no `version` (the version is declared in the plugin's plugin.json only)
  R3  the source has `ref` and `sha`; `sha` is 40 lowercase hex characters
  R4  the plugin repository can be read (--audience public: with NO credentials at all)
  R5  `ref` is a TAG of that repository (a branch is not a pin) and the tag points at `sha`
  R6  plugin.json exists at `sha` (under `path` for git-subdir), its `name` equals the entry name, it has a `version`
  R7  the tag is named v<version> or <name>--v<version> for that plugin.json version
  R8  (with --base-file) an entry whose `sha` changed also changed its plugin.json version; otherwise no installed
      user receives the new commit
  R9  (with --base-file) an entry that left `plugins` has a line in `renames` (its new name, or null)
  R10 the README lists exactly the entries: between the lines <!-- plugins:start --> and <!-- plugins:end --> the
      table has one row per entry, its first cell being the entry name in back-ticks (a README without these two
      marker lines is only checked for mentioning every entry name)
Notes are printed for things that are allowed but worth a look (a version that went down, a description that differs).
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import catalog_lib as lib  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Check a catalog of pinned Claude Code plugins.")
    ap.add_argument("--root", default=".", help="catalog repository root (holds .claude-plugin/marketplace.json)")
    ap.add_argument("--audience", choices=("public", "private"), required=True)
    ap.add_argument("--base-file", help="the previous marketplace.json, for rules R8 and R9")
    ap.add_argument("--readme", default="README.md", help="README path relative to --root; empty string skips R10")
    args = ap.parse_args()
    anonymous = args.audience == "public"

    path = os.path.join(args.root, ".claude-plugin", "marketplace.json")
    try:
        cat = lib.load_catalog(path)
        base = lib.load_catalog(args.base_file) if args.base_file else None
    except (OSError, ValueError) as exc:
        print("ERROR %s" % exc)
        return 2

    fails, notes = [], []

    def fail(rule, name, msg):
        fails.append("FAIL %-3s %s: %s" % (rule, name, msg))

    readme = None
    listed = None
    if args.readme:
        try:
            readme = open(os.path.join(args.root, args.readme), encoding="utf-8").read()
        except OSError:
            fail("R10", "(catalog)", "%s cannot be read" % args.readme)
        if readme is not None and "<!-- plugins:start -->" in readme and "<!-- plugins:end -->" in readme:
            block = readme.split("<!-- plugins:start -->", 1)[1].split("<!-- plugins:end -->", 1)[0]
            listed = set(re.findall(r"^\| `([^`|]+)` \|", block, re.M))

    base_entries = {e.get("name"): e for e in (base or {}).get("plugins", []) if isinstance(e, dict)}
    versions = {}
    print("catalog %s (%s audience): %d entries" % (cat.get("name"), args.audience, len(cat["plugins"])))

    for entry in cat["plugins"]:
        name = entry.get("name", "?") if isinstance(entry, dict) else "?"
        src = entry.get("source") if isinstance(entry, dict) else None
        before = len(fails)
        if listed is not None:
            if name not in listed:
                fail("R10", name, "the README's plugin table has no row for this entry")
        elif readme is not None and name not in readme:
            fail("R10", name, "the README does not mention this entry")
        if "version" in entry:
            fail("R2", name, "the entry sets version %r; remove it (plugin.json is the only place)" % entry["version"])
        if not isinstance(src, dict) or src.get("source") not in lib.GIT_SOURCES:
            fail("R1", name, "source must be an object of type github, url or git-subdir; got %r" % (src if not isinstance(src, dict) else src.get("source")))
            continue
        ref, sha = src.get("ref"), src.get("sha")
        if not ref or not sha:
            fail("R3", name, "source needs both ref and sha (ref=%r sha=%r)" % (ref, sha))
        elif not lib.SHA_RE.match(sha):
            fail("R3", name, "sha must be 40 lowercase hex characters; got %r" % sha)
        url = lib.source_url(src)
        ok, found, err = lib.ls_remote(url, ref or "HEAD", anonymous)
        if not ok:
            why = "with no credentials (a public catalog lists public repositories only)" if anonymous else "with the stored git credentials"
            fail("R4", name, "%s cannot be read %s: %s" % (url, why, err.splitlines()[-1] if err else ""))
            continue
        if ref:
            if found.get("tag") is None:
                kind = "a branch (a branch is not a pin)" if found.get("branch") else "neither a tag nor a branch of the repository"
                fail("R5", name, "ref %r is %s" % (ref, kind))
            elif sha and lib.SHA_RE.match(str(sha)) and found["tag"] != sha:
                fail("R5", name, "tag %s points at %s but the entry pins %s" % (ref, found["tag"][:12], str(sha)[:12]))
        if not sha or not lib.SHA_RE.match(str(sha)):
            continue
        manifest, err = lib.read_manifest(url, sha, lib.manifest_path(src), anonymous)
        if manifest is None:
            fail("R6", name, err)
            continue
        version = manifest.get("version")
        versions[name] = version
        if manifest.get("name") != name:
            fail("R6", name, "plugin.json at the pin is named %r" % manifest.get("name"))
        if not version:
            fail("R6", name, "plugin.json at the pin has no version")
        elif ref and found.get("tag") is not None and ref not in lib.tag_names(name, version):
            fail("R7", name, "plugin.json at the pin says %s but the tag is %s (expected %s or %s)" % ((version, ref) + lib.tag_names(name, version)))
        if entry.get("description") and manifest.get("description") and entry["description"] != manifest["description"]:
            notes.append("note    %s: the entry's description differs from plugin.json at the pin (users see the entry's)" % name)
        old = base_entries.get(name)
        old_src = old.get("source") if isinstance(old, dict) else None
        if isinstance(old_src, dict) and lib.SHA_RE.match(str(old_src.get("sha", ""))) and old_src["sha"] != sha and version:
            old_manifest, old_err = lib.read_manifest(lib.source_url(old_src), old_src["sha"], lib.manifest_path(old_src), anonymous)
            if old_manifest is None:
                notes.append("note    %s: the previous pin cannot be read (%s)" % (name, old_err))
            elif old_manifest.get("version") == version:
                fail("R8", name, "sha moved %s -> %s but plugin.json still says %s; installed users would receive nothing" % (old_src["sha"][:12], sha[:12], version))
            else:
                notes.append("note    %s: %s -> %s" % (name, old_manifest.get("version"), version))
        if len(fails) == before:
            print("ok      %s %s  %s @ %s" % (name, version, ref, sha[:12]))

    if listed is not None:
        for extra in sorted(listed - {e.get("name") for e in cat["plugins"] if isinstance(e, dict)}):
            fail("R10", extra, "the README's plugin table has a row for a plugin that is not an entry")

    if base is not None:
        now = {e.get("name") for e in cat["plugins"] if isinstance(e, dict)}
        renames = cat.get("renames") or {}
        for gone in sorted(n for n in base_entries if n not in now):
            if gone not in renames:
                fail("R9", gone, "the entry was removed but renames has no line for it (use null for a removed plugin)")
            else:
                notes.append("note    %s: removed, renames -> %r" % (gone, renames[gone]))

    for line in notes:
        print(line)
    for line in fails:
        print(line)
    print("\n%s: %d FAIL" % ("FAILED" if fails else "PASSED", len(fails)))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
