"""Re-draft + re-render the 4 sample postings (382/369/454/533) through the
updated curate prompt + renderer, writing v7 PDFs to artifacts/resumes/v7/.

Force-drafts past the fit-gate (these samples are skipped_low_fit) so we get
curated output to compare against v6. Curate mode → Sonnet (~$0.04 each).

Run: uv run python scripts/regen_v7_samples.py
"""

from __future__ import annotations

import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from job_finder.config import ROOT_DIR  # noqa: E402
from job_finder.db import close_pools  # noqa: E402
from job_finder.drafter.draft import draft_for_posting  # noqa: E402
from job_finder.resume.render import render_for_posting  # noqa: E402

IDS = [382, 369, 454, 533]
OUT = ROOT_DIR / "artifacts" / "resumes" / "v7"


async def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    total = 0.0
    try:
        for pid in IDS:
            r = await draft_for_posting(pid, mode="curate", skip_fit_gate=True)
            total += r.usd_cost
            pdf = await render_for_posting(pid, out_path=OUT / f"{pid}.pdf")
            print(f"{pid}: draft usd={r.usd_cost:.4f} -> {pdf.name} ({pdf.stat().st_size:,} B)")
    finally:
        await close_pools()
    print(f"TOTAL usd={total:.4f}")


if __name__ == "__main__":
    asyncio.run(main())
