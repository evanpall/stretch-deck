"""Publish new videos to Stretch Deck.

Scans videos/<Category Folder>/ for video files that have no entry in
SEED_EXERCISES (index.html), adds an entry for each, bumps SHELL_CACHE in
sw.js, logs the change in PROJECT_NOTES.md, commits, pushes to main and waits
until GitHub Pages serves the new version.

Run it by double-clicking add-new-videos.bat in the project folder.

    python tools/add_new_videos.py            # do everything
    python tools/add_new_videos.py --dry-run  # only show what would be added
    python tools/add_new_videos.py --no-push  # edit + commit, don't push
"""
import argparse
import datetime
import io
import json
import os
import re
import subprocess
import sys
import textwrap
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = "https://evanpall.github.io/stretch-deck/"
BRANCH = "main"
VIDEO_EXTS = (".mp4", ".m4v", ".mov", ".webm")
MAX_BYTES = 100 * 1024 * 1024  # GitHub rejects files of 100 MB or more
# File names longer than this are treated as downloader gibberish and get a
# "rename me" placeholder title instead of a title taken from the file name.
MAX_NAME_FOR_TITLE = 40

CATEGORIES_RE = re.compile(r"^(\s*var DEFAULT_CATEGORIES = )(\[.*\]);[ \t]*\r?$", re.M)
SEEDS_RE = re.compile(r"^(\s*var SEED_EXERCISES = )(\[.*\]);[ \t]*\r?$", re.M)
CACHE_RE = re.compile(r'(var SHELL_CACHE = "stretchdeck-shell-v)(\d+)(")')
CHANGELOG_RE = re.compile(r"(## Changelog \(most recent first\)\r?\n\r?\n)")


class Stop(Exception):
    pass


def read(name):
    with io.open(os.path.join(ROOT, name), encoding="utf-8", newline="") as f:
        return f.read()


def write(name, text):
    with io.open(os.path.join(ROOT, name), "w", encoding="utf-8", newline="") as f:
        f.write(text)


def git(*args, **kw):
    check = kw.pop("check", True)
    stdin = kw.pop("stdin", None)
    p = subprocess.run(["git", "-c", "core.quotepath=false"] + list(args), cwd=ROOT,
                       input=stdin, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       encoding="utf-8", errors="replace")
    if check and p.returncode != 0:
        raise Stop("git %s failed:\n%s" % (" ".join(args), p.stdout.strip()))
    return p


def short(name):
    return name if len(name) <= 34 else name[:14] + "..." + name[-14:]


def title_from(stem):
    t = re.sub(r"[_\s]+", " ", stem).strip()
    return t[:1].upper() + t[1:]


