#!/usr/bin/env python3
"""Markdown generator for the log of interventions carried out.

Counterpart of report.py: that one describes what was FOUND, this one describes
what was RESOLVED and how. It is generated at the end of the session, after
the fixes.

Usage:  python3 intervention.py interventions.json [-o log.md] [--lang en|cs]
Without -o the path is derived automatically:
    hosts/<hostname>/reports/<YYYY-MM-DD_HHMM>-intervention.md

Report language: --lang, otherwise `language` in hosts/sysadmin.toml,
otherwise "en". The JSON `status` values are always the English keys from
STATUS; only their display text is localized.
"""

import argparse
import json
import pathlib
import sys
import tomllib

from report import cell, default_out, para, section, stamp

# Canonical `status` values in the JSON, in display order.
STATUS = ["resolved", "partial", "not_done", "reverted"]

# Every human-readable string the script renders. The "cs" entries are the
# original Czech output and must stay byte-for-byte unchanged.
STRINGS = {
    "en": {
        "status": {"resolved": "resolved", "partial": "partial",
                   "not_done": "not done", "reverted": "reverted"},
        "host": "host",
        "title": "Intervention log — {host}",
        "follows": "Follows up on the diagnostics in `{report}`.",
        "addressed": "What was addressed and how",
        "no_items": "No intervention was made to the system.",
        "table": "| # | Status | Area | Intervention |",
        "problem": "Problem",
        "how": "How",
        "verify": "Verification",
        "rollback": "Rollback",
        "note": "Note",
        "repo_changes": "Changes inside the repository",
        "unresolved": "Left unresolved",
        "next_steps": "Recommended next steps",
        "footer": ("Log recorded {when}. It describes the interventions carried out; "
                   "the state of the system before them is captured by the "
                   "corresponding system check report."),
        "written": "written: {out}",
    },
    "cs": {
        "status": {"resolved": "vyřešeno", "partial": "částečně",
                   "not_done": "neprovedeno", "reverted": "vráceno"},
        "host": "stroj",
        "title": "Záznam zásahů — {host}",
        "follows": "Navazuje na diagnostiku `{report}`.",
        "addressed": "Co se řešilo a jak",
        "no_items": "Žádný zásah do systému nebyl proveden.",
        "table": "| # | Stav | Oblast | Zásah |",
        "problem": "Co se řešilo",
        "how": "Jak",
        "verify": "Ověření",
        "rollback": "Návrat",
        "note": "Poznámka",
        "repo_changes": "Změny uvnitř repozitáře",
        "unresolved": "Zůstalo neopravené",
        "next_steps": "Doporučené další kroky",
        "footer": ("Záznam pořízen {when}. Popisuje provedené zásahy; stav systému "
                   "před nimi zachycuje odpovídající report kontroly."),
        "written": "zapsano: {out}",
    },
}


def load_language(root, override=None):
    """Report language: override (--lang), else hosts/sysadmin.toml, else "en"."""
    if override:
        return override
    cfg = pathlib.Path(root) / "hosts" / "sysadmin.toml"
    try:
        with open(cfg, "rb") as fh:
            lang = tomllib.load(fh).get("language", "en")
    except FileNotFoundError:
        return "en"
    except tomllib.TOMLDecodeError as e:
        sys.exit(f"{cfg}: {e}")
    if lang not in STRINGS:
        sys.exit(f"{cfg}: unsupported language {lang!r}, expected one of: "
                 + ", ".join(STRINGS))
    return lang


def build(d, lang="en"):
    S = STRINGS[lang]

    def label(status):
        # Unknown values are rendered as they are, like before.
        return S["status"].get(status, status)

    items = d.get("interventions", [])
    when = d.get("timestamp") or stamp("%Y-%m-%d %H:%M")
    host = d.get("hostname", S["host"])
    meta = " · ".join(filter(None, [d.get("distro"), d.get("kernel")]))

    L = ["# " + S["title"].format(host=host), ""]
    L.append(f"**{when}**" + (f" · {meta}" if meta else ""))

    counts = {k: sum(1 for i in items if i.get("status") == k) for k in STATUS}
    active = [k for k in STATUS if counts[k]]
    if active:
        L += ["", "| " + " | ".join(label(k) for k in active) + " |",
              "|" + "---:|" * len(active),
              "| " + " | ".join(str(counts[k]) for k in active) + " |"]

    if d.get("report"):
        L += ["", S["follows"].format(report=para(d["report"]))]

    L += ["", f"## {S['addressed']}", ""]
    if not items:
        L.append(S["no_items"])
    else:
        L += [S["table"], "|---:|---|---|---|"]
        for n, it in enumerate(items, 1):
            L.append(f'| {n} | {cell(label(it.get("status", "not_done")))} | '
                     f'{cell(it.get("area", "—"))} | {cell(it.get("title", ""))} |')
        L.append("")
        for n, it in enumerate(items, 1):
            L += ["", f'### {n}. {para(it.get("title", ""))}',
                  f'*{para(label(it.get("status", "not_done")))}'
                  + (f' · {para(it["area"])}' if it.get("area") else "") + "*", ""]
            if it.get("problem"):
                L.append(f'- **{S["problem"]}:** {para(it["problem"])}')
            if it.get("how"):
                L += [f'- **{S["how"]}:**', "", "  ```", ]
                L += [f"  {line}" for line in str(it["how"]).splitlines()]
                L += ["  ```", ""]
            if it.get("verify"):
                L.append(f'- **{S["verify"]}:** {para(it["verify"])}')
            if it.get("rollback"):
                L.append(f'- **{S["rollback"]}:** {para(it["rollback"])}')
            # The note comes last on purpose: it holds what did not go to plan,
            # what the user overruled and where the prediction was wrong.
            # Without it the log is just a list of successes.
            if it.get("note"):
                L += ["", f'> **{S["note"]}:** {para(it["note"])}']

    L += section(S["repo_changes"], d.get("repo_changes", []))
    L += section(S["unresolved"], d.get("unresolved", []))
    L += section(S["next_steps"], d.get("next_steps", []), numbered=True)

    L += ["", "---", "", S["footer"].format(when=when)]
    return "\n".join(L).rstrip() + "\n"


def main():
    ap = argparse.ArgumentParser(description="Markdown log of interventions carried out")
    ap.add_argument("json", help="interventions file, or - for stdin")
    ap.add_argument("-o", "--out",
                    help="output file; without it "
                         "hosts/<host>/reports/<timestamp>-intervention.md")
    ap.add_argument("--lang", choices=list(STRINGS),
                    help="report language; overrides `language` in hosts/sysadmin.toml "
                         "(default: en)")
    a = ap.parse_args()
    lang = load_language(pathlib.Path(__file__).resolve().parents[3], a.lang)
    raw = sys.stdin.read() if a.json == "-" else open(a.json, encoding="utf-8").read()
    data = json.loads(raw)
    out = pathlib.Path(a.out) if a.out else default_out(data, "intervention")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build(data, lang), encoding="utf-8")
    print(STRINGS[lang]["written"].format(out=out))


if __name__ == "__main__":
    main()
