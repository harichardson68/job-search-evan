"""
update_scoring_evan.py — Evan Richardson Job Search
=====================================================
Runs at 12:30 AM via Windows Task Scheduler.

Sequence:
  1. git pull              — sync latest code + data from GitHub
  2. Read Google Sheet     — get today's form submissions
  3. Parse decisions       — map sheet rows to evan_job_decisions.json
  4. Apply auto-fixes      — update evan_job_search.py + evan_scoring_weights.json
  5. Write summary         — evan_overnight_summary.json (shown in tomorrow's email)
  6. git commit + push     — send everything back to GitHub
"""

import os
import json
import re
import subprocess
import shutil
from datetime import datetime, date
from dotenv import load_dotenv
from googleapiclient.discovery import build
from google.oauth2 import service_account

# ─── SETUP ───────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(SCRIPT_DIR, ".env"))

SHEET_ID         = "16NA3xPpvdV3nh1-FdWsfjGxCZ0OnvvmBAg6P2PQaaJs"
SHEET_RANGE      = "Form Responses 1!A:D"
CREDENTIALS_FILE = os.path.join(SCRIPT_DIR, "google_credentials.json")

DECISIONS_FILE  = os.path.join(SCRIPT_DIR, "evan_job_decisions.json")
TODAY_JOBS_FILE = os.path.join(SCRIPT_DIR, "evan_today_jobs.json")
WEIGHTS_FILE    = os.path.join(SCRIPT_DIR, "evan_scoring_weights.json")
JOB_SEARCH_FILE = os.path.join(SCRIPT_DIR, "evan_job_search.py")
SUMMARY_FILE    = os.path.join(SCRIPT_DIR, "evan_overnight_summary.json")
BACKUP_FILE     = os.path.join(SCRIPT_DIR, "evan_job_search.py.bak")

TODAY = date.today().isoformat()

DECISION_MAP = {
    "applied":                  "applied",
    "bad link":                 "bad_link",
    "onsite / not remote":      "onsite",
    "too senior":               "too_senior",
    "salary too low":           "salary_too_low",
    "not interested":           "not_interested",
    "already seen / duplicate": "already_seen",
    "already seen":             "already_seen",
    "search page listing":      "search_page",
    "search page":              "search_page",
    "not in united states":     "not_in_us",
    "other":                    "other",
}

