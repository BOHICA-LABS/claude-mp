#!/usr/bin/env python3
"""catalog-pin.py - write (or print) the pinned entry of one plugin release.

    python3 tools/catalog-pin.py --name vsdd-factory --tag v1.0.0-rc.26 --write
        moves the EXISTING entry vsdd-factory to that tag: sets source.ref and source.sha, removes any entry `version`

    python3 tools/catalog-pin.py --name my-plugin --tag my-plugin--v0.1.0 --github your-org/my-plugin
        prints a NEW entry for a plugin at the root of a GitHub repository (add --write to append it)

    python3 tools/catalog-pin.py --name tool --tag v2.0.0 --git-subdir https://github.com/org/mono.git --path plugins/tool

Before anything is written the release is checked: the tag exists, plugin.json exists at the tag's commit, its name is
--name and its version matches the tag name (v<version> or <name>--v<version>). --audience public reads with no credentials.
Exit 0 = printed or written. Exit 1 = the release does not pass; nothing is written.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import catalog_lib as lib  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Pin one catalog entry to a release tag and its commit.")
    ap.add_argument("--root", default=".")
    ap.add_argument("--name", required=True, help="entry name (equals the name in plugin.json)")
    ap.add_argument("--tag", required=True, help="release tag in the plugin repository")
    ap.add_argument("--audience", choices=("public", "private"), default="private")
    kind = ap.add_mutually_exclusive_group()
    kind.add_argument("--github", metavar="OWNER/REPO", help="new entry: plugin at the root of a GitHub repository")
    kind.add_argument("--url", metavar="GIT_URL", help="new entry: plugin at the root of a git repository on any host")
    kind.add_argument("--git-subdir", metavar="GIT_URL", help="new entry: plugin in a sub-folder (give --path)")
    ap.add_argument("--path", help="sub-folder of the plugin, with --git-subdir")
    ap.add_argument("--write", action="store_true", help="write .claude-plugin/marketplace.json instead of printing")
    args = ap.parse_args()
    anonymous = args.audience == "public"

    path = os.path.join(args.root, ".claude-plugin", "marketplace.json")
    try:
        cat = lib.load_catalog(path)
    except (OSError, ValueError) as exc:
        print("ERROR %s" % exc, file=sys.stderr)
        return 1
    existing = next((e for e in cat["plugins"] if isinstance(e, dict) and e.get("name") == args.name), None)

    if args.github:
        src = {"source": "github", "repo": args.github}
    elif args.url:
        src = {"source": "url", "url": args.url}
    elif args.git_subdir:
        if not args.path:
            print("ERROR --git-subdir needs --path", file=sys.stderr)
            return 1
        src = {"source": "git-subdir", "url": args.git_subdir, "path": args.path}
    elif existing and isinstance(existing.get("source"), dict) and existing["source"].get("source") in lib.GIT_SOURCES:
        src = {k: v for k, v in existing["source"].items() if k not in ("ref", "sha")}
    else:
        print("ERROR no entry %r with a git source in %s; give --github, --url or --git-subdir" % (args.name, path), file=sys.stderr)
        return 1

    url = lib.source_url(src)
    ok, found, err = lib.ls_remote(url, args.tag, anonymous)
    if not ok:
        print("ERROR %s cannot be read: %s" % (url, err), file=sys.stderr)
        return 1
    if found.get("tag") is None:
        print("ERROR %s has no tag %s" % (url, args.tag), file=sys.stderr)
        return 1
    sha = found["tag"]
    manifest, err = lib.read_manifest(url, sha, lib.manifest_path(src), anonymous)
    if manifest is None:
        print("ERROR %s" % err, file=sys.stderr)
        return 1
    version = manifest.get("version")
    if manifest.get("name") != args.name:
        print("ERROR plugin.json at %s is named %r, not %r" % (args.tag, manifest.get("name"), args.name), file=sys.stderr)
        return 1
    if not version or args.tag not in lib.tag_names(args.name, version):
        print("ERROR plugin.json at %s says version %r; the tag must be %s or %s" % ((args.tag, version) + lib.tag_names(args.name, version or "?")), file=sys.stderr)
        return 1

    src["ref"], src["sha"] = args.tag, sha
    if existing is not None:
        entry = existing
        entry["source"] = src
        entry.pop("version", None)
    else:
        entry = {"name": args.name, "source": src}
        if manifest.get("description"):
            entry["description"] = manifest["description"]
        cat["plugins"].append(entry)

    if args.write:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(cat, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        print("%s: entry %s -> %s (version %s) @ %s" % (path, args.name, args.tag, version, sha))
    else:
        print(json.dumps(entry, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
