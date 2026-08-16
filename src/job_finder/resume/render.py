"""Render a per-posting tailored résumé PDF from master + curate selection.

Pipeline (cost: $0 — no LLM, no API):

    1. Read master profile/resume.md
    2. Read applications.curate_payload (or .tailored_bullets for tailor mode)
    3. Trim master sections matching `dropped_projects`
    4. Bold lines that match `emphasis_quotes` verbatim
    5. Markdown → HTML (markdown-it-py, CommonMark + GFM tables)
    6. HTML → PDF (xhtml2pdf, pure-Python, no native deps)

The output PDF is ATS-readable (single column, plain Helvetica, no fancy
graphics) and lands in `artifacts/resumes/<slug>.pdf` by default.
"""

from __future__ import annotations

import functools
import io
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from markdown_it import MarkdownIt
from xhtml2pdf import pisa

from ..config import ROOT_DIR
from ..db import aconn
from ..logging_config import get_logger

log = get_logger(__name__)

DEFAULT_RESUMES_DIR = ROOT_DIR / "artifacts" / "resumes"
DEFAULT_PROFILE_DIR = ROOT_DIR / "profile"


# ─────────────────────────────────────────────────────────────────────────────
# Print CSS — clean ATS-friendly single-column layout. Keep this conservative
# (no flexbox, no grid, no custom fonts) so xhtml2pdf renders predictably.
# ─────────────────────────────────────────────────────────────────────────────

_PRINT_CSS = """
@page {
    size: letter;
    margin: 0.5in 0.55in 0.5in 0.55in;
}
body {
    font-family: Helvetica, Arial, sans-serif;
    font-size: 9.5pt;
    line-height: 1.25;
    color: #000000;
}
h1 { font-size: 17pt; margin: 0 0 1pt 0; padding: 0; font-weight: bold; }
h2 {
    font-size: 10.5pt;
    font-weight: bold;
    text-transform: uppercase;
    letter-spacing: 0.6pt;
    color: #000000;
    margin: 9pt 0 3pt 0;
    border: 0;
    padding: 0;
}
h3 { font-size: 10pt; font-weight: bold; margin: 5pt 0 1pt 0; color: #000000; }
h4 { font-size: 9.5pt; font-weight: bold; margin: 3pt 0 1pt 0; color: #000000; }
p  { margin: 1pt 0 2pt 0; }
ul { margin: 1pt 0 2pt 13pt; padding: 0; }
li { margin-bottom: 0.5pt; }
strong { font-weight: bold; }
em { font-style: italic; }
hr { border: 0; border-top: 0.5pt solid #cccccc; margin: 3pt 0; }
.tailoring-banner {
    background: #f0f4f8;
    border-left: 3pt solid #2a4258;
    padding: 5pt 7pt;
    margin: 0 0 8pt 0;
    font-size: 8pt;
    color: #555;
}
blockquote {
    border-left: 2pt solid #ccc;
    margin: 3pt 0;
    padding: 1pt 7pt;
    color: #555;
    font-size: 9pt;
}
code { font-family: "Courier New", monospace; font-size: 9pt; }
"""


# ─────────────────────────────────────────────────────────────────────────────
# Master-trimming logic
# ─────────────────────────────────────────────────────────────────────────────

# Maps project slug → list of header phrases that should match in the master's
# detailed-project sections. Match is case-insensitive substring of header.
_SLUG_TO_HEADER_KEYWORDS: dict[str, list[str]] = {
    "capstone-bell412":   ["bell-412", "bell 412", "ece496", "capstone"],
    "gnssdeny":            ["gnss-denied", "gnss denied", "gps-denied", "gnssdeny"],
    "5gcx":                ["5gcx", "pilot ai evaluation", "5gcx pilot eye-tracking"],
    "vimy-overview":       ["vimy systèmes", "vimy systemes", "head of engineering"],
    "tenstorrent":         ["tenstorrent", "qualification engineering"],
    "finalfusion":         ["finalfusion", "final fusion", "multi-modal sensor fusion"],
    "limiliminal":         ["limiliminal"],
    "reel-block":          ["reel_block", "reel block", "instagram reels"],
    "redline":             ["redline"],
    "genius-activities":   ["geniusactivities", "genius activities", "ibkr"],
    "pokemon-dcgan":       ["pokémon dcgan", "pokemon dcgan", "dcgan"],
    "myDrumpad":           ["mydrumpad", "drumpad"],
    "drone-bom-linker":    ["drone-bom-linker", "drone bom"],
    "pinball":             ["pinball"],
}

# h2 sections under which h3 trimming is ALLOWED. Sections like "Experience"
# and "Education" are operator history — never auto-trim job entries even if
# the curate model lists them as "dropped" (it does, naively).
_TRIMMABLE_H2_SECTIONS: frozenset[str] = frozenset({
    "flagship project",
    "selected personal projects",
})

# h2 sections to drop entirely from rendered output (regardless of mode):
# - Languages / Selected Public Links duplicate the contact header.
_ALWAYS_DROP_H2: frozenset[str] = frozenset({
    "languages",
    "selected public links",
})

# h3 entries to drop ANYWHERE they appear, even under protected h2 sections
# like Experience. These are entries that read as filler / padding rather
# than verifiable work history (e.g. the 1-month "Independent Contractor"
# pre-formalization period at a firm Mohammad co-founded).
_DROP_H3_KEYWORDS: tuple[str, ...] = (
    "independent contractor",
    "technical advisor",
)

