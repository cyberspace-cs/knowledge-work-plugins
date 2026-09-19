#!/usr/bin/env python3
"""Consistency check for anthropics/knowledge-work-plugins.

Run from the repository root:

    python verify_docs_consistency.py

Exits non-zero on any violation. Six invariants, each of which has been violated
by this repository at some point:

1. The plugin count in README.md equals the number of first-party plugin
   directories. The README said "11 plugins" while 17 shipped, which made six
   plugins undiscoverable from the repository landing page.
2. Every first-party plugin is linked from the README marketplace table.
3. `.claude-plugin/marketplace.json` is valid JSON and lists every first-party
   plugin.
4. Every `.claude-plugin/plugin.json` carries a name and a version.
5. Every `skills/*/SKILL.md` carries `name:` and `description:` frontmatter.
6. Every relative Markdown link resolves.

Deliberately *not* checked: whether a plugin README's skill table lists every
skill directory. The repository uses two naming conventions there (some READMEs
list slash-command names, some list skill names), so the check would report
dozens of pre-existing mismatches and would not be a usable gate. It is printed
as an informational count instead.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
COUNT_RE = re.compile(r"We're open-sourcing (\d+) plugins")
LINK_RE = re.compile(r"\]\(([^)#][^)]*)\)")
SKIP_SCHEMES = ("http://", "https://", "mailto:")


def first_party_plugins() -> list[str]:
    return sorted(
        d.name for d in ROOT.iterdir()
        if d.is_dir() and (d / ".claude-plugin" / "plugin.json").is_file()
    )


def main() -> int:
    errors: list[str] = []
    notes: list[str] = []
    plugins = first_party_plugins()
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    # 1 + 2
    match = COUNT_RE.search(readme)
    declared = int(match.group(1)) if match else -1
    if declared != len(plugins):
        errors.append(f"README.md declares {declared} plugins; the repo has {len(plugins)}")
    for name in plugins:
        if f"](./{name})" not in readme:
            errors.append(f"plugin {name!r} is not linked from the README marketplace table")
    notes.append(f"first-party plugins: {len(plugins)}")

    # 3
    mk_path = ROOT / ".claude-plugin" / "marketplace.json"
    try:
        marketplace = json.loads(mk_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"{mk_path.name} is not valid JSON: {exc}")
        marketplace = {"plugins": []}
    listed = {p.get("name") for p in marketplace.get("plugins", [])}
    absent = [n for n in plugins if n not in listed]
    if absent:
        errors.append(f"absent from marketplace.json: {absent}")
    notes.append(f"marketplace.json entries: {len(marketplace.get('plugins', []))}")

    # 4 + 5
    skills = 0
    for plugin in plugins:
        manifest = json.loads((ROOT / plugin / ".claude-plugin" / "plugin.json").read_text("utf-8"))
        if not manifest.get("name") or not manifest.get("version"):
            errors.append(f"{plugin}/plugin.json is missing name or version")
        skills_dir = ROOT / plugin / "skills"
        if not skills_dir.is_dir():
            continue
        for skill_dir in sorted(p for p in skills_dir.iterdir() if p.is_dir()):
            skill = skill_dir / "SKILL.md"
            if not skill.is_file():
                errors.append(f"{plugin}/skills/{skill_dir.name} has no SKILL.md")
                continue
            skills += 1
            parts = skill.read_text(encoding="utf-8").split("---")
            frontmatter = parts[1] if len(parts) > 2 else ""
            for key in ("name:", "description:"):
                if key not in frontmatter:
                    errors.append(f"{plugin}/skills/{skill_dir.name}/SKILL.md lacks {key}")
    notes.append(f"skills checked: {skills}")

    # 6
    markdown = (
        list(ROOT.glob("*.md"))
        + list(ROOT.glob("*/README.md"))
        + list(ROOT.glob("*/skills/*/SKILL.md"))
    )
    for doc in markdown:
        text = doc.read_text(encoding="utf-8")
        for target in LINK_RE.findall(text):
            if target.startswith(SKIP_SCHEMES):
                continue
            if not (doc.parent / target.split("#")[0]).resolve().exists():
                errors.append(f"{doc.relative_to(ROOT)}: broken link -> {target}")

    for note in notes:
        print(f"  {note}")
    if errors:
        print(f"\n{len(errors)} problem(s):")
        for err in errors:
            print(f"  - {err}")
        return 1
    print("\nOK — documentation and manifests are consistent")
    return 0


if __name__ == "__main__":
    sys.exit(main())
