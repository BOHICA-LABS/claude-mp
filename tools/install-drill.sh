#!/bin/bash
# install-drill.sh <catalog root>
# Adds the catalog checkout as a marketplace in a THROWAWAY Claude Code configuration directory, installs every entry,
# and checks that each one is installed at the pinned commit with the version its plugin.json declares and no load error.
# CLAUDE_CONFIG_DIR must be set by the caller to an empty or new folder; the script refuses to run without it, so it can
# never touch a real configuration. No login is needed for these commands.
set -euo pipefail
root="${1:?usage: install-drill.sh <catalog root>}"
: "${CLAUDE_CONFIG_DIR:?set CLAUDE_CONFIG_DIR to a throwaway folder first}"
case "$CLAUDE_CONFIG_DIR" in "$HOME/.claude"|"$HOME/.claude/"*) echo "refusing the real configuration directory" >&2; exit 2;; esac
mkdir -p "$CLAUDE_CONFIG_DIR"
if [ -e "$CLAUDE_CONFIG_DIR/plugins/installed_plugins.json" ]; then echo "CLAUDE_CONFIG_DIR already holds installs; use a new folder" >&2; exit 2; fi
manifest="$root/.claude-plugin/marketplace.json"
mp=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["name"])' "$manifest")
claude plugin marketplace add "$root" < /dev/null
python3 -c 'import json,sys; [print(p["name"]) for p in json.load(open(sys.argv[1]))["plugins"]]' "$manifest" | while read -r name; do
  claude plugin install "$name@$mp" < /dev/null
done
claude plugin list --json < /dev/null > "$CLAUDE_CONFIG_DIR/drill-list.json"
python3 - "$manifest" "$CLAUDE_CONFIG_DIR" "$mp" <<'EOF'
import json, os, sys
manifest, cfg, mp = sys.argv[1:4]
entries = {p["name"]: p for p in json.load(open(manifest))["plugins"]}
records = json.load(open(os.path.join(cfg, "plugins", "installed_plugins.json"))).get("plugins", {})
listed = json.load(open(os.path.join(cfg, "drill-list.json")))
listed = listed if isinstance(listed, list) else listed.get("plugins", [])
errors_by_id = {p.get("id"): p.get("errors") for p in listed if isinstance(p, dict)}
bad = 0
for name, entry in entries.items():
    pid = "%s@%s" % (name, mp)
    recs = records.get(pid) or []
    if not recs:
        print("FAIL %s: no install record" % pid); bad += 1; continue
    rec = recs[0]
    want = entry["source"].get("sha") if isinstance(entry.get("source"), dict) else None
    pj = os.path.join(rec.get("installPath", ""), ".claude-plugin", "plugin.json")
    declared = json.load(open(pj)).get("version") if os.path.exists(pj) else None
    problems = []
    if want and rec.get("gitCommitSha") != want:
        problems.append("installed commit %s, pinned %s" % (rec.get("gitCommitSha"), want))
    if declared != rec.get("version"):
        problems.append("recorded version %s, plugin.json says %s" % (rec.get("version"), declared))
    if errors_by_id.get(pid):
        problems.append("load errors: %s" % errors_by_id[pid])
    if problems:
        print("FAIL %s: %s" % (pid, "; ".join(problems))); bad += 1
    else:
        print("ok   %s version %s at %s" % (pid, rec.get("version"), rec.get("gitCommitSha")))
print("\n%s: %d of %d entries failed" % ("FAILED" if bad else "PASSED", bad, len(entries)))
sys.exit(1 if bad else 0)
EOF