# Skill items to strip from any Skills bullet/line, regardless of variant.
# These are tools-used-once or trivially-anyone items that read weakly at
# senior levels (per the "résumé bloat" rule of thumb).
_SKILL_BLACKLIST: tuple[str, ...] = (
    "Spline 3D embeds",
    "Vercel Analytics",
    "ESLint",
    "Anthropic API (Haiku, Sonnet)",
    "Anthropic API",
    "LaTeX",
)

# Whole lines to drop verbatim (substring match). These are self-narrating /
# defensive / cross-reference lines that don't belong on a polished résumé.
_DROP_LINE_SUBSTRINGS: tuple[str, ...] = (
    "Compensation is a hybrid",
    "cross-referenced with company experience above",
    "Pre-formalization advisory engagement",
    "Public framing only — implementation specifics governed by partner NDA",
    "Public-facing framing only",
    "omitted from this résumé to avoid recursion",
)

# Per-h3-section bullet caps (overrides the global default). Vimy gets a
# tighter cap because the section has many proposal-stage / awaiting-decision
# bullets that don't carry weight.
_H3_BULLET_CAP_OVERRIDES: dict[str, int] = {
    "co-founder & engineering lead": 4,
    "founding engineer": 4,
    "head of engineering": 4,  # back-compat in case master regresses
}

# Skill-line label → variants where it should be KEPT. Lines whose label isn't
# in any kept-set for the current variant are dropped from the Skills section.
# A line is "label: <text>" or "**label** <text>" — we match on the first ~40
# chars case-insensitively. Variants come from `suggested_resume_variant`.
_SKILLS_KEEP_BY_VARIANT: dict[str, set[str]] = {
    "ml_graphics": {
        "languages", "robotics", "ai / ml", "backend", "web", "defence", "tooling",
    },
    "graphics": {
        "languages", "ai / ml", "web", "tooling", "backend",
    },
    "systems_5g": {
        "languages", "robotics", "backend", "defence", "tooling",
        "mobile", "embedded",
    },
    "web": {
        "languages", "web", "backend", "tooling", "ai / ml",
    },
    "generic": set(),  # empty = keep all
}


@dataclass(slots=True)
class ResumeRenderInputs:
    posting_id: int
    posting_title: str
    company_name: str
    draft_mode: str  # 'tailor' | 'curate' | (None means render plain master)
    selected_slugs: list[str]   # empty = include everything
    dropped_slugs: list[str]
    emphasis_quotes: list[str]
    tailored_bullets: list[dict[str, str]]  # tailor-mode only
    suggested_resume_variant: str | None
    # New (April 2026, curate-only): per-posting Summary + Skills overrides
    tailored_summary: str = ""             # replaces master Summary if non-empty
    skills_order: list[str] | None = None  # category labels in priority order
    skills_item_order: dict[str, list[str]] | None = None  # within-category