print(f"\n{'='*55}")
print(f"  Evan Update Scoring — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(f"{'='*55}\n")

def git_pull():
    print("[GIT] Pulling latest from GitHub...")
    try:
        result = subprocess.run(["git", "pull"], cwd=SCRIPT_DIR, capture_output=True, text=True)
        print(f"   {result.stdout.strip() or 'Already up to date.'}")
    except Exception as e:
        print(f"   [WARN] git pull failed: {e}")

def load_today_jobs():
    try:
        if os.path.exists(TODAY_JOBS_FILE):
            with open(TODAY_JOBS_FILE, "r") as f:
                data = json.load(f)
            if data.get("date") == TODAY:
                return {j["number"]: j for j in data.get("jobs", [])}
            else:
                print(f"   [WARN] evan_today_jobs.json is from {data.get('date')} not today")
    except Exception as e:
        print(f"   [WARN] Could not load evan_today_jobs.json: {e}")
    return {}

def read_google_sheet():
    decisions = {}
    try:
        creds = service_account.Credentials.from_service_account_file(
            CREDENTIALS_FILE,
            scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
        )
        service = build("sheets", "v4", credentials=creds)
        result  = service.spreadsheets().values().get(
            spreadsheetId=SHEET_ID, range=SHEET_RANGE
        ).execute()
        rows = result.get("values", [])

        if not rows or len(rows) < 2:
            print("   [INFO] No form submissions found in sheet")
            return decisions

        print(f"   Found {len(rows)-1} total submission(s) in sheet")
        # Handle M/D/YYYY format that Google Sheets uses
        today_fmt = f"{datetime.now().month}/{datetime.now().day}/{datetime.now().year}"

        for row in rows[1:]:
            if len(row) < 3:
                continue
            timestamp  = row[0] if len(row) > 0 else ""
            job_number = row[1] if len(row) > 1 else ""
            decision   = row[2] if len(row) > 2 else ""
            reason     = row[3] if len(row) > 3 else ""

            if TODAY not in timestamp and today_fmt not in timestamp:
                continue

            try:
                job_num = int(str(job_number).strip())
            except ValueError:
                continue

            decision_key = DECISION_MAP.get(decision.lower().strip(), "other")
            decisions[job_num] = {
                "decision": decision_key,
                "reason":   reason.strip() if reason else None,
                "raw":      decision,
            }
            print(f"   Job {job_num}: {decision_key}" + (f" — {reason}" if reason else ""))

    except Exception as e:
        print(f"   [ERROR] Google Sheets read failed: {e}")
    return decisions

def save_decisions(today_jobs, decisions):
    try:
        all_decisions = {}
        if os.path.exists(DECISIONS_FILE):
            with open(DECISIONS_FILE, "r") as f:
                all_decisions = json.load(f)

        today_entries = []
        for job_num, job in today_jobs.items():
            dec = decisions.get(job_num, {})
            today_entries.append({
                "job_id":           job.get("job_id", ""),
                "number":           job_num,
                "title":            job.get("title", ""),
                "company":          job.get("company", ""),
                "track":            job.get("track", ""),
                "score":            job.get("score", 0),
                "url":              job.get("url", ""),
                "matched_keywords": job.get("matched_keywords", []),
                "source":           job.get("source", ""),
                "decision":         dec.get("decision", "no_response"),
                "reason":           dec.get("reason", None),
                "raw_decision":     dec.get("raw", ""),
                "timestamp":        datetime.now().strftime("%Y-%m-%d %H:%M"),
            })

        all_decisions[TODAY] = today_entries
        with open(DECISIONS_FILE, "w") as f:
            json.dump(all_decisions, f, indent=2)
        print(f"[OK] Saved {len(today_entries)} decisions to evan_job_decisions.json")
        return today_entries
    except Exception as e:
        print(f"[ERROR] Could not save decisions: {e}")
        return []

def load_weights():
    defaults = {
        "soc_analyst_score":        35,
        "cyber_analyst_score":      35,
        "mdr_analyst_score":        35,
        "vuln_mgmt_score":          30,
        "incident_response_score":  30,
        "pen_test_score":           25,
        "boosted_keywords":         [],
        "downweighted_keywords":    [],
        "auto_blocked_sites":       [],
        "auto_blocked_companies":   [],
        "auto_blocked_locations":   [],
        "applied_tracks":           {},
        "skipped_tracks":           {},
        "total_applied":             0,
        "total_skipped":             0,
        "last_updated":             "",
    }
    try:
        if os.path.exists(WEIGHTS_FILE):
            with open(WEIGHTS_FILE, "r") as f:
                saved = json.load(f)
            defaults.update(saved)
    except Exception:
        pass
    return defaults

def save_weights(weights):
    weights["last_updated"] = datetime.now().isoformat()
    with open(WEIGHTS_FILE, "w") as f:
        json.dump(weights, f, indent=2)
    print(f"[OK] Updated evan_scoring_weights.json")

def apply_feedback(entries, weights):
    auto_handled = []
    needs_review = []

    for entry in entries:
        decision = entry.get("decision", "no_response")
        reason   = entry.get("reason", "") or ""
        keywords = entry.get("matched_keywords", [])
        track    = entry.get("track", "")
        url      = entry.get("url", "").lower().strip()

        if decision == "applied":
            weights["total_applied"] += 1
            weights["applied_tracks"][track] = weights["applied_tracks"].get(track, 0) + 1
            for kw in keywords:
                kw_lower = kw.lower()
                if kw_lower not in weights["boosted_keywords"]:
                    weights["boosted_keywords"].append(kw_lower)
                    auto_handled.append(f"Boosted keyword: '{kw_lower}'")

        elif decision in ("not_interested", "too_senior", "salary_too_low", "already_seen", "search_page"):
            weights["total_skipped"] += 1
            weights["skipped_tracks"][track] = weights["skipped_tracks"].get(track, 0) + 1

        elif decision == "bad_link":
            weights["total_skipped"] += 1
            domain_match = re.search(r"https?://([^/]+)", url)
            if domain_match:
                domain = domain_match.group(1)
                if domain not in weights["auto_blocked_sites"]:
                    weights["auto_blocked_sites"].append(domain)
                    auto_handled.append(f"Auto-blocked site: '{domain}'")

        elif decision == "not_in_us":
            weights["total_skipped"] += 1
            if reason:
                loc = reason.lower().strip().rstrip(".")
                if loc and loc not in weights["auto_blocked_locations"]:
                    weights["auto_blocked_locations"].append(loc)
                    auto_handled.append(f"Auto-blocked location: '{loc}'")

        elif decision == "onsite":
            weights["total_skipped"] += 1
            if reason:
                city = reason.lower().strip().rstrip(".")
                if city and city not in weights.get("onsite_cities_seen", []):
                    if "onsite_cities_seen" not in weights:
                        weights["onsite_cities_seen"] = []
                    weights["onsite_cities_seen"].append(city)
                    auto_handled.append(f"Noted onsite city: '{city}'")

        elif decision == "other" and reason:
            reason_lower = reason.lower()
            loc_match = re.search(r"(?:bad location|overseas|wrong location|location)[:\s\-]+(.+)", reason_lower)
            co_match  = re.search(r"(?:bad company|sketchy|scam|body shop)[:\s\-]+(.+)", reason_lower)
            if loc_match:
                loc = loc_match.group(1).strip().rstrip(".")
                if loc and loc not in weights["auto_blocked_locations"]:
                    weights["auto_blocked_locations"].append(loc)
                    auto_handled.append(f"Auto-blocked location: '{loc}'")
            elif co_match:
                co = co_match.group(1).strip()
                if co not in weights["auto_blocked_companies"]:
                    weights["auto_blocked_companies"].append(co)
                    auto_handled.append(f"Auto-blocked company: '{co}'")
            else:
                needs_review.append(f"Job '{entry.get('title','?')}': {reason}")

    return auto_handled, needs_review

def patch_job_search(weights):
    if not os.path.exists(JOB_SEARCH_FILE):
        print(f"   [WARN] {JOB_SEARCH_FILE} not found — skipping patch")
        return False

    shutil.copy2(JOB_SEARCH_FILE, BACKUP_FILE)

    with open(JOB_SEARCH_FILE, "r", encoding="utf-8") as f:
        content = f.read()

    changed = False

    for loc in weights.get("auto_blocked_locations", []):
        if f'"{loc}"' not in content and f"'{loc}'" not in content:
            pattern = r'(NON_US_LOCATIONS\s*=\s*\[)(.*?)(]\s*\n)'
            def add_loc(m, loc=loc):
                return m.group(1) + m.group(2) + f'    "{loc}",\n' + m.group(3)
            new = re.sub(pattern, add_loc, content, flags=re.DOTALL)
            if new != content:
                content = new
                changed = True
                print(f"   [PATCH] Added '{loc}' to NON_US_LOCATIONS")

    for site in weights.get("auto_blocked_sites", []):
        if f'"{site}"' not in content:
            pattern = r'(BLOCKED_JOB_SITES\s*=\s*\[)(.*?)(]\s*\n)'
            def add_site(m, site=site):
                return m.group(1) + m.group(2) + f'    "{site}",\n' + m.group(3)
            new = re.sub(pattern, add_site, content, flags=re.DOTALL)
            if new != content:
                content = new
                changed = True
                print(f"   [PATCH] Added '{site}' to BLOCKED_JOB_SITES")

    for co in weights.get("auto_blocked_companies", []):
        if f'"{co}"' not in content:
            pattern = r'(BLOCKED_COMPANIES\s*=\s*\[)(.*?)(]\s*\n)'
            def add_co(m, co=co):
                return m.group(1) + m.group(2) + f'    "{co}",\n' + m.group(3)
            new = re.sub(pattern, add_co, content, flags=re.DOTALL)
            if new != content:
                content = new
                changed = True
                print(f"   [PATCH] Added '{co}' to BLOCKED_COMPANIES")

    if changed:
        with open(JOB_SEARCH_FILE, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"[OK] evan_job_search.py patched successfully")
    else:
        print(f"[OK] No patches needed for evan_job_search.py")
    return changed

def write_summary(entries, auto_handled, needs_review, git_committed):
    decisions_received = sum(1 for e in entries if e.get("decision") != "no_response")
    no_response        = sum(1 for e in entries if e.get("decision") == "no_response")
    summary = {
        "date":               TODAY,
        "jobs_sent":          len(entries),
        "decisions_received": decisions_received,
        "no_response":        no_response,
        "auto_handled":       auto_handled,
        "needs_review":       needs_review,
        "git_committed":      "Yes" if git_committed else "No",
        "generated_at":       datetime.now().isoformat(),
    }
    with open(SUMMARY_FILE, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"[OK] Evan overnight summary written")

def git_commit_push(auto_handled, needs_review):
    print("[GIT] Committing and pushing updates...")
    try:
        subprocess.run(["git", "add", "."], cwd=SCRIPT_DIR, check=True)
        changes = f"{len(auto_handled)} auto-fixes" if auto_handled else "decisions recorded"
        commit_msg = f"Evan auto-update {TODAY}: {changes}"
        result = subprocess.run(
            ["git", "commit", "-m", commit_msg],
            cwd=SCRIPT_DIR, capture_output=True, text=True
        )
        if "nothing to commit" in result.stdout:
            print("   [INFO] Nothing to commit")
            return False
        subprocess.run(["git", "push"], cwd=SCRIPT_DIR, check=True)
        print(f"   [OK] Pushed: '{commit_msg}'")
        return True
    except subprocess.CalledProcessError as e:
        print(f"   [ERROR] Git failed: {e}")
        return False

def main():
    git_pull()

    today_jobs = load_today_jobs()
    if not today_jobs:
        print("[INFO] No jobs for today — nothing to process")
        write_summary([], [], [], False)
        return
    print(f"[OK] Loaded {len(today_jobs)} jobs from evan_today_jobs.json")

    print("[SHEETS] Reading Evan's Google Sheet...")
    decisions = read_google_sheet()
    print(f"[OK] {len(decisions)} decision(s) from Google Sheet")

    entries = save_decisions(today_jobs, decisions)
    weights = load_weights()

    auto_handled, needs_review = apply_feedback(entries, weights)
    print(f"[OK] Auto-handled: {len(auto_handled)} | Needs review: {len(needs_review)}")
    for item in auto_handled:
        print(f"   + {item}")
    for item in needs_review:
        print(f"   ! {item}")

    save_weights(weights)
    patch_job_search(weights)
    git_committed = git_commit_push(auto_handled, needs_review)
    write_summary(entries, auto_handled, needs_review, git_committed)

    print(f"\n[DONE] Evan update completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        print(f"\n[FATAL] {traceback.format_exc()}")
