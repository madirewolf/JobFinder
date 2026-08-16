"""Re-render (only) the 4 sample postings to v7 PDFs using stored curate drafts.
No LLM calls — $0. Run after a renderer change to refresh v7 without re-drafting.
"""
from __future__ import annotations

import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from job_finder.config import ROOT_DIR  # noqa: E402
from job_finder.db import close_pools  # noqa: E402
from job_finder.resume.render import render_for_posting  # noqa: E402

OUT = ROOT_DIR / "artifacts" / "resumes" / "v7"


async def main() -> None:
    try:
        for pid in [382, 369, 454, 533]:
            p = await render_for_posting(pid, out_path=OUT / f"{pid}.pdf")
            print(f"{pid}: {p.stat().st_size:,} B")
    finally:
        await close_pools()


if __name__ == "__main__":
    asyncio.run(main())