async def _fetch_inputs(posting_id: int) -> ResumeRenderInputs:
    async with aconn() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT a.draft_mode,
                       a.tailored_bullets,
                       a.curate_payload,
                       p.title AS posting_title,
                       c.name  AS company_name
                FROM postings p
                JOIN companies c ON c.id = p.company_id
                LEFT JOIN applications a ON a.posting_id = p.id
                WHERE p.id = %s
                """,
                (posting_id,),
            )
            r = await cur.fetchone()
    if r is None:
        raise ValueError(f"posting {posting_id} not found")
    cp = r.get("curate_payload") or {}
    return ResumeRenderInputs(
        posting_id=posting_id,
        posting_title=r["posting_title"],
        company_name=r["company_name"],
        draft_mode=r.get("draft_mode") or "",
        selected_slugs=list(cp.get("selected_projects") or []),
        dropped_slugs=list(cp.get("dropped_projects") or []),
        emphasis_quotes=[q["quote"] for q in (cp.get("emphasis_quotes") or []) if isinstance(q, dict)],
        tailored_bullets=list(r.get("tailored_bullets") or []),
        suggested_resume_variant=cp.get("suggested_resume_variant") if cp else None,
        tailored_summary=str(cp.get("tailored_summary") or ""),
        skills_order=list(cp.get("skills_order") or []) or None,
        skills_item_order=dict(cp.get("skills_item_order") or {}) or None,
    )


def _header_matches_slug(header_text: str, slug: str) -> bool:
    keywords = _SLUG_TO_HEADER_KEYWORDS.get(slug, [slug])
    h = header_text.lower()
    return any(k.lower() in h for k in keywords)


def _trim_dropped_sections(md: str, dropped_slugs: list[str]) -> str:
    """Remove h3/h4 markdown sections whose header matches any dropped slug,
    but ONLY when the current parent h2 is in `_TRIMMABLE_H2_SECTIONS`.

    Operator history (Experience / Education / Summary) is NEVER auto-trimmed
    even if the curate model lists those h3s as "dropped" — those are real
    employment entries, not toggleable projects.
    """
    if not dropped_slugs:
        return md
    lines = md.split("\n")
    out: list[str] = []
    current_h2_slug = ""
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        h2 = re.match(r"^##\s+(.*)$", line)
        if h2 and not h2.group(1).startswith("#"):
            current_h2_slug = h2.group(1).strip().lower()
            out.append(line)
            i += 1
            continue
        h3 = re.match(r"^(#{3,4})\s+(.*)$", line)
        if (
            h3
            and current_h2_slug in _TRIMMABLE_H2_SECTIONS
            and any(_header_matches_slug(h3.group(2), s) for s in dropped_slugs)
        ):
            level = len(h3.group(1))
            i += 1
            while i < n:
                nxt = lines[i]
                if re.match(rf"^#{{1,{level}}}\s+", nxt):
                    break
                i += 1
            continue
        out.append(line)
        i += 1
    return "\n".join(out)


def _strip_polish(md: str, *, variant: str | None, drop_additional_projects: bool) -> str:
    """Remove sections / lines that don't belong on a polished, ready-to-send
    résumé regardless of mode.

    Always:
      - Drops the leading `> Naming note: ...` blockquote (HR-form info, not résumé)
      - Drops `## Languages` and `## Selected Public Links` h2 sections
        (they duplicate the contact header)
      - Drops the IB Extended Essay topic line (high-school trivia)
      - Trims `Selected coursework:` to the first ~5 entries

    Variant-conditional:
      - Drops `## Additional Projects` for non-generic variants (course
        projects don't add signal for senior roles in robotics/AI/etc.)
      - Filters Skills lines per `_SKILLS_KEEP_BY_VARIANT[variant]`
    """
    lines = md.split("\n")
    out: list[str] = []
    i = 0
    n = len(lines)
    in_skills = False
    keep_skills = _SKILLS_KEEP_BY_VARIANT.get(variant or "", set())
    skills_filter_active = bool(keep_skills)  # empty set = keep all

    while i < n:
        line = lines[i]
        h2 = re.match(r"^##\s+(.*)$", line)
        if h2:
            h2_slug = h2.group(1).strip().lower()
            # Drop entire section (header + content until next h2)?
            should_drop = (
                h2_slug in _ALWAYS_DROP_H2
                or (h2_slug == "additional projects" and drop_additional_projects)
            )
            if should_drop:
                i += 1
                while i < n and not re.match(r"^##\s+(?!#)", lines[i]):
                    i += 1
                continue
            in_skills = (h2_slug == "skills")
            out.append(line)
            i += 1
            continue

        # Drop blacklisted h3 entries (e.g. Independent Contractor / Technical
        # Advisor) wherever they appear — even inside protected sections like
        # Experience. The header + everything up to the next same-or-shallower
        # header gets removed.
        h3 = re.match(r"^(#{3,4})\s+(.*)$", line)
        if h3 and any(k in h3.group(2).lower() for k in _DROP_H3_KEYWORDS):
            level = len(h3.group(1))
            i += 1
            while i < n:
                if re.match(rf"^#{{1,{level}}}\s+", lines[i]):
                    break
                i += 1
            continue

        # Drop self-narrating / defensive / cross-reference lines verbatim
        if any(s in line for s in _DROP_LINE_SUBSTRINGS):
            i += 1
            continue

        # Strip the broken "(see flagship project below)" cross-reference.
        # Also any analogous cross-refs that point at sections that may have
        # been trimmed in some renders.
        if "(see flagship project below)" in line:
            line = line.replace(" *(see flagship project below)*", "").replace("(see flagship project below)", "")

        # Drop the naming-note blockquote (and its continuation lines) —
        # passport-vs-email spelling is HR-form info, not résumé content.
        # Stripped again June 2026 per operator request (was kept April 2026).
        if line.lstrip().startswith("> Naming note:"):
            i += 1
            while i < n and lines[i].lstrip().startswith(">"):
                i += 1
            continue

        # Drop the IB Extended Essay topic line (English-Lit trivia)
        if "Extended Essay" in line:
            i += 1
            continue

        # Trim "Selected coursework:" line to the first 5 entries.
        # Master is `- **Selected coursework:** ECE344 · ECE297 · ...`. The
        # `**` after the colon is the closing bold tag — must be preserved
        # so markdown→HTML renders the label bold and the entries plain.
        if "Selected coursework:" in line:
            m = re.match(r"^(\s*-\s*\*\*Selected coursework:\*\*\s*)(.*)$", line)
            if m:
                head, tail = m.group(1), m.group(2)
                entries = [e.strip() for e in tail.split("·") if e.strip()]
                line = head + " · ".join(entries[:5])
            out.append(line)
            i += 1
            continue

        # Variant-aware Skills filter: master uses two-line format —
        #   **Label**
        #   content · with · dots
        # When a label doesn't match the variant's keep-set, drop the label
        # line PLUS everything up to (but not including) the next bold label
        # or h2/hr.
        if in_skills and skills_filter_active:
            label_match = re.match(r"^\s*\*\*([^*]+)\*\*\s*$", line)
            if label_match:
                label = label_match.group(1).strip().lower()
                if not any(k in label for k in keep_skills):
                    i += 1
                    while i < n:
                        nxt = lines[i]
                        if (re.match(r"^\s*\*\*[^*]+\*\*\s*$", nxt)
                                or re.match(r"^##\s+", nxt)
                                or nxt.strip().startswith("---")):
                            break
                        i += 1
                    continue

        # Strip individual blacklisted skill items from Skills content lines.
        # Items are " · "-separated. Remove matching items, collapse double
        # separators, drop the line if it becomes empty.
        if in_skills and any(b in line for b in _SKILL_BLACKLIST):
            for b in _SKILL_BLACKLIST:
                line = line.replace(f" · {b}", "").replace(f"{b} · ", "").replace(b, "")
            line = re.sub(r"\s+·\s+·\s+", " · ", line).strip(" ·")
            if not line.strip():
                i += 1
                continue

        out.append(line)
        i += 1

    return "\n".join(out)


# Engineering-convention section order: lead with the strongest professional
# signal (Experience → Flagship → Projects), then qualifications (Education),
# then Skills. Section names are matched case-insensitively. Anything not
# listed retains its original relative position at the end.
_SECTION_ORDER: tuple[str, ...] = (
    "summary",
    "experience",
    "flagship project",
    "selected personal projects",
    "additional projects",
    "skills",
    "education",
)


def _reorder_sections(md: str) -> str:
    """Split the master by h2, re-emit in `_SECTION_ORDER` order.

    Pre-h2 content (header line + contact line) is kept at the top untouched.
    Sections not present in the master are skipped silently.
    """
    lines = md.split("\n")
    # Find the index of every h2 header
    h2_idxs = [i for i, line in enumerate(lines) if re.match(r"^##\s+(?!#)", line)]
    if not h2_idxs:
        return md

    pre_h2 = "\n".join(lines[: h2_idxs[0]])
    sections: dict[str, list[str]] = {}
    for k, start in enumerate(h2_idxs):
        end = h2_idxs[k + 1] if k + 1 < len(h2_idxs) else len(lines)
        header = lines[start]
        slug = re.match(r"^##\s+(.*)$", header).group(1).strip().lower()
        sections[slug] = lines[start:end]

    ordered: list[str] = [pre_h2]
    seen: set[str] = set()
    for name in _SECTION_ORDER:
        if name in sections:
            ordered.extend(sections[name])
            seen.add(name)
    # Append any sections we didn't explicitly order (defensive)
    for name, body in sections.items():
        if name not in seen:
            ordered.extend(body)
    return "\n".join(ordered)


def _cap_bullets_per_h3(md: str, max_bullets: int = 5) -> str:
    """Within each h3 section, retain at most `max_bullets` top-level list
    items (or a per-section override from `_H3_BULLET_CAP_OVERRIDES`).
    Sub-bullets and non-bullet content are preserved.

    The master is intentionally long for fidelity; tailored renders cap to
    keep the PDF close to 2 pages. Order in the master controls priority —
    earliest bullets win.
    """
    if max_bullets <= 0:
        return md
    lines = md.split("\n")
    out: list[str] = []
    bullet_count = 0
    current_cap = max_bullets
    for line in lines:
        h = re.match(r"^(#{1,6})\s+(.*)$", line)
        if h:
            bullet_count = 0  # reset on any header
            level = len(h.group(1))
            if level == 3:
                # Look up override for this h3's title; fall back to default
                title = h.group(2).strip().lower()
                current_cap = max_bullets
                for key, override in _H3_BULLET_CAP_OVERRIDES.items():
                    if key in title:
                        current_cap = override
                        break
            elif level <= 2:
                current_cap = max_bullets
            out.append(line)
            continue
        is_top_bullet = bool(re.match(r"^[-*]\s+", line))
        if is_top_bullet:
            bullet_count += 1
            if bullet_count > current_cap:
                continue
        out.append(line)
    return "\n".join(out)


# Term canonicalization: pick one spelling for each interchangeable variant.
# Applied after all other passes so we catch terms regardless of where they
# came from. Order matters — longer-substring rules run first.
_TERM_CANONICALIZATIONS: tuple[tuple[str, str], ...] = (
    ("LIDAR",       "lidar"),
    ("LiDAR",       "lidar"),
    ("Lidar",       "lidar"),
    ("GNSS-denied", "GPS-denied"),
    ("GNSS denied", "GPS-denied"),
    ("GPS denied",  "GPS-denied"),
)


def _normalize_terms(md: str) -> str:
    """Pick one canonical spelling for terms with common variants."""
    for old, new in _TERM_CANONICALIZATIONS:
        md = md.replace(old, new)
    return md


# ─────────────────────────────────────────────────────────────────────────────
# Curated-output presentation fixes (identity, project renames, hedging).
# Apply ONLY to per-posting curated/tailored renders (render_resume_html), never
# to the master PDF or the preset pool résumés (those bake the changes in).
# ─────────────────────────────────────────────────────────────────────────────

# (old, new) substring rewrites for identity / company presentation.
# June 2026: the title rewrite (→ Founding Engineer), founder names, and
# company-history clarifier are now baked into the master; the naming note and
# work-eligibility line are gone from shipped résumés entirely (eligibility
# questions get answered in application forms, not volunteered on the page).
_IDENTITY_REWRITES: tuple[tuple[str, str], ...] = (
    ("[GH](", "[GitHub]("),
    ("[LI](", "[LinkedIn]("),
    ("Head of Engineering", "Founding Engineer"),
    ("Engineering Lead", "Founding Engineer"),
    ("4-person Canadian deep-tech firm", "Toronto-based deep-tech startup"),
)


def _apply_curate_identity(md: str) -> str:
    """Title canonicalization (older titles → Founding Engineer, catching
    model-introduced leaks in tailored summaries), 'Toronto-based startup'
    (no headcount), and GitHub/LinkedIn label expansion. Master stays as-is —
    these are render-time presentation rewrites."""
    for old, new in _IDENTITY_REWRITES:
        md = md.replace(old, new)
    return md


@functools.lru_cache(maxsize=1)
def _load_rename_config() -> tuple[dict[str, str], tuple[str, ...]]:
    """Load resumes/project_names.toml → ({slug: display}, (drop slugs,))."""
    path = ROOT_DIR / "resumes" / "project_names.toml"
    if not path.exists():
        return {}, ()
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    names = {str(k): str(v) for k, v in (data.get("names") or {}).items()}
    drop = tuple(str(s) for s in (data.get("drop") or []))
    return names, drop


def _apply_project_renames(md: str) -> str:
    """Item 12: rename project headers per resumes/project_names.toml (slug
    matched as a substring of an h3/h4 header), and drop sections whose header
    contains a drop-listed slug."""
    names, drop = _load_rename_config()
    for slug, display in names.items():
        pat = re.compile(rf"^(#{{3,4}})\s+.*{re.escape(slug)}.*$", re.MULTILINE)
        md = pat.sub(lambda m, d=display: f"{m.group(1)} {d}", md)
    for slug in drop:
        lines = md.split("\n")
        out: list[str] = []
        i, n = 0, len(lines)
        while i < n:
            h = re.match(r"^(#{3,4})\s+(.*)$", lines[i])
            if h and slug.lower() in h.group(2).lower():
                level = len(h.group(1))
                i += 1
                while i < n and not re.match(rf"^#{{1,{level}}}\s+", lines[i]):
                    i += 1
                continue
            out.append(lines[i])
            i += 1
        md = "\n".join(out)
    return md


def _strip_hedging(md: str) -> str:
    """Item 15: strip diminishing/hedging language. Removes '(secondary
    contribution)' / '(secondary)' parentheticals — KEEPS '(primary…)', whose
    ownership signal is load-bearing — and any '<X>-adjacent' construction.
    The 'public-facing framing only' line is dropped via _DROP_LINE_SUBSTRINGS."""
    for token in (
        " (secondary contribution)", " (secondary)",
        "(secondary contribution)", "(secondary)",
    ):
        md = md.replace(token, "")
    md = re.sub(r"\b\w+-adjacent\b\s*", "", md)
    return md


def _strip_targeting_sentence(md: str) -> str:
    """Item 5 safety-net: delete any leaked 'Targeting … roles.' sentence that
    slips past the prompt rule."""
    return re.sub(r"\s*Targeting\b[^.]*\broles?\b\.?", "", md, flags=re.IGNORECASE)


def _replace_summary(md: str, tailored_summary: str) -> str:
    """Replace the master's `## Summary` section body with `tailored_summary`.

    The h2 header itself stays. Body is everything between `## Summary` and
    the next `## ` (or hr / EOF). No-op if `tailored_summary` is empty.
    """
    if not tailored_summary.strip():
        return md
    lines = md.split("\n")
    out: list[str] = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        if re.match(r"^##\s+Summary\s*$", line, re.IGNORECASE):
            out.append(line)
            out.append("")
            out.append(tailored_summary.strip())
            out.append("")
            i += 1
            # Skip everything until the next h2 or hr
            while i < n and not re.match(r"^##\s+(?!#)", lines[i]):
                if lines[i].strip() == "---":
                    out.append(lines[i])
                    i += 1
                    break
                i += 1
            continue
        out.append(line)
        i += 1
    return "\n".join(out)


def _reorder_skills(
    md: str,
    skills_order: list[str] | None,
    skills_item_order: dict[str, list[str]] | None,
) -> str:
    """Rewrite the `## Skills` section per the curate model's ordering.

    The master uses a two-line format per category:
        **Category Label**
        item · item · item

    Behaviour:
      - If `skills_order` is empty/None: leave Skills section unchanged
        (renderer falls back to existing variant filter elsewhere).
      - If `skills_order` is set:
          * Categories appear in the listed order.
          * Categories NOT in the list are dropped entirely.
          * Within each kept category, if `skills_item_order[label]` is
            present, items are reordered to match (and items absent from
            that list are dropped).
    """
    if not skills_order:
        return md
    skills_item_order = skills_item_order or {}

    lines = md.split("\n")
    n = len(lines)

    # Locate the Skills section
    skills_start = -1
    skills_end = n
    for i, line in enumerate(lines):
        if re.match(r"^##\s+Skills\s*$", line, re.IGNORECASE):
            skills_start = i
            break
    if skills_start == -1:
        return md
    for j in range(skills_start + 1, n):
        if re.match(r"^##\s+(?!#)", lines[j]):
            skills_end = j
            break

    # Parse existing categories: label → list of content lines
    body = lines[skills_start + 1 : skills_end]
    parsed: dict[str, list[str]] = {}
    current_label: str | None = None
    current_content: list[str] = []
    for ln in body:
        m = re.match(r"^\s*\*\*([^*]+)\*\*\s*$", ln)
        if m:
            if current_label is not None:
                parsed[current_label] = current_content
            current_label = m.group(1).strip()
            current_content = []
        elif current_label is not None:
            current_content.append(ln)
    if current_label is not None:
        parsed[current_label] = current_content

    # Rebuild in skills_order; skip categories absent from the master
    rebuilt: list[str] = []
    for label in skills_order:
        if label not in parsed:
            continue
        content_lines = parsed[label]
        # Find the single content line with " · "-separated items
        content = "\n".join(content_lines).strip()
        items_line = content
        # Pull the items line (first non-blank line of content)
        for cl in content_lines:
            if cl.strip():
                items_line = cl.strip()
                break

        if label in skills_item_order and skills_item_order[label]:
            # Reorder by the model's per-category list. Match each desired
            # item against the master's items by case-insensitive substring;
            # keeps verbatim master text but in the desired order. Items the
            # model didn't mention get dropped.
            master_items = [i.strip() for i in items_line.split("·") if i.strip()]
            desired = skills_item_order[label]
            chosen: list[str] = []
            for d in desired:
                d_low = d.lower().strip()
                for mi in master_items:
                    if d_low in mi.lower() and mi not in chosen:
                        chosen.append(mi)
                        break
            if chosen:
                items_line = " · ".join(chosen)

        rebuilt.append(f"**{label}**")
        rebuilt.append(items_line)
        rebuilt.append("")

    new_lines = (
        lines[: skills_start + 1]
        + [""]
        + rebuilt
        + lines[skills_end:]
    )
    return "\n".join(new_lines)


def _drop_empty_h2_sections(md: str) -> str:
    """Drop h2 sections whose body (between this h2 and the next h2) contains
    no non-blank, non-comment content. Prevents dangling 'Experience' headers
    when all h3 children got trimmed.
    """
    lines = md.split("\n")
    out: list[str] = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        if re.match(r"^##\s+(?!#)", line):
            j = i + 1
            has_content = False
            while j < n and not re.match(r"^##\s+(?!#)", lines[j]):
                stripped = lines[j].strip()
                if stripped and not stripped.startswith("---"):
                    has_content = True
                j += 1
            if not has_content:
                i = j
                continue
        out.append(line)
        i += 1
    return "\n".join(out)


def _bold_emphasis_quotes(md: str, quotes: list[str]) -> str:
    """Wrap each verbatim emphasis quote in **bold** so it visually leads.

    Idempotent: skips quotes that already appear bolded (no double-asterisk).
    Quotes are matched as substrings; case-sensitive (they should already be
    verbatim per `verify_curate_quotes`).
    """
    out = md
    for q in quotes:
        q = q.strip()
        if not q or q not in out:
            continue
        # Avoid re-bolding already-bold quotes
        if f"**{q}**" in out:
            continue
        out = out.replace(q, f"**{q}**", 1)
    return out


def _render_tailor_callout(bullets: list[dict[str, str]]) -> str:
    """For tailor mode: render an opening callout block with the LLM-rewritten
    bullets, clearly labelled as tailored.
    """
    if not bullets:
        return ""
    lines = ["", "## Highlights for this role", ""]
    for b in bullets:
        section = b.get("section", "Experience")
        bullet = b.get("bullet", "")
        if bullet:
            lines.append(f"- *[{section}]* {bullet}")
    lines.append("")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Render functions
# ─────────────────────────────────────────────────────────────────────────────

def _md_to_html(md_text: str) -> str:
    """CommonMark + GFM tables. Plain output — no syntax highlighting or
    inline-html plugins (keeps xhtml2pdf happy)."""
    parser = MarkdownIt("commonmark", {"html": False, "breaks": False, "linkify": False})
    return parser.render(md_text)


def render_resume_html(
    inputs: ResumeRenderInputs,
    *,
    profile_dir: Path = DEFAULT_PROFILE_DIR,
    show_banner: bool = False,
) -> str:
    """Build the full HTML document (with print CSS) — pre-PDF rendering.

    `show_banner=True` adds a "Tailored for X · mode: Y" header useful for
    personal review. OFF by default — production-ready PDFs go straight to
    the recruiter and shouldn't tell them an AI tailored the doc.
    """
    master_path = profile_dir / "resume.md"
    if not master_path.exists():
        raise FileNotFoundError(f"master resume not found at {master_path}")
    master = master_path.read_text(encoding="utf-8")

    md = master
    # Identity/company/contact presentation rewrites — applied to the master
    # text early so the exact master strings still match (items 1-4, 17).
    md = _apply_curate_identity(md)
    if inputs.draft_mode == "curate":
        md = _trim_dropped_sections(md, inputs.dropped_slugs)
        md = _bold_emphasis_quotes(md, inputs.emphasis_quotes)
        # Per-posting Summary rewrite (replaces master's static summary).
        # Falls through to master if tailored_summary is empty.
        md = _replace_summary(md, inputs.tailored_summary)
        # Per-posting Skills reorder + drop. Falls through to variant filter
        # below when skills_order is empty (back-compat for old curate rows).
        md = _reorder_skills(md, inputs.skills_order, inputs.skills_item_order)
    elif inputs.draft_mode == "tailor":
        md = _render_tailor_callout(inputs.tailored_bullets) + md

    # Polish pass: strip non-résumé content + variant-aware filtering.
    # If the curate model already supplied skills_order, the variant filter
    # below is a no-op for Skills (categories already culled).
    variant = inputs.suggested_resume_variant
    md = _strip_polish(
        md,
        variant=variant,
        drop_additional_projects=(variant != "generic"),
    )
    # Cap bullets per h3 (engineering convention: tight is better than long)
    md = _cap_bullets_per_h3(md, max_bullets=5)
    # Lead with strongest signal: Experience → Flagship → Projects → Education → Skills
    md = _reorder_sections(md)
    md = _drop_empty_h2_sections(md)
    # Canonicalize term variants (lidar, GPS-denied, …)
    md = _normalize_terms(md)
    # Curated-output presentation fixes: project renames/drops (item 12),
    # hedging strip (item 15), and the targeting-sentence safety-net (item 5).
    md = _apply_project_renames(md)
    md = _strip_hedging(md)
    md = _strip_targeting_sentence(md)
    # Re-apply identity rewrites AFTER summary injection: the curate model can
    # write an outdated title into its tailored_summary despite the prompt, and
    # the early pass ran before that text existed. Idempotent (all replacements
    # no-op if already applied), so this only catches model-introduced leaks.
    md = _apply_curate_identity(md)

    body_html = _md_to_html(md)

    banner = ""
    if show_banner:
        banner = (
            f'<div class="tailoring-banner">'
            f"Tailored for <strong>{inputs.company_name}</strong> · "
            f"<em>{inputs.posting_title}</em> · "
            f"mode: {inputs.draft_mode or 'master'}"
            f"</div>"
        )

    full_html = (
        f"<!DOCTYPE html><html><head>"
        f"<meta charset='utf-8'/>"
        f"<style>{_PRINT_CSS}</style>"
        f"</head><body>"
        f"{banner}"
        f"{body_html}"
        f"</body></html>"
    )
    return full_html


def _safe_filename(s: str) -> str:
    """Lowercase, ASCII-only, dash-joined; for the output filename."""
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")[:80]


# ─────────────────────────────────────────────────────────────────────────────
# Preset pool resumes — resumes/<slug>/{resume,cover-letter}.md
#
# Unlike tailor/curate (which transform the master per posting via an LLM),
# preset mode attaches one of a handful of pre-built, pool-specific résumés
# (e.g. autonomy / graphics / applied-ai / fullstack). $0, no LLM, no
# master-trimming — the pool file is already polished. Stored as draft_mode
# "preset:<slug>" on the application.
# ─────────────────────────────────────────────────────────────────────────────

PRESET_MODE_PREFIX = "preset:"
DEFAULT_POOL_DIR = ROOT_DIR / "resumes"

# Strips the inline "*(Drafted from project summary … verify …)*" flags that
# mark not-yet-verified bullets in the source markdown.
_VERIFY_FLAG_RE = re.compile(r"\s*\*\(Drafted from project summary[^)]*\)\*")


def is_preset_mode(mode: str | None) -> bool:
    return bool(mode) and mode.startswith(PRESET_MODE_PREFIX)


def preset_slug(mode: str | None) -> str:
    """`'preset:graphics-3d'` → `'graphics-3d'`; non-preset → `''`."""
    return mode[len(PRESET_MODE_PREFIX):] if is_preset_mode(mode) else ""


def clean_resume_md(md: str) -> str:
    """Strip conversation-scaffolding from a pool résumé before rendering: the
    `> **Pool resume:` annotation blockquote, any leftover `> Naming note:`
    blockquote (removed from the sources June 2026), and the inline verify
    flags."""
    kept = [
        ln
        for ln in md.split("\n")
        if not ln.lstrip().startswith(("> **Pool resume:", "> Naming note:"))
    ]
    return _VERIFY_FLAG_RE.sub("", "\n".join(kept))


def clean_cover_letter_md(md: str) -> str:
    """Return only the letter body — everything after the first horizontal
    rule — which drops the `# Cover Letter …` title and the instruction block.
    The `[bracketed]` fill-in spots are intentionally kept."""
    parts = re.split(r"\n---\s*\n", md, maxsplit=1)
    return parts[1].strip() if len(parts) == 2 else md.strip()


def _wrap_html(body_html: str) -> str:
    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'/>"
        f"<style>{_PRINT_CSS}</style></head><body>{body_html}</body></html>"
    )


def render_markdown_to_pdf(md_text: str, out_path: Path) -> Path:
    """Render already-cleaned markdown to PDF using the shared print CSS."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    html = _wrap_html(_md_to_html(md_text))
    with open(out_path, "wb") as f:
        result = pisa.CreatePDF(html, dest=f, encoding="utf-8")
    if result.err:
        raise RuntimeError(f"xhtml2pdf failed rendering {out_path.name} ({result.err} errors)")
    return out_path


