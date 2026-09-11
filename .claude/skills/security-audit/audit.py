#!/usr/bin/env python3
"""Markdown report generator for the security audit.

Usage:  python3 audit.py findings.json [-o report.md] [--lang en|cs]
Without -o the path is derived automatically:
    hosts/<hostname>/reports/<YYYY-MM-DD_HHMM>-security.md

The output is Markdown so it can be read on a machine without a browser -
`cat`, `less`, `git diff` between runs. The format is described in SKILL.md.

Report language: --lang overrides `language` in hosts/sysadmin.toml;
a missing file or key means "en". Only headings and labels are localized;
free-text values from the JSON are rendered as given.

The report gets committed: the JSON must never contain a token value, key
contents or a password - only the path, permissions and nature of the finding
(CLAUDE.md §7).
"""

import argparse
import datetime
import json
import pathlib
import socket
import sys
import tomllib

ROOT = pathlib.Path(__file__).resolve().parents[3]

RISK_CODES = ("R1", "R2", "R3", "R4")

# All rendered text. The `cs` entries must stay byte-for-byte identical to the
# original Czech output.
STRINGS = {
    "en": {
        "risk": {
            "R1": "critical",
            "R2": "serious",
            "R3": "defense in depth",
            "R4": "accepted",
        },
        "title": "Security audit — {host}",
        "unknown_host": "host",
        "threat_model": "Threat model",
        "findings": "Findings",
        "no_findings": "No findings.",
        "table_header": "| # | Risk | Area | Finding | Who and from where |",
        "evidence": "Evidence",
        "attacker": "Who and from where",
        "impact": "Impact",
        "fix": "Proposed fix",
        "clean": "Verified and clean",
        "accepted": "Accepted risks",
        "not_checked": "Not checked",
        "next_steps": "Proposed fix order",
        "footer": ("State snapshot taken {when}. The audit is read-only — none of "
                   "the fixes listed has been applied, each requires separate "
                   "approval. Interventions carried out are recorded in a separate "
                   "`*-intervention.md` log."),
        "written": "written: {path}",
    },
    "cs": {
        "risk": {
            "R1": "kritické",
            "R2": "vážné",
            "R3": "obrana do hloubky",
            "R4": "přijaté",
        },
        "title": "Bezpečnostní audit — {host}",
        "unknown_host": "stroj",
        "threat_model": "Model hrozby",
        "findings": "Nálezy",
        "no_findings": "Žádné nálezy.",
        "table_header": "| # | Riz. | Oblast | Nález | Kdo a odkud |",
        "evidence": "Doklad",
        "attacker": "Kdo a odkud",
        "impact": "Dopad",
        "fix": "Návrh řešení",
        "clean": "Ověřeno a v pořádku",
        "accepted": "Přijatá rizika",
        "not_checked": "Nezkontrolováno",
        "next_steps": "Navržené pořadí oprav",
        "footer": ("Snímek stavu pořízen {when}. Audit je čtecí — žádná z uvedených "
                   "oprav nebyla provedena, každá vyžaduje samostatné schválení. "
                   "Provedené zásahy popisuje samostatný záznam `*-intervention.md`."),
        "written": "zapsano: {path}",
    },
}


def load_language(root, override=None):
    """Report language: --lang, else hosts/sysadmin.toml, else "en"."""
    if override:
        return override
    path = root / "hosts" / "sysadmin.toml"
    try:
        with open(path, "rb") as fh:
            lang = tomllib.load(fh).get("language", "en")
    except FileNotFoundError:
        return "en"
    except tomllib.TOMLDecodeError as e:
        sys.exit(f"{path}: invalid TOML: {e}")
    if lang not in STRINGS:
        sys.exit(f"{path}: unsupported language {lang!r}, "
                 f"expected one of: {', '.join(STRINGS)}")
    return lang


def cell(v):
    """Text for a table cell: no line breaks, pipe characters escaped."""
    return " ".join(str(v if v is not None else "").split()).replace("|", "\\|")


def para(v):
    return " ".join(str(v if v is not None else "").split())


