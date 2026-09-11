#!/usr/bin/env python3
"""Collector of open items from the report history of one machine.

Usage:  python3 next_steps.py [--host host-1] [--all] [--days 400] [--lang en|cs]

Reads hosts/<hostname>/reports/*.md and prints structured input:
when each type of check last ran, how it turned out, and the verbatim content
of the carried-over sections (Left unresolved, Not checked, Recommended next
steps, ...) with a reference to the source and its age.

The script **only collects**. It does not pair findings with interventions and
recommends nothing - that is the model's job, because pairing is fuzzy and a
script would be confidently wrong. The report formats are described in the
SKILL.md of each skill.

Report language comes from --lang, else from `language` in hosts/sysadmin.toml,
else "en". Section headings are recognised in that language only.
"""

import argparse
import datetime
import pathlib
import re
import socket
import sys
import tomllib

# Report type by the suffix in the file name. The order sets the output order.
TYPES = ["check", "security", "leftovers", "diagnostics", "intervention"]

# Types for which cadence makes sense. An intervention is not a check - it
# happens when there is something to fix, so "no intervention for a long time"
# is not a finding.
CADENCE = ["check", "security", "leftovers"]


# Language-specific grammar. Each language has its own "N days ago" and
# "N reports" forms; the tables below point to them.

def ago_en(days):
    """'today' / '1 day ago' / 'N days ago'."""
    if days == 0:
        return "today"
    return "1 day ago" if days == 1 else f"{days} days ago"


def count_en(n, forms):
    """English form by count: 1 report, 2 reports. forms = (singular, plural)."""
    return f"{n} {forms[0] if n == 1 else forms[1]}"


def ago_cs(days):
    """Czech 'today' / '1 day ago' / 'N days ago'. The singular after 1 has
    its own case ending, so the plural form is never used for 1."""
    if days == 0:
        return "dnes"
    return "před 1 dnem" if days == 1 else f"před {days} dny"


def count_cs(n, forms):
    """Czech form by count: 1, 2-4, 5 and more. forms = (one, few, many)."""
    return f"{n} {forms[0] if n == 1 else forms[1] if 2 <= n <= 4 else forms[2]}"


