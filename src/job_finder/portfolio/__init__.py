"""Portfolio-site ingestion (spec §5.1).

Crawls the candidate's public sites (limiliminal.com, 5gcx.ai, vimy.ai) and
GitHub READMEs, extracts text, chunks, embeds, and inserts into
`portfolio_chunks` alongside the markdown-profile chunks.

Source-key convention (matches spec §4 schema comment):
    'limiliminal' | '5gcx' | 'vimy' | 'github:<owner>/<repo>'
"""