def stamp(fmt):
    return datetime.datetime.now().strftime(fmt)


def default_out(data, suffix="security"):
    """hosts/<hostname>/reports/<YYYY-MM-DD_HHMM>-<suffix>.md in the repo root."""
    host = data.get("hostname") or socket.gethostname()
    d = ROOT / "hosts" / host / "reports"
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
    s = STRINGS[lang]
    risk = s["risk"]
    fnd = sorted(d.get("findings", []),
                 key=lambda f: (RISK_CODES.index(f.get("sev", "R4"))
                                if f.get("sev") in RISK_CODES else 9))
    counts = {k: sum(1 for f in fnd if f.get("sev") == k) for k in RISK_CODES}
    when = d.get("timestamp") or d.get("date") or stamp("%Y-%m-%d %H:%M")
    host = d.get("hostname", s["unknown_host"])

    meta = " · ".join(filter(None, [d.get("distro"), d.get("kernel")]))

    L = ["# " + s["title"].format(host=host), ""]
    L.append(f"**{when}**" + (f" · {meta}" if meta else ""))
    L += ["", "| " + " | ".join(f"{k} {risk[k]}" for k in RISK_CODES) + " |",
          "|" + "---:|" * len(RISK_CODES),
          "| " + " | ".join(str(counts[k]) for k in RISK_CODES) + " |"]

    if d.get("threat_model"):
        L += ["", f"## {s['threat_model']}", "", para(d["threat_model"])]

    L += ["", f"## {s['findings']}", ""]
    if not fnd:
        L.append(s["no_findings"])
    else:
        L += [s["table_header"],
              "|---:|---|---|---|---|"]
        for i, f in enumerate(fnd, 1):
            L.append(f'| {i} | **{cell(f.get("sev", "R4"))}** | '
                     f'{cell(f.get("area", "—"))} | {cell(f.get("title", ""))} | '
                     f'{cell(f.get("attacker", "—"))} |')
        L.append("")
        for i, f in enumerate(fnd, 1):
            sev = f.get("sev", "R4")
            area = f' · {para(f["area"])}' if f.get("area") else ""
            L += ["", f'### {i}. {sev} — {para(f.get("title", ""))}',
                  f"*{risk.get(sev, risk['R4'])}{area}*", ""]
            if f.get("detail"):
                L += [para(f["detail"]), ""]
            if f.get("evidence"):
                L.append(f'- **{s["evidence"]}:** {para(f["evidence"])}')
            if f.get("attacker"):
                L.append(f'- **{s["attacker"]}:** {para(f["attacker"])}')
            if f.get("impact"):
                L.append(f'- **{s["impact"]}:** {para(f["impact"])}')
            if f.get("fix"):
                L.append(f'- **{s["fix"]}:** {para(f["fix"])}')

    L += section(s["clean"], d.get("clean", []))
    L += section(s["accepted"], d.get("accepted", []))
    L += section(s["not_checked"], d.get("not_checked", []))
    L += section(s["next_steps"], d.get("next_steps", []), numbered=True)

    L += ["", "---", "", s["footer"].format(when=when)]
    return "\n".join(L).rstrip() + "\n"


def main():
    ap = argparse.ArgumentParser(description="Markdown report from a security audit")
    ap.add_argument("json", help="findings file, or - for stdin")
    ap.add_argument("-o", "--out",
                    help="output file; default hosts/<host>/reports/<timestamp>-security.md")
    ap.add_argument("--lang", choices=sorted(STRINGS),
                    help="report language; overrides `language` in hosts/sysadmin.toml "
                         "(default en)")
    a = ap.parse_args()
    lang = load_language(ROOT, a.lang)
    raw = sys.stdin.read() if a.json == "-" else open(a.json, encoding="utf-8").read()
    data = json.loads(raw)
    out = pathlib.Path(a.out) if a.out else default_out(data)
    out.write_text(build(data, lang), encoding="utf-8")
    print(STRINGS[lang]["written"].format(path=out))


if __name__ == "__main__":
    main()