def find_new(cats, seeds):
    """Return (new seed entries, warnings)."""
    warnings = []
    have = set((e["category"], e.get("videoFile", "")) for e in seeds)
    next_id = max([int(e["id"][5:]) for e in seeds if re.match(r"seed-\d+$", e["id"])] + [0]) + 1
    folders = {}
    added = []
    for c in cats:
        folders[c["folder"]] = c
        d = os.path.join(ROOT, "videos", c["folder"])
        if not os.path.isdir(d):
            warnings.append('Category "%s" has no folder videos/%s' % (c["name"], c["folder"]))
            continue
        mine = [e for e in seeds if e["category"] == c["id"]]
        order = max([e.get("order", -1) for e in mine] + [-1]) + 1
        clip = max([int(m.group(1)) for m in
                    (re.match(r"Untitled clip (\d+)", e["title"]) for e in mine) if m] + [0]) + 1
        for f in sorted(os.listdir(d), key=str.lower):
            stem, ext = os.path.splitext(f)
            if ext.lower() not in VIDEO_EXTS or (c["id"], f) in have:
                continue
            size = os.path.getsize(os.path.join(d, f))
            if size >= MAX_BYTES:
                warnings.append("SKIPPED videos/%s/%s - %d MB is over GitHub's 100 MB limit"
                                % (c["folder"], f, size // (1024 * 1024)))
                continue
            if len(stem) <= MAX_NAME_FOR_TITLE:
                title, what = title_from(stem), "duration and cue"
            else:
                title, what = "Untitled clip %d (rename me)" % clip, "name, duration and cue"
                clip += 1
            added.append({
                "id": "seed-%d" % next_id, "category": c["id"], "title": title,
                "duration": "", "equipment": "", "link": "", "videoFile": f,
                "notes": "Auto-added from your videos/%s folder — open it, then fill in the real %s."
                         % (c["folder"], what),
                "order": order})
            next_id += 1
            order += 1

    # Things the user probably wants to know about but that we leave alone.
    vroot = os.path.join(ROOT, "videos")
    for name in sorted(os.listdir(vroot)):
        p = os.path.join(vroot, name)
        if os.path.isdir(p) and name not in folders:
            n = len([f for f in os.listdir(p) if f.lower().endswith(VIDEO_EXTS)])
            if n:
                warnings.append('SKIPPED %d video(s) in videos/%s - that folder is not a category '
                                'in the app (check the spelling, or add the category first)' % (n, name))
        elif name.lower().endswith(VIDEO_EXTS):
            warnings.append("SKIPPED videos/%s - move it into a category folder" % name)
    by_id = dict((c["id"], c) for c in cats)
    for e in seeds:
        c = by_id.get(e["category"])
        if c and e.get("videoFile") and not os.path.isfile(
                os.path.join(vroot, c["folder"], e["videoFile"])):
            warnings.append('Listed in the app but file is missing: videos/%s/%s'
                            % (c["folder"], e["videoFile"]))
    return added, warnings


def apply_edits(html, seeds_match, added, cats):
    """Write index.html, sw.js and PROJECT_NOTES.md. Return the new cache version."""
    line = seeds_match.group(0)
    end = line.rindex("];")
    extra = "".join(", " + json.dumps(e, ensure_ascii=False) for e in added)
    write("index.html", html.replace(line, line[:end] + extra + line[end:]))

    sw = read("sw.js")
    m = CACHE_RE.search(sw)
    if not m:
        raise Stop("Could not find SHELL_CACHE in sw.js")
    version = int(m.group(2)) + 1
    write("sw.js", sw[:m.start()] + m.group(1) + str(version) + m.group(3) + sw[m.end():])

    notes = read("PROJECT_NOTES.md")
    m = CHANGELOG_RE.search(notes)
    if m:
        nl = "\r\n" if "\r\n" in notes else "\n"
        names = dict((c["id"], c["name"]) for c in cats)
        items = "; ".join('`%s` %s, "%s" (`%s`)' % (e["id"], names[e["category"]], e["title"],
                                                   short(e["videoFile"])) for e in added)
        entry = "- **%s** — `add-new-videos.bat` added %d video(s): %s. Bumped `SHELL_CACHE` to `v%d`." % (
            datetime.date.today().isoformat(), len(added), items, version)
        wrapped = textwrap.wrap(entry, 80, subsequent_indent="  ", break_long_words=False,
                                break_on_hyphens=False)
        write("PROJECT_NOTES.md", notes[:m.end()] + nl.join(wrapped) + nl + notes[m.end():])
    return version


def fetch(url, method="GET"):
    req = urllib.request.Request(url, method=method, headers={"Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status, (r.read().decode("utf-8", "replace") if method == "GET" else "")


def wait_until_live(version, cats, check):
    print("\nWaiting for GitHub Pages to publish (usually 1-2 minutes)...")
    want = "stretchdeck-shell-v%d" % version
    deadline = time.time() + 360
    while True:
        try:
            if want in fetch(SITE + "sw.js?t=%d" % time.time())[1]:
                break
        except (urllib.error.URLError, OSError):
            pass
        if time.time() > deadline:
            print("  Still not published after 6 minutes. The push succeeded, so it should")
            print("  appear soon - check " + SITE)
            return False
        sys.stdout.write(".")
        sys.stdout.flush()
        time.sleep(15)
    print("\n  New version v%d is live." % version)
    folders = dict((c["id"], c["folder"]) for c in cats)
    ok = True
    for e in check:
        url = SITE + "videos/%s/%s" % (urllib.parse.quote(folders[e["category"]]),
                                       urllib.parse.quote(e["videoFile"]))
        try:
            status = fetch(url, "HEAD")[0]
        except urllib.error.HTTPError as err:
            status = err.code
        except (urllib.error.URLError, OSError):
            status = 0
        if status != 200:
            ok = False
            print("  PROBLEM: video not reachable (%s): %s" % (status or "network error", e["videoFile"]))
    if ok and check:
        print("  All %d new video(s) load from the live site." % len(check))
    return ok


def main():
    ap = argparse.ArgumentParser(description="Publish new Stretch Deck videos.")
    ap.add_argument("--dry-run", action="store_true", help="only list what would be added")
    ap.add_argument("--no-push", action="store_true", help="commit but do not push")
    args = ap.parse_args()
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(errors="replace")

    branch = git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    if branch != BRANCH:
        raise Stop("You are on branch '%s'; the app is published from '%s'." % (branch, BRANCH))
    if not args.dry_run and not args.no_push:
        p = git("pull", "--ff-only", "origin", BRANCH, check=False)
        if p.returncode != 0:
            print("Warning: could not update from GitHub first:\n  " + p.stdout.strip().replace("\n", "\n  "))

    html = read("index.html")
    cm, sm = CATEGORIES_RE.search(html), SEEDS_RE.search(html)
    if not cm or not sm:
        raise Stop("Could not find DEFAULT_CATEGORIES / SEED_EXERCISES in index.html")
    cats, seeds = json.loads(cm.group(2)), json.loads(sm.group(2))

    added, warnings = find_new(cats, seeds)
    names = dict((c["id"], c["name"]) for c in cats)
    if added:
        print("New videos found: %d" % len(added))
        for e in added:
            print('  + %-20s "%s"   <- %s' % (names[e["category"]], e["title"], short(e["videoFile"])))
    else:
        print("No new videos - all %d video entries are already in the app." % len(seeds))
    for w in warnings:
        print("  ! " + w)
    if args.dry_run:
        print("\nDry run - nothing was changed.")
        return 0

    version = None
    if added:
        version = apply_edits(html, sm, added, cats)
        seeds = seeds + added

    # Commit. Also picks up edits left behind by an earlier run that was interrupted.
    folders = dict((c["id"], c["folder"]) for c in cats)
    paths = ["index.html", "sw.js", "PROJECT_NOTES.md"] + [
        "videos/%s/%s" % (folders[e["category"]], e["videoFile"]) for e in seeds
        if e["category"] in folders and e.get("videoFile")
        and os.path.isfile(os.path.join(ROOT, "videos", folders[e["category"]], e["videoFile"]))]
    git("add", "--pathspec-from-file=-", stdin="\n".join(paths) + "\n")
    if git("diff", "--cached", "--quiet", check=False).returncode != 0:
        if added:
            cat_names = sorted(set(names[e["category"]] for e in added))
            msg = "Add seed entr%s for %d new %s video%s\n\nBumped SHELL_CACHE to v%d so installed phones pick up the new shell." % (
                "y" if len(added) == 1 else "ies", len(added), ", ".join(cat_names),
                "" if len(added) == 1 else "s", version)
        else:
            msg = "Publish pending video changes"
        git("commit", "-m", msg)
        print("\nCommitted: " + msg.splitlines()[0])

    if args.no_push:
        print("\n--no-push given - not pushing.")
        return 0
    ahead = git("rev-list", "--count", "origin/%s..HEAD" % BRANCH, check=False).stdout.strip()
    if ahead in ("", "0"):
        return 0
    print("Uploading to GitHub (can take a while for big videos)...")
    git("push", "origin", BRANCH)
    print("  Pushed.")
    if version is None:
        version = int(CACHE_RE.search(read("sw.js")).group(2))
    ok = wait_until_live(version, cats, added)
    if ok:
        print("\nDONE. On your phone: fully close the app and reopen it (twice if needed).")
        print("Then open each new video and fill in its real name / duration / cue.")
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Stop as e:
        print("\nSTOPPED: %s" % e)
        sys.exit(1)
