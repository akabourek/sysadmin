#!/usr/bin/env python3
"""Markdown report generator for leftovers of uninstalled applications.

Usage:  python3 leftovers.py findings.json [-o report.md] [--lang en|cs]
Without -o the path is derived automatically:
    hosts/<hostname>/reports/<YYYY-MM-DD_HHMM>-leftovers.md

Findings are sorted by CONFIDENCE, not by severity: for orphans the question
is "am I sure about this?", not "how much does it hurt". The JSON format is
described in SKILL.md.

Language: --lang overrides `language` in hosts/sysadmin.toml; if neither is
set, the report is in English.

Confidence tiers: the JSON always uses C1-C4. The English report renders them
as C1-C4, the Czech report as J1-J4. J1-J4 in the JSON are accepted as aliases
of C1-C4; any other or missing value is counted as C3.
"""

import argparse
import datetime
import json
import pathlib
import socket
import sys
import tomllib

TIERS = ("C1", "C2", "C3", "C4")

# Accepted input codes -> canonical tier.
ALIASES = {**{t: t for t in TIERS}, "J1": "C1", "J2": "C2", "J3": "C3", "J4": "C4"}

# What may count towards "reclaimable space". C4 is not an orphan and C3 is
# only a hypothesis — adding them into one number would turn an estimate into
# a promise.
RECLAIMABLE = ("C1", "C2")

# All human-readable output. The `cs` entries are the original Czech strings,
# byte for byte.
STRINGS = {
    "en": {
        "code": {"C1": "C1", "C2": "C2", "C3": "C3", "C4": "C4"},
        "tier": {
            "C1": "confirmed",
            "C2": "probable",
            "C3": "candidate",
            "C4": "false alarm",
        },
        "host_fallback": "host",
        "title": "# Application leftovers — {host}",
        "summary_head": "| Confidence | Meaning | Items | Size |",
        "summary": ("Confirmed by evidence ({c1}): **{s1}**. "
                    "Including probable ({c1}+{c2}): **{s12}**. "
                    "The total is not a recommendation to delete — the "
                    "*Verdict* column decides each item."),
        "inventory": "Inventory",
        "inventory_intro": ("What the orphans were compared against. Anything "
                            "missing from the inventory produces false positives."),
        "findings": "Findings",
        "no_items": "No leftovers found.",
        "items_head": "| # | Area | Path / object | Size | Last used | Evidence | Verdict |",
        "details": "Details",
        "clean": "Verified, not an orphan",
        "not_checked": "Not searched",
        "next_steps": "Proposed cleanup order",
        "footer": ("Snapshot taken {when}. This report is read-only — **nothing "
                   "listed here has been deleted.** Every deletion is a separate "
                   "task with approval under CLAUDE.md §3a and is recorded in "
                   "`*-intervention.md`. {c3} items are heuristics, not findings: "
                   "the user decides on them."),
        "written": "written: {out}",
    },
    "cs": {
        "code": {"C1": "J1", "C2": "J2", "C3": "J3", "C4": "J4"},
        "tier": {
            "C1": "doloženo",
            "C2": "pravděpodobné",
            "C3": "kandidát",
            "C4": "falešný poplach",
        },
        "host_fallback": "stroj",
        "title": "# Zbytky po aplikacích — {host}",
        "summary_head": "| Jistota | Význam | Položek | Zabráno |",
        "summary": ("Doloženo evidencí ({c1}): **{s1}**. "
                    "Včetně pravděpodobných ({c1}+{c2}): **{s12}**. "
                    "Součet není doporučení ke smazání — o každé položce rozhoduje "
                    "sloupec *Verdikt*."),
        "inventory": "Inventura",
        "inventory_intro": ("Proti čemu se sirotci porovnávali. Co v inventuře chybí, "
                            "vyrábí falešně pozitivní nálezy."),
        "findings": "Nálezy",
        "no_items": "Žádné zbytky nenalezeny.",
        "items_head": "| # | Oblast | Cesta / objekt | Velikost | Naposledy | Doklad | Verdikt |",
        "details": "Podrobnosti",
        "clean": "Ověřeno a není sirotek",
        "not_checked": "Neprohledáno",
        "next_steps": "Navržené pořadí úklidu",
        "footer": ("Snímek pořízen {when}. Report je čtecí — **nic z uvedeného nebylo "
                   "smazáno.** Každé smazání je samostatné zadání se schválením podle "
                   "CLAUDE.md §3a a zapisuje se do `*-intervention.md`. Položky {c3} jsou "
                   "heuristika, ne zjištění: o nich rozhoduje uživatel."),
        "written": "zapsano: {out}",
    },
}


def load_language(root, override=None):
    """Report language: --lang, else hosts/sysadmin.toml, else "en"."""
    lang = override
    if lang is None:
        cfg = pathlib.Path(root) / "hosts" / "sysadmin.toml"
        try:
            with cfg.open("rb") as f:
                lang = tomllib.load(f).get("language")
        except FileNotFoundError:
            lang = None
        except tomllib.TOMLDecodeError as e:
            sys.exit(f"{cfg}: {e}")
    lang = lang or "en"
    if lang not in STRINGS:
        sys.exit(f"unsupported language {lang!r}; expected one of: {', '.join(STRINGS)}")
    return lang


