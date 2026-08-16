"""Render the 4 pool resume + cover-letter markdown pairs to PDF.

Reuses the production toolchain (markdown-it-py → xhtml2pdf with the same
ATS-friendly print CSS as the per-posting renderer) so these match house style.

Conventions:
  - Resumes: rendered faithfully, but our conversation-scaffolding is stripped
    (the `> **Pool resume:` annotation blockquote, any leftover `> Naming
    note:` blockquote, and the `*(Drafted from project summary — verify…)*`
    flags).
  - Cover letters: only the content AFTER the first `---` separator is rendered,
    which drops the `# Cover Letter …` title and the `> **Preset template…`
    instruction block. The `[bracketed]` fill-in spots are intentionally kept.

Run:  uv run python scripts/render_pool_pdfs.py
Output: a .pdf next to each .md (same stem).
"""

from __future__ import annotations

from job_finder.config import ROOT_DIR
from job_finder.resume.render import (
    clean_cover_letter_md,
    clean_resume_md,
    render_markdown_to_pdf,
)

# graphics-3d and autonomy-robotics retired 2026-06-14 (moved to resumes/inactive/).
# Surviving send-out pools only.
POOLS = (
    "applied-ai-ml",
    "fullstack-product",
    "design-engineer",
)
RESUMES_DIR = ROOT_DIR / "resumes"


def main() -> None:
    for pool in POOLS:
        d = RESUMES_DIR / pool
        print(f"{pool}:")
        resume_md = clean_resume_md((d / "resume.md").read_text(encoding="utf-8"))
        p = render_markdown_to_pdf(resume_md, d / "resume.pdf")
        print(f"  wrote {p.relative_to(ROOT_DIR)}  ({p.stat().st_size:,} bytes)")
        cl_md = clean_cover_letter_md((d / "cover-letter.md").read_text(encoding="utf-8"))
        p = render_markdown_to_pdf(cl_md, d / "cover-letter.pdf")
        print(f"  wrote {p.relative_to(ROOT_DIR)}  ({p.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