def preset_resume_md_path(slug: str, *, pool_dir: Path = DEFAULT_POOL_DIR) -> Path:
    return pool_dir / slug / "resume.md"


def preset_cover_letter_md_path(slug: str, *, pool_dir: Path = DEFAULT_POOL_DIR) -> Path:
    return pool_dir / slug / "cover-letter.md"


def read_preset_cover_letter_text(slug: str, *, pool_dir: Path = DEFAULT_POOL_DIR) -> str:
    """Cleaned cover-letter body for a pool, or '' if the file is missing."""
    p = preset_cover_letter_md_path(slug, pool_dir=pool_dir)
    if not p.exists():
        return ""
    return clean_cover_letter_md(p.read_text(encoding="utf-8"))


def render_preset_resume_pdf(
    slug: str, *, out_path: Path, pool_dir: Path = DEFAULT_POOL_DIR
) -> Path:
    p = preset_resume_md_path(slug, pool_dir=pool_dir)
    if not p.exists():
        raise FileNotFoundError(f"preset résumé not found for pool {slug!r}: {p}")
    pdf = render_markdown_to_pdf(clean_resume_md(p.read_text(encoding="utf-8")), out_path)
    log.info("resume.preset.pdf.written", slug=slug, path=str(pdf), size=pdf.stat().st_size)
    return pdf


