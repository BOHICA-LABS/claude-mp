# claude-mp

Bohica Labs' public Claude Code plugin catalog (marketplace name: `claude-mp`).

This repository holds the catalog file `.claude-plugin/marketplace.json` and the checks that guard it. Each plugin lives in its own public repository; the catalog points at one release of it.

## Plugins

<!-- plugins:start -->
| Plugin | What it is | Source repository | Who can install |
| :- | :- | :- | :- |
| `vsdd-factory` | Verified Spec-Driven Development (VSDD) dark factory for software: brownfield ingest, spec crystallization, story decomposition, TDD delivery, adversarial review, holdout evaluation, formal verification, release gating | <https://github.com/bohica-labs/vsdd-factory> | anyone |
<!-- plugins:end -->

The release each plugin is pinned to is written in `.claude-plugin/marketplace.json`: `ref` is the release tag and `sha` is the commit of that tag. This catalog lists public repositories only.

## Install

From a shell:

```
claude plugin marketplace add bohica-labs/claude-mp
claude plugin install vsdd-factory@claude-mp
```

Or in a Claude Code session:

```
/plugin marketplace add bohica-labs/claude-mp
/plugin install vsdd-factory@claude-mp
/reload-plugins
```

- No GitHub account is needed. On a machine with no GitHub SSH key you can set `CLAUDE_CODE_PLUGIN_PREFER_HTTPS=1`, so that Claude Code clones GitHub `owner/repo` sources over HTTPS without trying SSH first.
- `claude plugin install` installs for you in every project (user scope). Add `--scope project` inside a repository to install for that repository only.
- `vsdd-factory`: after every install and every update, run `/vsdd-factory:activate` again in a session. The plugin's README says what that step does.

## Update

Background auto-update is off for this catalog unless you turn it on (`/plugin`, tab **Marketplaces**, select `claude-mp`). Without it, update by hand:

```
claude plugin update vsdd-factory@claude-mp
```

- You receive a new copy only when the plugin's version changed. `already at the latest version` means the catalog still pins the version you have.
- A project-scope install is updated one project at a time: run the command inside each project that installed the plugin.

## Use it in a repository

To register the catalog for everyone who works in one repository, run this once inside it and commit the `.claude/settings.json` it writes:

```
claude plugin marketplace add bohica-labs/claude-mp --scope project
claude plugin install vsdd-factory@claude-mp --scope project
```

Each contributor then runs the second command once in their own clone.

## What "pinned" means here

- An entry names a release tag (`ref`) and that tag's commit (`sha`). Claude Code checks out the commit, so a fresh install always gets the same bytes for the same catalog commit.
- The plugin's version is declared in one place, the plugin's own `plugin.json` at that commit. Entries carry no `version` field.
- A release reaches you when the catalog moves an entry to a new tag whose `plugin.json` version differs from the one you have.
- To go back, the catalog moves the entry back to the earlier tag; your next update installs that version.

## How a release gets into this catalog

1. The plugin repository publishes a release: `plugin.json` carries the new version, the release tag is created, and the tag is not moved afterwards.
2. A pull request here moves the entry to that tag: `python3 tools/catalog-pin.py --name <plugin> --tag <tag> --audience public --write`. For `vsdd-factory` the plugin's release workflow opens this pull request.
3. The checks below run on the pull request. A maintainer merges it.

## Checks (maintainers)

Every pull request, every push to `main` and a daily schedule run `.github/workflows/catalog.yml`:

- `claude plugin validate . --strict`
- `python3 tools/catalog-check.py --audience public`: every entry is a git source with a tag and its commit, readable with no credentials, with a `plugin.json` at that commit whose name and version agree with the entry and the tag; a moved pin must come with a changed version; a removed entry must have a line in `renames`; the plugin table of this README has exactly one row per entry.
- `tools/install-drill.sh`: adds this checkout as a marketplace in a throwaway configuration directory and installs every entry.

To add a plugin: its repository must be public, carry a release tag, and declare `version` in its `plugin.json`. Then run `tools/catalog-pin.py` with `--github`, `--url` or `--git-subdir`, add a row to the table above, and open a pull request.

To remove a plugin: delete its entry and add `"<name>": null` to `renames` in the same pull request.

## License

MIT — see [LICENSE](LICENSE).