STRINGS = {
    "en": {
        "ago": ago_en,
        "count": count_en,
        "report_forms": ("report", "reports"),
        "item_forms": ("item", "items"),
        "types": {
            "check": "system check",
            "security": "security audit",
            "leftovers": "application leftovers",
            "diagnostics": "targeted diagnostics",
            "intervention": "intervention log",
        },
        # Sections whose content is carried over to the next session.
        # The key is the heading in the report.
        "carried_over": [
            "Left unresolved",
            "What remains",
            "Not checked",
            "Not searched",
            "Recommended next steps",
            "Proposed fix order",
            "Proposed cleanup order",
        ],
        # Section with the findings table: check/audit/leftovers, intervention.
        "findings_sections": ["Findings", "What was addressed and how"],
        # Column with the item count in the vertical summary table (leftovers).
        "items_column": "Items",
        "host_line": "HOST: {host} — {reports}, {first} to {last} (latest {age})",
        "cadence_title": "== CADENCE ==",
        "col_type": "type",
        "col_last": "last",
        "col_ago": "ago",
        "col_runs": "runs",
        "col_summary": "summary",
        "never": "NEVER",
        "never_note": "never run on this machine",
        "carried_title": "== CARRIED-OVER SECTIONS ==",
        "carried_intro": "Verbatim content of the sections a report handed on. "
                         "'N reports after it' = how many reports were written later.",
        "carried_source": "{age}, {reports} after it",
        "carried_none": "None. Either the history is short, or the reports "
                        "do not write these sections.",
        "findings_title": "== FINDINGS ==",
        "findings_intro": "Latest report of each type. --all prints the whole history.",
        "no_dir": "missing {dir} — this machine has no history yet",
        "no_reports": "no report named <YYYY-MM-DD_HHMM>-<type>.md in {dir}",
    },
    "cs": {
        "ago": ago_cs,
        "count": count_cs,
        "report_forms": ("report", "reporty", "reportů"),
        "item_forms": ("položka", "položky", "položek"),
        "types": {
            "check": "kontrola systému",
            "security": "bezpečnostní audit",
            "leftovers": "zbytky po aplikacích",
            "diagnostics": "cílená diagnostika",
            "intervention": "záznam zásahů",
        },
        "carried_over": [
            "Zůstalo neopravené",
            "Co zbývá",
            "Nezkontrolováno",
            "Neprohledáno",
            "Doporučené další kroky",
            "Navržené pořadí oprav",
            "Navržené pořadí úklidu",
        ],
        "findings_sections": ["Nálezy", "Co se řešilo a jak"],
        "items_column": "Polož",
        "host_line": "STROJ: {host} — {reports}, {first} až {last} (poslední {age})",
        "cadence_title": "== KADENCE ==",
        "col_type": "typ",
        "col_last": "poslední",
        "col_ago": "před",
        "col_runs": "běhů",
        "col_summary": "souhrn",
        "never": "NIKDY",
        "never_note": "na tomhle stroji nikdy neproběhl",
        "carried_title": "== PŘENÁŠENÉ SEKCE ==",
        "carried_intro": "Doslovný obsah sekcí, které si report předal dál. "
                         "'po nich' = kolik reportů vzniklo později.",
        "carried_source": "{age}, po nich {reports}",
        "carried_none": "Žádná. Buď je historie krátká, nebo reporty tyto sekce nepíší.",
        "findings_title": "== NÁLEZY ==",
        "findings_intro": "Poslední report každého typu. Celou historii vypíše --all.",
        "no_dir": "chybí {dir} — na tomhle stroji zatím žádná historie není",
        "no_reports": "v {dir} není žádný report s názvem <RRRR-MM-DD_HHMM>-<typ>.md",
    },
}

FILE_NAME = re.compile(r"^(\d{4}-\d{2}-\d{2})_(\d{2})(\d{2})-([a-z]+)\.md$")
# Severity / confidence codes: P (system check), R (security audit),
# J (leftovers, Czech) and C (leftovers, English).
SEVERITY = re.compile(r"\*\*([PRJC][1-4])\*\*")
CODE_HEADING = re.compile(r"^([PRJC][1-4])\b")
BULLET = re.compile(r"^(?:[-*]\s+|\d+\.\s+)(.*)$")


