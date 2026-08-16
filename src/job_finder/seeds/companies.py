"""Seed data — target companies for Toronto/Montreal tech search.

Ranked by (role_fit × check_leniency × hiring_velocity) per SPEC §10.1.
Tier 1 = apply immediately, Tier 4 = high-stringency, decide individually.

Fields: (name, domain, ats_platform, ats_token, bg_check_stringency, tier,
         hq_city, hq_province, notes)

`ats_token` is what the ATS client's fetch() needs as input:
  - greenhouse: board slug (https://boards.greenhouse.io/<slug>)
  - lever:      company slug (https://jobs.lever.co/<slug>)
  - ashby:      company slug (https://jobs.ashbyhq.com/<slug>)
  - smartrecruiters: company id (https://jobs.smartrecruiters.com/<id>)
  - workable:   company slug (https://apply.workable.com/<slug>)
  - workday:    "tenant:wd_server:site_path" (see workday.py docstring)
  - custom:     None (manual discovery needed)

VERIFY TOKENS before first ingestion — some are inferred and may need adjustment
once you hit the actual careers page. Wrong tokens will show up as 404s in
the ingester logs and tell you what to fix.
"""

from __future__ import annotations

SeedTuple = tuple[str, str | None, str, str | None, str, int, str, str, str | None]

