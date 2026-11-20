"""Copy a Confluence page (a DCRI SDLC template) and record the copy in tracking.json.

The jira-confluence skill's `jc conf copy` only accepts a page as the parent. The release
documents live in a Confluence *folder*, so this calls the same copy endpoint through the
skill's own client (same token handling, same endpoint allow-list, no deletes) with the
folder as the destination.

    python tools/release/conf_copy.py <slug> <template_page_id> "<title>" (--folder ID | --parent PAGE_ID) [--apply]

Dry run unless --apply. Refuses if the slug is already recorded.
"""
import argparse
import json
import os
import sys
from pathlib import Path

SKILLS = Path(os.environ.get("DCRI_SKILLS_DIR", Path.home() / "PROJECTS/devops/dcri-skills-setup/plugins/dcri-global/skills"))
sys.path.insert(0, str(SKILLS / "jira-confluence" / "scripts"))
from jira_confluence.client import Client  # noqa: E402

TRACK = Path("docs/release-1.0/tracking.json")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("slug"); ap.add_argument("template"); ap.add_argument("title")
    ap.add_argument("--folder"); ap.add_argument("--parent"); ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    track = json.loads(TRACK.read_text())
    if a.slug in track["pages"]:
        sys.exit(f"already recorded: {a.slug} = {track['pages'][a.slug]['id']}")
    if bool(a.folder) == bool(a.parent):
        sys.exit("give exactly one of --folder / --parent")
    dest = {"type": "parent_content", "value": a.folder} if a.folder else {"type": "parent_page", "value": a.parent}
    body = {"copyAttachments": True, "copyPermissions": False, "copyProperties": True, "copyLabels": False,
            "copyCustomContents": True, "destination": dest, "pageTitle": a.title}
    c = Client()
    c.check_space("ADP")
    r = c.write("POST", f"/wiki/rest/api/content/{a.template}/copy", body, dry_run=not a.apply,
                target=f"copy of template {a.template} titled '{a.title}' into {dest}")
    if not a.apply:
        print(json.dumps(r, indent=1)); return
    track["pages"][a.slug] = {"id": r["id"], "title": a.title, "template": a.template}
    TRACK.write_text(json.dumps(track, indent=1))
    print(r["id"], a.title)


if __name__ == "__main__":
    main()