def age_days(now, when):
    """Number of whole days. Negative (a report from this afternoon) is zero."""
    return max(0, int((now - when).total_seconds() // 86400))


def repo_root():
    """Repository root - three levels above .claude/skills/<skill>/."""
    return pathlib.Path(__file__).resolve().parents[3]


def load_language(root, override):
    """--lang wins; otherwise `language` from hosts/sysadmin.toml; otherwise en."""
    if override:
        return override
    path = root / "hosts" / "sysadmin.toml"
    try:
        with open(path, "rb") as f:
            lang = tomllib.load(f).get("language", "en")
    except FileNotFoundError:
        return "en"
    except tomllib.TOMLDecodeError as e:
        sys.exit(f"{path}: invalid TOML: {e}")
    if lang not in STRINGS:
        sys.exit(f"{path}: unsupported language {lang!r}, "
                 f"expected one of: {', '.join(STRINGS)}")
    return lang


def read_reports(directory):
    """List of reports sorted chronologically, oldest first."""
    out = []
    for p in sorted(directory.glob("*.md")):
        m = FILE_NAME.match(p.name)
        if not m:
            continue
        day, hh, mm, rtype = m.groups()
        try:
            when = datetime.datetime.strptime(f"{day} {hh}:{mm}", "%Y-%m-%d %H:%M")
        except ValueError:
            continue
        out.append({
            "path": p,
            "when": when,
            "type": rtype,
            "text": p.read_text(encoding="utf-8"),
        })
    return sorted(out, key=lambda r: r["when"])


def sections(text):
    """Split into sections by '## '. Returns {heading: [lines]}."""
    out, heading, buf = {}, None, []
    for line in text.splitlines():
        if line.startswith("## "):
            if heading is not None:
                out[heading] = buf
            heading, buf = line[3:].strip(), []
        elif heading is not None:
            buf.append(line)
    if heading is not None:
        out[heading] = buf
    return out


def items(lines):
    """Bullets and numbered points of a section. Stops at '---' - the footer follows."""
    out = []
    for line in lines:
        s = line.strip()
        if s.startswith("---"):
            break  # horizontal rule before the report footer
        if not s or s.startswith(("|", "#", ">", "```")):
            continue
        m = BULLET.match(s)
        out.append(m.group(1).strip() if m else s)
    return out


def cells(line):
    """Cells of one table row, or None when the line is not a table row."""
    s = line.strip()
    if not s.startswith("|"):
        return None
    return [c.strip() for c in s.strip("|").split("|")]


def is_separator(row):
    return row is not None and all(set(c) <= set("-: ") for c in row)


def summary(text, S):
    """Counter from the report's opening table: 'P1 0 · P2 2 · ...'.

    Two shapes: horizontal (check, audit, intervention - header with the
    numbers below it) and vertical (leftovers - confidence code in the first
    column, count in the Items column).
    """
    lines = text.splitlines()
    header, data = None, []
    for line in lines:
        row = cells(line)
        if row is None:
            if header is not None and data:
                break  # the table ended
            continue
        if is_separator(row):
            continue
        if header is None:
            header = row
        else:
            data.append(row)
    if not header or not data:
        return ""

    codes = [SEVERITY.match(c) for c in (r[0] for r in data)]
    if all(codes):  # vertical shape
        try:
            col = next(j for j, h in enumerate(header) if S["items_column"] in h)
        except StopIteration:
            col = 1
        return " · ".join(f"{m.group(1)} {r[col]}"
                          for m, r in zip(codes, data) if col < len(r))

    first = data[0]  # horizontal shape
    if len(first) == len(header) and all(c.isdigit() for c in first):
        # A severity legend cell is "P1 meaning" -> keep the code; a status
        # cell may be several words ("not done") -> keep it whole.
        return " · ".join(f"{m.group(1) if (m := CODE_HEADING.match(h)) else h} {v}"
                          for h, v in zip(header, first))
    return ""


def findings(report, S):
    """Rows of the findings table: (tag, area, description).

    The tag is P#/R# from the bold column (check, audit), the status from the
    Status column (intervention), or J#/C# from a subheading such as
    '### C1 — proven' (leftovers).
    """
    s = sections(report["text"])
    lines = []
    for name in S["findings_sections"]:
        if s.get(name):
            lines = s[name]
            break
    subheading, header = None, None
    out = []
    for i, line in enumerate(lines):
        if line.startswith("### "):
            m = CODE_HEADING.match(line[4:].strip())
            subheading = m.group(1) if m else None
            continue
        row = cells(line)
        if row is None:
            header = None  # the table ended
            continue
        if is_separator(row):
            continue
        if is_separator(cells(lines[i + 1])) if i + 1 < len(lines) else False:
            header = row
            continue
        # A findings row is recognised by the header '| # | ...'. Without that,
        # helper tables from the details under a finding would get in too.
        if not header or header[0] != "#" or len(row) < 3:
            continue
        m = SEVERITY.search(" ".join(row))
        if m:
            out.append((m.group(1), row[2], row[3] if len(row) > 3 else ""))
        elif subheading:  # leftovers: code from the subheading, path + verdict
            out.append((subheading, row[1], f"{row[2]} → {row[-1]}"))
        else:
            out.append((row[1], row[2], row[3] if len(row) > 3 else ""))
    return out


def render(reports, host, show_all, now, S):
    ago, count = S["ago"], S["count"]
    L = []
    first, last = reports[0], reports[-1]
    L += [
        S["host_line"].format(
            host=host,
            reports=count(len(reports), S["report_forms"]),
            first=f"{first['when']:%Y-%m-%d}",
            last=f"{last['when']:%Y-%m-%d}",
            age=ago(age_days(now, last["when"]))),
        "",
        S["cadence_title"],
        "",
        f"{S['col_type']:<22} {S['col_last']:<12} {S['col_ago']:>7}  "
        f"{S['col_runs']:>5}  {S['col_summary']}",
    ]
    for rtype in TYPES + sorted(set(r["type"] for r in reports) - set(TYPES)):
        runs = [r for r in reports if r["type"] == rtype]
        label = S["types"].get(rtype, rtype)
        if not runs:
            # A check that never ran on this machine is a finding in itself -
            # there is nothing to compare with and nobody knows what is inside.
            # Types outside CADENCE (diagnostics runs on request) never report "never".
            if rtype in CADENCE:
                L.append(f"{label:<22} {S['never']:<12} {'—':>7}  {0:>5}  "
                         f"{S['never_note']}")
            continue
        p = runs[-1]
        L.append(f"{label:<22} {p['when']:%Y-%m-%d}   "
                 f"{age_days(now, p['when']):>5} d  {len(runs):>5}  "
                 f"{summary(p['text'], S)}")

    L += ["", S["carried_title"], "", S["carried_intro"], ""]
    nothing = True
    for i, r in enumerate(reports):
        s = sections(r["text"])
        for heading in S["carried_over"]:
            if heading not in s:
                continue
            points = items(s[heading])
            if not points:
                continue
            nothing = False
            source = S["carried_source"].format(
                age=ago(age_days(now, r["when"])),
                reports=count(len(reports) - i - 1, S["report_forms"]))
            L.append(f"[{r['when']:%Y-%m-%d %H:%M} · {r['path'].name} · {heading}]"
                     f"  {source}")
            for b in points:
                L.append(f"    - {b}")
            L.append("")
    if nothing:
        L.append(S["carried_none"])

    L += ["", S["findings_title"], ""]
    selected = reports if show_all else [
        [r for r in reports if r["type"] == t][-1]
        for t in dict.fromkeys(r["type"] for r in reports)
    ]
    if not show_all:
        L.append(S["findings_intro"])
        L.append("")
    for r in sorted(selected, key=lambda r: r["when"]):
        rows = findings(r, S)
        L.append(f"[{r['when']:%Y-%m-%d %H:%M} · {r['path'].name}] "
                 + count(len(rows), S["item_forms"]))
        for tag, area, desc in rows:
            L.append(f"    {tag:<12} {area:<16} {desc}")
        L.append("")

    return "\n".join(L).rstrip() + "\n"


def main():
    ap = argparse.ArgumentParser(
        description="Collect open items from the report history of one machine")
    ap.add_argument("--host", default=socket.gethostname(),
                    help="machine hostname; defaults to this machine")
    ap.add_argument("--all", action="store_true",
                    help="print findings from all reports, not only the latest of each type")
    ap.add_argument("--days", type=int,
                    help="limit the history to the last N days")
    ap.add_argument("--lang", choices=sorted(STRINGS),
                    help="report language; overrides `language` in hosts/sysadmin.toml "
                         "(default en)")
    a = ap.parse_args()

    root = repo_root()
    S = STRINGS[load_language(root, a.lang)]

    directory = root / "hosts" / a.host / "reports"
    if not directory.is_dir():
        sys.exit(S["no_dir"].format(dir=directory))

    reports = read_reports(directory)
    now = datetime.datetime.now()
    if a.days:
        limit = now - datetime.timedelta(days=a.days)
        reports = [r for r in reports if r["when"] >= limit]
    if not reports:
        sys.exit(S["no_reports"].format(dir=directory))

    sys.stdout.write(render(reports, a.host, a.all, now, S))


if __name__ == "__main__":
    main()
