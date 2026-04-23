# Automated Cybersecurity Job Search System

A Python-based automated job search pipeline targeting **SOC Analyst**, **Cybersecurity Analyst**, **MDR Analyst**, **Vulnerability Management**, **Incident Response**, and **Junior Penetration Tester** roles in the **Remote US** and **Kansas City Metro** markets. Runs daily and delivers a scored, filtered, deduplicated HTML email digest with AI-generated cover letters.

---

## What It Does

- **Multi-source job aggregation** — pulls from RemoteOK, Serper (Google Jobs), USAJobs, Greenhouse, Lever, Google Custom Search, Dice, and Wellfound
- **Dual-market targeting** — Remote US jobs AND KC Metro hybrid/onsite roles are both collected and scored
- **Cybersecurity track scoring** — independently scores jobs against SOC, MDR, Vulnerability Management, Incident Response, and Pen Test keyword sets
- **Strict relevance filtering** — non-US locations, blocked aggregator sites, blocked companies (staffing body shops, resume harvesters), and sketchy job patterns all filtered out
- **Deduplication** — cross-source dedup by title+URL within each run, plus persistent `evan_seen_jobs.json` to prevent repeat sends across days
- **AI cover letter generation** — uses Claude (Anthropic) to write a tailored cover letter per job
- **HTML email digest** — sends a formatted daily digest with color-coded job tracks, Workday link warnings, score, matched keywords, source, and cover letter

---

## Architecture

```
Sources (8)                  Filtering Pipeline              Output
──────────                   ──────────────────              ──────
RemoteOK        ──┐          is_us_remote()       ─┐
Serper          ──┤          is_relevant_title()   ─┤         evan_seen_jobs.json
USAJobs         ──┼──► raw ──is_blocked_site()     ─┼──► scored ──► top 10 ──► Gmail HTML digest
Greenhouse      ──┤   jobs   is_blocked_company()  ─┤   jobs          │
Lever           ──┤          is_sketchy_job()       ─┤                 └──► cover letters (Claude)
Google Jobs     ──┤          score_job()            ─┘
Dice            ──┤          deduplication
Wellfound       ──┘
```

---

## Cybersecurity Job Tracks

| Track | Color | Example Roles |
|---|---|---|
| SOC Analyst | Navy | SOC Analyst I, Security Operations Analyst |
| Cybersecurity Analyst | Green | Information Security Analyst, Cyber Analyst |
| MDR Analyst | Purple | MDR Analyst, Managed Detection Analyst |
| Vulnerability Management | Amber | Vuln Management Analyst, Patch Management |
| Incident Response | Red | DFIR Analyst, Incident Response Analyst |
| Junior Pen Tester | Teal | Junior Penetration Tester, AppSec Analyst |

---

## Location Strategy

The system targets two distinct markets simultaneously:

- **Remote US** — nationwide remote roles, filtered to exclude non-US postings (India, Canada, UK, Europe, etc.)
- **KC Metro** — hybrid/onsite roles within commuting distance: Kansas City MO/KS, Lee's Summit, Overland Park, Olathe, Shawnee, Lenexa, Leawood, and surrounding suburbs

---

## Setup

### 1. Install dependencies
```bash
pip install requests feedparser python-dateutil anthropic
```

### 2. Configure environment
```bash
cp .env.example .env
# Edit .env and fill in your API keys and Gmail credentials
```

Load the `.env` before running, or use `python-dotenv`.

### 3. Run manually
```bash
python evan_job_search.py
```

### 4. Schedule daily (Windows Task Scheduler)
- Action: `python C:\path\to\evan_job_search.py`
- Trigger: Daily at your preferred time
- Log output goes to `evan_job_search.log` automatically

---

## API Keys Required

| Service | Purpose | Cost |
|---|---|---|
| [Anthropic](https://console.anthropic.com) | Cover letter generation | Pay per use |
| [Serper](https://serper.dev) | Google Jobs search | Free tier (2,500/mo) |
| [USAJobs](https://developer.usajobs.gov) | Federal cybersecurity jobs | Free (registration required) |
| [Google Custom Search](https://developers.google.com/custom-search) | Backup search | Free tier (100/day) |
| Gmail App Password | Email delivery | Free |

---

## Key Design Decisions

**Why both remote and KC Metro?** A recent Cybersecurity graduate benefits from both channels — remote roles maximize nationwide reach while KC Metro onsite/hybrid roles at local employers (Garmin, Cerner/Oracle Health, H&R Block, Evergy, Lockton) may be more accessible for entry-level candidates.

**Why track-based scoring instead of a single score?** Different cybersecurity roles require different keywords. A SOC Analyst role and a Pen Test role don't share vocabulary, so each track scores independently and the job is assigned to its best-matching track.

**Why blocked companies list?** Entry-level cybersecurity postings attract a high density of staffing body shops and resume harvesters. The blocked company list filters these before they reach the candidate.

---

## Output Files

| File | Purpose |
|---|---|
| `evan_job_search.log` | Full run log with debug output |
| `evan_seen_jobs.json` | Persistent store of already-sent job URLs |

---

## About

Built by **Hans Richardson** for his son **Evan Richardson**, a recent Cybersecurity graduate entering the job market. This project demonstrates automated multi-source data aggregation, LLM integration, and practical Python tooling applied to a real-world problem.
