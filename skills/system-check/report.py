#!/usr/bin/env python3
"""Markdown report generator for a system check.

Usage:  python3 report.py findings.json [-o report.md] [--lang en|cs]
Without -o the path is derived automatically:
    hosts/<hostname>/reports/<YYYY-MM-DD_HHMM>-check.md

The output is Markdown so it can be read on a machine without a browser - `cat`,
`less`, `git diff` between runs. The JSON format is described in SKILL.md.

Report language: --lang, otherwise `language` in hosts/sysadmin.toml,
otherwise "en". JSON keys and severity codes (P1-P4) do not depend on it.
"""

import argparse
import datetime
import json
import pathlib
import socket
import sys
import tomllib

# Severity codes, most serious first. Their rendered labels live in STRINGS.
SEV = ["P1", "P2", "P3", "P4"]

# Every human-readable string the script renders. The "cs" entries are the
# original Czech output and must stay byte-for-byte unchanged.
STRINGS = {
    "en": {
        "sev": {"P1": "critical", "P2": "serious", "P3": "minor", "P4": "noise"},
        "host": "host",
        "title": "System check — {host}",
        "uptime": "uptime {uptime}",
        "findings": "Findings",
        "no_findings": "No findings.",
        "table": "| # | Sev. | Area | Finding |",
        "impact": "Impact",
        "fix": "Proposed fix",
        "clean": "Verified and clean",
        "not_checked": "Not checked",
        "next_steps": "Proposed fix order",
        "footer": ("State snapshot taken {when}. The report is read-only — none of the "
                   "listed fixes has been applied, each needs separate approval. "
                   "Interventions carried out are described in a separate "
                   "`*-intervention.md` log."),
        "written": "written: {out}",
    },
    "cs": {
        "sev": {"P1": "kritická", "P2": "vážná", "P3": "drobná", "P4": "šum"},
        "host": "stroj",
        "title": "Kontrola systému — {host}",
        "uptime": "uptime {uptime}",
        "findings": "Nálezy",
        "no_findings": "Žádné nálezy.",
        "table": "| # | Záv. | Oblast | Nález |",
        "impact": "Dopad",
        "fix": "Návrh řešení",
        "clean": "Ověřeno a v pořádku",
        "not_checked": "Nezkontrolováno",
        "next_steps": "Navržené pořadí oprav",
        "footer": ("Snímek stavu pořízen {when}. Report je čtecí — žádná z uvedených oprav "
                   "nebyla provedena, každá vyžaduje samostatné schválení. Provedené zásahy "
                   "popisuje samostatný záznam `*-intervention.md`."),
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


def cell(v):
    """Text for a table cell: no line breaks, pipe characters escaped."""
    return " ".join(str(v if v is not None else "").split()).replace("|", "\\|")


def para(v):
    return " ".join(str(v if v is not None else "").split())


def stamp(fmt):
    return datetime.datetime.now().strftime(fmt)


def default_out(data, suffix="check"):
    """hosts/<hostname>/reports/<YYYY-MM-DD_HHMM>-<suffix>.md in the repo root."""
    root = pathlib.Path(__file__).resolve().parents[3]
    host = data.get("hostname") or socket.gethostname()
    d = root / "hosts" / host / "reports"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{stamp('%Y-%m-%d_%H%M')}-{suffix}.md"


def section(title, items, numbered=False):
    if not items:
        return []
    out = ["", f"## {title}", ""]
    for n, x in enumerate(items, 1):
        out.append(f"{n}. {para(x)}" if numbered else f"- {para(x)}")
    return out


def build(d, lang="en"):
    S = STRINGS[lang]
    fnd = sorted(d.get("findings", []),
                 key=lambda f: (SEV.index(f.get("sev", "P4"))
                                if f.get("sev") in SEV else 9))
    counts = {k: sum(1 for f in fnd if f.get("sev") == k) for k in SEV}
    when = d.get("timestamp") or d.get("date") or stamp("%Y-%m-%d %H:%M")
    host = d.get("hostname", S["host"])

    meta = " · ".join(filter(None, [
        d.get("distro"), d.get("kernel"),
        S["uptime"].format(uptime=d["uptime"]) if d.get("uptime") else None]))

    L = ["# " + S["title"].format(host=host), ""]
    L.append(f"**{when}**" + (f" · {meta}" if meta else ""))
    L += ["", "| " + " | ".join(f"{k} {S['sev'][k]}" for k in SEV) + " |",
          "|" + "---:|" * len(SEV),
          "| " + " | ".join(str(counts[k]) for k in SEV) + " |"]

    L += ["", f"## {S['findings']}", ""]
    if not fnd:
        L.append(S["no_findings"])
    else:
        L += [S["table"], "|---:|---|---|---|"]
        for i, f in enumerate(fnd, 1):
            L.append(f'| {i} | **{cell(f.get("sev", "P4"))}** | '
                     f'{cell(f.get("area", "—"))} | {cell(f.get("title", ""))} |')
        L.append("")
        for i, f in enumerate(fnd, 1):
            sev = f.get("sev", "P4")
            area = f' · {para(f["area"])}' if f.get("area") else ""
            L += ["", f'### {i}. {sev} — {para(f.get("title", ""))}',
                  f"*{S['sev'].get(sev, S['sev']['P4'])}{area}*", ""]
            if f.get("detail"):
                L += [para(f["detail"]), ""]
            if f.get("impact"):
                L.append(f'- **{S["impact"]}:** {para(f["impact"])}')
            if f.get("fix"):
                L.append(f'- **{S["fix"]}:** {para(f["fix"])}')

    L += section(S["clean"], d.get("clean", []))
    L += section(S["not_checked"], d.get("not_checked", []))
    L += section(S["next_steps"], d.get("next_steps", []), numbered=True)

    L += ["", "---", "", S["footer"].format(when=when)]
    return "\n".join(L).rstrip() + "\n"


def main():
    ap = argparse.ArgumentParser(description="Markdown report from a system check")
    ap.add_argument("json", help="findings file, or - for stdin")
    ap.add_argument("-o", "--out",
                    help="output file; without it hosts/<host>/reports/<timestamp>-check.md")
    ap.add_argument("--lang", choices=list(STRINGS),
                    help="report language; overrides `language` in hosts/sysadmin.toml "
                         "(default: en)")
    a = ap.parse_args()
    lang = load_language(pathlib.Path(__file__).resolve().parents[3], a.lang)
    raw = sys.stdin.read() if a.json == "-" else open(a.json, encoding="utf-8").read()
    data = json.loads(raw)
    out = pathlib.Path(a.out) if a.out else default_out(data)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build(data, lang), encoding="utf-8")
    print(STRINGS[lang]["written"].format(out=out))


if __name__ == "__main__":
    main()