def render_preset_cover_letter_pdf(
    slug: str, *, out_path: Path, pool_dir: Path = DEFAULT_POOL_DIR
) -> Path:
    p = preset_cover_letter_md_path(slug, pool_dir=pool_dir)
    if not p.exists():
        raise FileNotFoundError(f"preset cover letter not found for pool {slug!r}: {p}")
    return render_markdown_to_pdf(clean_cover_letter_md(p.read_text(encoding="utf-8")), out_path)


def render_master_pdf(
    *,
    out_path: Path | None = None,
    profile_dir: Path = DEFAULT_PROFILE_DIR,
) -> Path:
    """Render the master `profile/resume.md` as a PDF — no per-application
    transformations applied. Use this for a readable view of the master
    instead of scrolling the markdown.

    Output defaults to `artifacts/resumes/master.pdf`.
    """
    master_path = profile_dir / "resume.md"
    if not master_path.exists():
        raise FileNotFoundError(f"master resume not found at {master_path}")
    md = master_path.read_text(encoding="utf-8")
    body_html = _md_to_html(md)
    full_html = (
        f"<!DOCTYPE html><html><head>"
        f"<meta charset='utf-8'/>"
        f"<style>{_PRINT_CSS}</style>"
        f"</head><body>"
        f"{body_html}"
        f"</body></html>"
    )
    if out_path is None:
        DEFAULT_RESUMES_DIR.mkdir(parents=True, exist_ok=True)
        out_path = DEFAULT_RESUMES_DIR / "master.pdf"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "wb") as f:
        result = pisa.CreatePDF(full_html, dest=f, encoding="utf-8")
    if result.err:
        raise RuntimeError(f"xhtml2pdf failed rendering master ({result.err} errors)")
    log.info("resume.master.pdf.written", path=str(out_path), size=out_path.stat().st_size)
    return out_path