SEED_COMPANIES: list[SeedTuple] = [
    # ═══════════════════════════════════════════════════════════════════════════
    # TIER 1 — bullseye for the operator's ICP (applied-AI / autonomy /
    # robotics / defence-tech / AI-tooling at Series A-B with a real engineering
    # bar). Apply early.
    # ═══════════════════════════════════════════════════════════════════════════

    # ─── Autonomy / robotics ──────────────────────────────────────────────────
    ("Waabi", "waabi.ai", "lever", "waabi", "moderate", 1, "Toronto", "ON",
     "Self-driving truck autonomy; Raquel Urtasun; $750M Series C; ROS/SLAM/MPC stack"),
    ("Sanctuary AI", "sanctuary.ai", "lever", "sanctuaryai", "moderate", 1, "Vancouver", "BC",
     "General-purpose humanoid robotics; manipulation + perception; verify ATS slug"),
    ("Aurora Innovation", "aurora.tech", "greenhouse", "aurora", "moderate", 1, "Remote", None,
     "AV trucking; remote-friendly; AV stack overlaps capstone work"),
    ("Wayve", "wayve.ai", "greenhouse", "wayve", "moderate", 1, "London", "UK",
     "End-to-end AV ML; UK-based but expanding; remote-friendly for senior roles"),
    ("Skydio", "skydio.com", "greenhouse", "skydio", "moderate", 1, "Remote", None,
     "Autonomous drones; perception + planning; less clearance gating than defence peers"),
    ("Anduril", "anduril.com", "lever", "anduril", "strict", 1, "Remote", None,
     "Defence-tech; Lattice + autonomy; US clearance preferred but not always required"),
    ("Shield AI", "shield.ai", "greenhouse", "shieldai", "strict", 1, "Remote", None,
     "Defence-tech AI pilot for UAS; clearance often required — read JD"),
    ("Saronic", "saronic.com", "ashby", "saronic", "strict", 1, "Austin", "TX",
     "Naval autonomous surface vessels; defence-tech; verify ATS slug"),
    ("Helsing", "helsing.ai", "greenhouse", "helsing", "strict", 1, "Berlin", "DE",
     "European defence-AI; less clearance gated than US peers; remote-EU friendly"),
    ("Applied Intuition", "appliedintuition.com", "greenhouse", "appliedintuition", "moderate", 1, "Mountain View", "CA",
     "AV simulation + autonomy software; remote-CA sometimes"),

    # ─── AI-tooling / agentic platforms ──────────────────────────────────────
    ("Anthropic", "anthropic.com", "greenhouse", "anthropic", "moderate", 1, "Remote", None,
     "Bullseye for AI-coding lover; Claude maker; Toronto presence + remote roles"),
    ("Cohere", "cohere.com", "greenhouse", "cohere", "moderate", 1, "Toronto", "ON",
     "LLM systems/ML; Greenhouse-only; HQ Toronto"),
    ("Cursor (Anysphere)", "cursor.com", "ashby", "anysphere", "lenient", 1, "Remote", None,
     "AI-native code editor; agentic coding; verify ATS slug"),
    ("Codeium / Windsurf", "codeium.com", "ashby", "codeium", "lenient", 1, "Remote", None,
     "AI dev tools / Windsurf IDE; remote-friendly"),
    ("Continue.dev", "continue.dev", "ashby", "continue", "lenient", 1, "Remote", None,
     "Open-source AI dev assistant; smaller team, founding-engineer adjacent"),
    ("LangChain", "langchain.com", "greenhouse", "langchain", "lenient", 1, "Remote", None,
     "Agent infra; remote-friendly; well known"),
    ("LlamaIndex", "llamaindex.ai", "ashby", "llamaindex", "lenient", 1, "Remote", None,
     "RAG + agent framework; remote-friendly"),
    ("Browserbase", "browserbase.com", "ashby", "browserbase", "lenient", 1, "Remote", None,
     "Headless browser for agents; YC-adjacent; verify ATS slug"),
    ("CrewAI", "crewai.com", "ashby", "crewai", "lenient", 1, "Remote", None,
     "Multi-agent orchestration; YC; verify ATS slug"),
    ("Glean", "glean.com", "greenhouse", "glean", "moderate", 1, "Remote", None,
     "Enterprise AI search; well-funded; engineering-heavy"),
    ("Vercel", "vercel.com", "greenhouse", "vercel", "lenient", 1, "Remote", None,
     "Next.js + AI SDK; remote-CA; not pure AI but AI-adjacent stack"),

    # ─── ML systems / AI accelerator silicon ─────────────────────────────────
    ("Tenstorrent", "tenstorrent.com", "greenhouse", "tenstorrent", "strict", 1, "Toronto", "ON",
     "Returning-engineer territory; AI accelerator silicon; US export control — verify per JD"),
    ("NVIDIA", "nvidia.com", "workday", "nvidia:5:nvidiaexternalcareersite", "moderate", 1, "Toronto", "ON",
     "Expanding Toronto; CUDA / inference / robotics teams"),
    ("AMD", "amd.com", "custom", None, "moderate", 1, "Markham", "ON",
     "GPU drivers; ROCm; US export control gates; custom portal"),
    ("Groq", "groq.com", "greenhouse", "groqcareers", "moderate", 1, "Remote", None,
     "Inference accelerator; LPU; remote-friendly"),
    ("Cerebras", "cerebras.net", "greenhouse", "cerebras", "moderate", 1, "Remote", None,
     "Wafer-scale AI accelerator; ML-systems heavy"),

    # ═══════════════════════════════════════════════════════════════════════════
    # TIER 2 — strong overlap on at least one axis; apply Week 2-3
    # ═══════════════════════════════════════════════════════════════════════════
    ("Ericsson Canada", "ericsson.com", "eightfold", "ericsson", "moderate", 2, "Montreal", "QC",
     "5G + autonomy in vehicle networks; eightfold stub — implement before relying"),
    ("Ciena", "ciena.com", "workday", "ciena:5:CienaCareers", "moderate", 2, "Ottawa", "ON",
     "Optical / 5G systems; less ICP-aligned than T1 but solid systems work"),
    ("ServiceNow", "servicenow.com", "workday", "servicenow:5:ServiceNowCareers", "moderate", 2, "Montreal", "QC",
     "ex-Element AI; AI agents in enterprise SaaS; verify Workday triple"),
    ("Coveo", "coveo.com", "greenhouse", "coveo", "moderate", 2, "Quebec City", "QC",
     "AI search; strong s.18.2"),
    ("Shopify", "shopify.com", "ashby", "shopify", "moderate", 2, "Toronto", "ON",
     "Ruby/Rails at scale; AI features growing; remote-first"),
    ("Autodesk", "autodesk.com", "workday", "autodesk:5:Autodesk", "moderate", 2, "Toronto", "ON",
     "Maya/Fusion + AI Research; geometry-aware ML; verify Workday triple"),
    ("Ada Support", "ada.cx", "greenhouse", "ada", "lenient", 2, "Toronto", "ON",
     "AI customer-service agents; agentic adjacent"),
    ("Faire", "faire.com", "greenhouse", "faire", "moderate", 2, "Toronto", "ON",
     "Marketplace backend + ML"),
    ("Geotab", "geotab.com", "smartrecruiters", "Geotab", "moderate", 2, "Oakville", "ON",
     "Telematics / IoT; sensor data + ML; new Toronto office"),
    ("Mila", "mila.quebec", "workable", "mila", "lenient", 2, "Montreal", "QC",
     "Academic ML research; Bengio orbit"),
    ("Vector Institute", "vectorinstitute.ai", "custom", None, "lenient", 2, "Toronto", "ON",
     "Toronto AI research org; verify ATS"),
    ("Matrox", "matrox.com", "custom", None, "lenient", 2, "Dorval", "QC",
     "Graphics + vision hardware; Quebec-owned; careers page scrape needed"),
    ("1Password", "1password.com", "ashby", "1password", "strict", 2, "Toronto", "ON",
     "SOC2-heavy; less ICP-aligned"),

    # ═══════════════════════════════════════════════════════════════════════════
    # TIER 3 — good fit but narrower hiring or off-center on the ICP axis
    # ═══════════════════════════════════════════════════════════════════════════
    ("Behaviour Interactive", "bhvr.com", "lever", "behaviour", "lenient", 3, "Montreal", "QC",
     "Demoted from T1: F2P games not on ICP; keep for fallback"),
    ("Electronic Arts", "ea.com", "workday", "ea:1:ea", "moderate", 3, "Montreal", "QC",
     "Demoted: SEED has Gen-AI research but games trajectory mismatch"),
    ("Ubisoft", "ubisoft.com", "smartrecruiters", "Ubisoft", "moderate", 3, "Montreal", "QC",
     "Demoted: AAA games, off-ICP"),
    ("Moment Factory", "momentfactory.com", "lever", "momentfactory", "lenient", 3, "Montreal", "QC",
     "Demoted: creative tech, off-ICP"),
    ("SideFX", "sidefx.com", "custom", None, "lenient", 3, "Toronto", "ON",
     "Demoted: Houdini/graphics, off-ICP"),
    ("Uken Games", "uken.com", "custom", None, "moderate", 3, "Toronto", "ON",
     "F2P mobile + backend; custom ATS"),
    ("Rodeo FX", "rodeofx.com", "smartrecruiters", "RodeoFX", "moderate", 3, "Montreal", "QC",
     "Graphics pipeline; off-ICP"),
    ("Snowed In Studios", "snowedinstudios.com", "workable", "snowedinstudios", "lenient", 3, "Ottawa", "ON",
     "AAA co-dev; off-ICP"),
    ("Haven Studios", "havenstudios.com", "greenhouse", "havenstudios", "strict", 3, "Montreal", "QC",
     "Sony; offer-stage criminal checks"),
    ("Compulsion Games", "compulsiongames.com", "smartrecruiters", "CompulsionGames", "moderate", 3, "Montreal", "QC",
     "Unreal; Microsoft parent"),
    ("Gameloft", "gameloft.com", "smartrecruiters", "Gameloft", "lenient", 3, "Montreal", "QC",
     "Cross-platform gameplay + data science"),
    ("Lightspeed", "lightspeedhq.com", "greenhouse", "lightspeed", "strict", 3, "Montreal", "QC",
     "POS + payments (PCI-DSS on payments roles)"),
    ("Framestore", "framestore.com", "greenhouse", "framestore", "moderate", 3, "Montreal", "QC",
     "VFX pipeline; TPN medium-high"),
    ("BenchSci", "benchsci.com", "lever", "benchsci", "strict", 3, "Toronto", "ON",
     "Pharma ML"),
    ("Jane Software", "jane.app", "lever", "jane", "strict", 3, "Remote", "BC",
     "Rails healthcare; PHIPA/HIPAA"),
    ("League", "league.com", "greenhouse", "league", "strict", 3, "Toronto", "ON",
     "Healthcare platform + AI agents"),
    ("Klick Health", "klick.com", "smartrecruiters", "KlickHealth", "strict", 3, "Toronto", "ON",
     "Applied Sciences + tech"),
    ("AlayaCare", "alayacare.com", "greenhouse", "alayacare", "very_strict", 3, "Montreal", "QC",
     "Home healthcare SaaS; HIPAA + Law 25"),
    ("Hopper", "hopper.com", "ashby", "hopper", "strict", 3, "Montreal", "QC",
     "Travel + payments; cautious hiring"),
    ("Workleap", "workleap.com", "greenhouse", "workleap", "lenient", 3, "Montreal", "QC",
     ".NET/React SaaS"),

    # ═══════════════════════════════════════════════════════════════════════════
    # TIER 4 — very strict BG checks; surface but rank-penalised
    # ═══════════════════════════════════════════════════════════════════════════
    ("Wealthsimple", "wealthsimple.com", "ashby", "wealthsimple", "very_strict", 4, "Toronto", "ON",
     "OSFI-regulated fintech; enhanced + credit"),
    ("TD Bank", "td.com", "workday", "td:3:TD_Prod_Careers", "very_strict", 4, "Toronto", "ON",
     "Layer 6 AI under TD; verify Workday triple"),
    ("Neo Financial", "neofinancial.com", "lever", "neofinancial", "very_strict", 4, "Toronto", "ON",
     "Publicly states screening required"),
    ("Nuvei", "nuvei.com", "workable", "nuvei", "very_strict", 4, "Montreal", "QC",
     "PCI-DSS payments"),
    ("TELUS", "telus.com", "workday", "telus:5:careers", "very_strict", 4, "Toronto", "ON",
     "Telecom; BackCheck (criminal + credit)"),
    ("CGI", "cgi.com", "custom", None, "very_strict", 4, "Montreal", "QC",
     "Gov contractor; Reliability/Secret often required; Njoyn ATS (custom)"),
]