def cell(v):
    """Table cell text: no line breaks, pipe escaped."""
    return " ".join(str(v if v is not None else "").split()).replace("|", "\\|")


def para(v):
    return " ".join(str(v if v is not None else "").split())


def code(v):
    """Path in a table cell. Backticks inside the path would break formatting."""
    t = cell(v).replace("`", "")
    return f"`{t}`" if t else "—"


def human(kb):
    """Size from `du -sk` (kilobytes) in readable form."""
    if not isinstance(kb, (int, float)) or kb <= 0:
        return "—"
    for unit, div in (("GB", 1024 * 1024), ("MB", 1024), ("kB", 1)):
        if kb >= div:
            v = kb / div
            return f"{v:.1f} {unit}" if v < 10 and unit != "kB" else f"{v:.0f} {unit}"
    return "—"


def stamp(fmt):
    return datetime.datetime.now().strftime(fmt)


def default_out(data, suffix="leftovers"):
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
    s = STRINGS[lang]
    items = d.get("items", [])
    for i, it in enumerate(items, 1):
        it["_n"] = i
    by_tier = {k: [x for x in items if ALIASES.get(x.get("confidence")) == k] for k in TIERS}
    unknown = [x for x in items if x.get("confidence") not in ALIASES]
    if unknown:
        by_tier["C3"] = by_tier["C3"] + unknown

    def total(rows):
        return sum(r.get("kb", 0) or 0 for r in rows)

    def label(v):
        """Tier code as shown in this language; unknown values are shown as given."""
        return s["code"][ALIASES[v]] if v in ALIASES else v

    when = d.get("timestamp") or d.get("date") or stamp("%Y-%m-%d %H:%M")
    host = d.get("hostname", s["host_fallback"])
    meta = " · ".join(filter(None, [d.get("distro"), d.get("kernel")]))

    L = [s["title"].format(host=host), ""]
    L.append(f"**{when}**" + (f" · {meta}" if meta else ""))

    L += ["", s["summary_head"], "|---|---|---:|---:|"]
    for k in TIERS:
        L.append(f"| **{s['code'][k]}** | {s['tier'][k]} | {len(by_tier[k])} "
                 f"| {human(total(by_tier[k]))} |")
    L += ["",
          s["summary"].format(
              c1=s["code"]["C1"], c2=s["code"]["C2"],
              s1=human(total(by_tier["C1"])),
              s12=human(total([r for t in RECLAIMABLE for r in by_tier[t]])))]

    if d.get("inventory"):
        L += ["", f"## {s['inventory']}", "", s["inventory_intro"], ""]
        for x in d["inventory"]:
            L.append(f"- {para(x)}")

    L += ["", f"## {s['findings']}"]
    if not items:
        L += ["", s["no_items"]]
    for k in TIERS:
        rows = by_tier[k]
        if not rows:
            continue
        L += ["", f"### {s['code'][k]} — {s['tier'][k]}", ""]
        L += [s["items_head"],
              "|---:|---|---|---:|---|---|---|"]
        for r in rows:
            L.append(
                f'| {r["_n"]} | {cell(r.get("area", "—"))} | {code(r.get("path"))} '
                f'| {human(r.get("kb", 0))} | {cell(r.get("last_used", "—"))} '
                f'| {cell(r.get("evidence", ""))} | {cell(r.get("verdict", ""))} |')

    detailed = [x for x in items if x.get("detail")]
    if detailed:
        L += ["", f"## {s['details']}", ""]
        for r in detailed:
            L += [f'### {r["_n"]}. {para(r.get("path", ""))}',
                  f'*{label(r.get("confidence", "C3"))} · {para(r.get("area", "—"))}*', "",
                  para(r["detail"]), ""]

    L += section(s["clean"], d.get("clean", []))
    L += section(s["not_checked"], d.get("not_checked", []))
    L += section(s["next_steps"], d.get("next_steps", []), numbered=True)

    L += ["", "---", "", s["footer"].format(when=when, c3=s["code"]["C3"])]
    return "\n".join(L).rstrip() + "\n"


def main():
    ap = argparse.ArgumentParser(description="Markdown report of application leftovers")
    ap.add_argument("json", help="findings file, or - for stdin")
    ap.add_argument("-o", "--out",
                    help="output file; without it hosts/<host>/reports/<timestamp>-leftovers.md")
    ap.add_argument("--lang", choices=sorted(STRINGS),
                    help="report language; overrides `language` in hosts/sysadmin.toml "
                         "(default: en)")
    a = ap.parse_args()
    raw = sys.stdin.read() if a.json == "-" else open(a.json, encoding="utf-8").read()
    data = json.loads(raw)
    lang = load_language(pathlib.Path(__file__).resolve().parents[3], a.lang)
    out = pathlib.Path(a.out) if a.out else default_out(data)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build(data, lang), encoding="utf-8")
    print(STRINGS[lang]["written"].format(out=out))


if __name__ == "__main__":
    main()