async def render_for_posting(
    posting_id: int,
    *,
    out_path: Path | None = None,
    profile_dir: Path = DEFAULT_PROFILE_DIR,
    show_banner: bool = False,
) -> Path:
    """Render the tailored résumé for one posting and write a PDF.

    Returns the path to the written PDF. Default output:
        artifacts/resumes/<company>-<title>-<posting_id>.pdf
    """
    inputs = await _fetch_inputs(posting_id)

    if out_path is None:
        DEFAULT_RESUMES_DIR.mkdir(parents=True, exist_ok=True)
        slug = _safe_filename(f"{inputs.company_name}-{inputs.posting_title}-{posting_id}")
        out_path = DEFAULT_RESUMES_DIR / f"{slug}.pdf"

    # Preset mode: attach the pre-built pool résumé verbatim — no master
    # transform, no LLM. draft_mode is "preset:<pool-slug>".
    if is_preset_mode(inputs.draft_mode):
        pool = preset_slug(inputs.draft_mode)
        pdf = render_preset_resume_pdf(pool, out_path=out_path)
        log.info("resume.pdf.written", posting_id=posting_id, path=str(pdf),
                 size=pdf.stat().st_size, mode=inputs.draft_mode)
        return pdf

    html = render_resume_html(inputs, profile_dir=profile_dir, show_banner=show_banner)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "wb") as f:
        result = pisa.CreatePDF(html, dest=f, encoding="utf-8")
    if result.err:
        raise RuntimeError(f"xhtml2pdf failed for posting {posting_id} ({result.err} errors)")

    log.info(
        "resume.pdf.written",
        posting_id=posting_id,
        path=str(out_path),
        size=out_path.stat().st_size,
        mode=inputs.draft_mode,
        dropped=len(inputs.dropped_slugs),
        bolded=len(inputs.emphasis_quotes),
    )
    return out_path


async def render_cover_letter_for_posting(
    posting_id: int, *, out_path: Path | None = None
) -> Path:
    """Render the cover-letter PDF for a preset-mode posting.

    Only meaningful for preset modes (the pool ships a cover-letter template);
    tailor/curate cover letters are LLM text shown inline, not a PDF. Raises
    ValueError for non-preset applications.
    """
    inputs = await _fetch_inputs(posting_id)
    if not is_preset_mode(inputs.draft_mode):
        raise ValueError("cover-letter PDF is only available for preset-mode applications")
    if out_path is None:
        DEFAULT_RESUMES_DIR.mkdir(parents=True, exist_ok=True)
        slug = _safe_filename(f"{inputs.company_name}-{inputs.posting_title}-{posting_id}-cover")
        out_path = DEFAULT_RESUMES_DIR / f"{slug}.pdf"
    return render_preset_cover_letter_pdf(preset_slug(inputs.draft_mode), out_path=out_path)
