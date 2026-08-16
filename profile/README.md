# profile/

Everything the bot uses to represent *you*.

On `jfb profile ingest`, every `*.md` under this directory is recursively
chunked (≈512 tokens, 50 overlap), embedded via Ollama, and written to
`portfolio_chunks`. A centroid of those embeddings is saved to
`profile_vectors` under the label `primary`, and it's what the Stage-3
cosine gate uses before spending Haiku tokens.

## Layout

```
profile/
├─ resume.md              # 1-page master resume (required)
├─ prefs.md               # what you want / don't want (target roles, pay, geo)
├─ portfolio/             # long-form site copy (limiliminal, 5gcx, vimy, …)
│   └─ *.md
└─ projects/              # one file per project, stem = slug
    └─ <slug>.md
```

File naming rules (see `src/job_finder/classify/profile.py:_classify_source`):

| Path                                    | `portfolio_chunks.source` | `.project` |
|-----------------------------------------|---------------------------|------------|
| `profile/resume.md`                     | `resume`                  | `NULL`     |
| `profile/prefs.md` (or `preferences.md`)| `prefs`                   | `NULL`     |
| `profile/projects/<slug>.md`            | `project:<slug>`          | `<slug>`   |
| anything else                           | `portfolio`               | `NULL`     |

## Contents (you fill in)

- **resume.md** — plain markdown, one page. Use the same wording you'd want
  the bot to match against job descriptions. Sections: header, skills,
  experience, projects, education.
- **prefs.md** — bullet list. Target roles, target compensation, geography
  (Toronto / Montreal / remote-Canada), constraints. This goes into the
  cached Haiku system prefix, so keep it tight (≤ 8k chars combined with
  resume).
- **portfolio/*.md** — dump of your site copy. The more specific and
  quantified, the better the retrieval for per-application drafting.
- **projects/*.md** — one file per project. Each should answer: *what did
  I build, what stack, what was the outcome, what's the link.*

## Re-running

Ingest is idempotent with `--replace` (the default): it truncates
`portfolio_chunks` before inserting. Safe to re-run whenever you edit
files. The aggregate vector under `profile_vectors.label='primary'` is
upserted — any references downstream keep working.

## Gitignore

`profile/` itself is tracked (so this README and the examples below live
with the repo), but if you store a real resume with private contact info,
add `profile/resume.md` and `profile/prefs.md` to `.gitignore` locally.
