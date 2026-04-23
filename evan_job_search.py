#!/usr/bin/env python3
"""
============================================================
  Evan Richardson - Cybersecurity Job Search System
  Target: SOC Analyst, Cybersecurity Analyst, MDR Analyst,
          Security Operations, Vulnerability Management,
          Incident Response, Junior Penetration Tester
  Markets: Remote + KC Metro (Hybrid/Onsite)
  Built:   April 2026
============================================================
"""

import os
import sys
import json
import re
import time
import smtplib
import requests
import feedparser
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from dateutil import parser as dateparser
from dotenv import load_dotenv

# Load .env file from same directory as this script
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

# ─── LOGGING SETUP ───────────────────────────────────────────
import os as _os
LOG_FILE = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "evan_job_search.log")
if _os.path.exists(LOG_FILE):
    try:
        with open(LOG_FILE, "w") as _test:
            pass
    except PermissionError:
        LOG_FILE = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "evan_job_search_new.log")

class DualLogger:
    def __init__(self, log_path):
        self.console = sys.__stdout__
        try:
            self.logfile = open(log_path, "w", encoding="utf-8")
            self._has_log = True
        except PermissionError:
            self.logfile = None
            self._has_log = False
            self.console.write("[WARN] Could not open log file - running console only\n")
    def write(self, message):
        self.console.write(message)
        if self._has_log:
            self.logfile.write(message)
            self.logfile.flush()
    def flush(self):
        self.console.flush()
        if self._has_log and self.logfile:
            self.logfile.flush()

sys.stdout = DualLogger(LOG_FILE)

print(f"\n{'='*60}")
print(f"  Evan Richardson Job Search Run: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(f"{'='*60}")

# ─── CONFIGURATION ───────────────────────────────────────────
DEBUG_MODE       = True
MAX_AGE_HOURS    = 72    # 3 days
MAX_JOBS_EMAIL   = 10
SEEN_JOBS_FILE   = "evan_seen_jobs.json"
GENERATE_COVER_LETTERS = False  # Enabled

# Email config
SMTP_EMAIL    = os.environ.get("SMTP_EMAIL", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
TARGET_EMAIL  = os.environ.get("TARGET_EMAIL", "")  # Evan's email

# API Keys
SERPER_API_KEY    = os.environ.get("SERPER_API_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
GOOGLE_API_KEY    = os.environ.get("GOOGLE_API_KEY", "")
GOOGLE_CX         = os.environ.get("GOOGLE_CX", "")

# ─── BLOCKED SITES ───────────────────────────────────────────
BLOCKED_JOB_SITES = [
    "jobgether.com", "kuubik.com", "jobtogether.com", "jobisjob.com",
    "jobleads.com", "pangian.com", "dailyremote.com", "remoterocketship.com",
    "devitjobs.com", "novaedge.com", "twine.net", "applytojob.com",
    "dataannotation.tech", "dataannotation", "pitchmeai.com", "pitchmeai",
    "jobflarely", "liveblog365.com", "remotelyusajobs.com",
    "hireza.com", "hireza", "synergisticit.com", "synergisticit",
    "trabajo.org", "naukri.com", "naukri", "jobright.ai", "jobright",
    "energyjobline.com", "lockedinai.com", "whatjobs.com",
    "trovit.com", "travajo.com", "talents.vaia.com",
    "remotica.totalh.net", "totalh.net", "remotica",
    "smartworking.com", "smart-working-solutions",
    "jobera.com", "workingnomads.com",
    "jobsearcher.com", "remotejobsanywhere.com",
]

def is_blocked_site(url):
    url_lower = str(url).lower()
    return any(site in url_lower for site in BLOCKED_JOB_SITES)

# ─── STALE / CLOSED JOB DETECTION ───────────────────────────
STALE_AGE_PATTERNS = [
    re.compile(r'\b([2-9]|1[0-9])\s+months?\s+ago\b', re.IGNORECASE),
    re.compile(r'\b[1-9]\d*\s+years?\s+ago\b', re.IGNORECASE),
]

CLOSED_SNIPPET_PHRASES = [
    "no longer accepting", "position filled", "job closed",
    "no longer available", "applications closed",
    "not accepting applications", "reposted", "re-posted",
]

def is_stale_or_closed(title, snippet, posted=""):
    text = (title + " " + snippet + " " + str(posted)).lower()
    for phrase in CLOSED_SNIPPET_PHRASES:
        if phrase in text:
            return True
    full_text = title + " " + snippet
    for pattern in STALE_AGE_PATTERNS:
        if pattern.search(full_text):
            return True
    return False

# ─── BLOCKED COMPANIES ───────────────────────────────────────
# Known staffing body shops, resume harvesters, sketchy recruiters
BLOCKED_COMPANIES = [
    "crossing hurdles", "synergisticit", "synergistic it",
    "hiretual", "hireza", "teksystems", "infosys bpm",
    "hcltech", "wipro", "cognizant", "mphasis",
    "international contract bench", "contract bench",
    "bench sales", "bench marketing",
    "staffing solutions", "staffing inc", "staffing llc",
    "global staffing", "talent staffing",
    "it staffing", "cyber staffing",
    # Fake/bot company names
    "asistente virtual", "virtual assistant", "confidential company",
    "undisclosed company", "anonymous employer",
]

# Platform/source names that appear in organic results — NOT real company names
PLATFORM_NAMES = {
    "n/a", "na", "none", "", "unknown", "lever", "greenhouse",
    "linkedin", "wellfound", "angel.co", "dice", "clearancejobs",
    "google jobs", "indeed", "ziprecruiter", "ashby", "ashbyhq",
}

def is_blocked_company(company):
    """Only blocks when we have a real employer name, not a platform/source name."""
    c = str(company).lower().strip()
    if not c or c in PLATFORM_NAMES:
        return False  # Can't evaluate from organic results — let other filters handle it
    return any(blocked in c for blocked in BLOCKED_COMPANIES)

# ─── SKETCHY JOB PATTERNS ────────────────────────────────────
SKETCHY_TITLE_PATTERNS = [
    "contract bench", "international contract", "bench sales",
    "bench marketing", "c2c", "corp to corp",
    "resume harvest", "talent pool", "talent pipeline",
    "promoted by hirer",
    # Foreign company hiring patterns
    "accenture belgium", "accenture india", "accenture uk",
]

def is_sketchy_job(title, description):
    text = (title + " " + description).lower()
    return any(pattern in text for pattern in SKETCHY_TITLE_PATTERNS)

# ─── NON-US LOCATION FILTER ──────────────────────────────────
NON_US_LOCATIONS = [
    "india", "bangalore", "bengaluru", "mumbai", "delhi", "hyderabad",
    "chennai", "pune", "kolkata", "noida", "gurugram", "gurgaon",
    "cochin", "coimbatore", "kochi", "indore", "jaipur", "ahmedabad",
    "karnataka", "maharashtra", "tamil nadu",
    "canada", "toronto", "vancouver", "montreal", "ontario",
    "united kingdom", "london", "manchester",
    "australia", "germany", "france", "netherlands",
    "belgium", "brussels", "antwerp",
    "spain", "madrid", "barcelona",
    "italy", "rome", "milan",
    "sweden", "norway", "denmark", "finland",
    "singapore", "philippines", "zambia", "indonesia",
    "remote in canada", "remote in uk", "remote in europe",
    "remote in india", "europe, remote", "emea remote",
    "apac remote", "latam remote",
    "markham, on", "markham, ontario",
]

# KC Metro areas Evan can commute to
KC_METRO_LOCATIONS = [
    "kansas city", "lee's summit", "lees summit", "independence",
    "overland park", "olathe", "shawnee", "lenexa", "leawood",
    "prairie village", "mission", "merriam", "belton", "raymore",
    "blue springs", "liberty", "gladstone", "north kansas city",
    "grandview", "raytown", "kc metro", "greater kansas city",
    "kansas city, mo", "kansas city, ks", "kcmo", "kcks",
    "overland park, ks", "olathe, ks",
]

# Non-KC cities — block unconditionally (Evan can't commute there)
BLOCKED_ONSITE_CITIES = [
    # Texas
    "the woodlands", "woodlands, tx", "houston", "dallas", "austin", "san antonio",
    # Northeast
    "new york", "boston", "philadelphia", "baltimore", "washington, dc",
    "richmond, va", "pittsburgh",
    # Midwest (non-KC)
    "chicago", "detroit", "cleveland", "columbus", "cincinnati",
    "indianapolis", "milwaukee", "minneapolis", "st. louis", "st louis",
    "omaha",
    # Southeast
    "atlanta", "miami", "charlotte", "raleigh", "nashville", "memphis",
    # West
    "seattle", "portland", "san francisco", "los angeles", "sacramento",
    "denver", "salt lake city", "phoenix", "scottsdale", "tempe",
    "chandler", "mesa, az", "gilbert, az", "glendale, az",
    # Other
    "madison, wi", "madison wi", "smoketown", "lancaster, pa",
    "tulsa", "oklahoma city",
]

# Non-English words that indicate foreign job postings
NON_ENGLISH_INDICATORS = [
    "nagha-hire", "sedang mencari", "nous recherchons", "wir suchen",
    "estamos buscando", "cercamos", "stiamo cercando",
    "op zoek naar", "vi søger", "vi söker",
    "asistente virtual", "asistente",
]

def is_non_english_posting(title, description):
    text = (title + " " + description).lower()
    return any(indicator in text for indicator in NON_ENGLISH_INDICATORS)

def is_valid_evan_location(title, description, location=""):
    """
    Returns True if job is:
    1. Remote (anywhere in US) OR
    2. In KC Metro area (hybrid/onsite OK)
    Returns False if:
    - International location
    - Onsite/hybrid in non-KC city
    - Closed job
    """
    import re as _re
    loc_lower = location.lower().strip()
    check = (title + " " + description + " " + location).lower()

    # Check closed jobs first
    closed = [
        "no longer accepting", "position filled", "job closed",
        "no longer available", "this job is closed", "expired",
        "applications closed", "not accepting applications",
        "reposted", "re-posted",
    ]
    for c in closed:
        if c in check:
            return False

    # Block non-English postings
    for indicator in NON_ENGLISH_INDICATORS:
        if indicator in check:
            return False

    # Block non-US locations
    for indicator in NON_US_LOCATIONS:
        if indicator.strip() in check:
            return False

    # Block non-KC cities unconditionally — Evan can't commute there regardless
    for blocked_city in BLOCKED_ONSITE_CITIES:
        if blocked_city in check:
            return False

    # If it mentions KC Metro — always allow (remote, hybrid, or onsite)
    for kc_loc in KC_METRO_LOCATIONS:
        if kc_loc in check:
            return True

    # If it's onsite/hybrid WITHOUT KC mention — reject
    # (Evan can't commute to Chicago, NYC, etc.)
    onsite_indicators = [
        "on-site", "onsite", "on site", "in-office", "in office",
        "hybrid", "in person", "in-person",
    ]
    is_onsite = any(ind in check for ind in onsite_indicators)

    if is_onsite:
        # Check if it's a KC location we might have missed
        if any(kc in check for kc in ["missouri", " mo,", ", mo ", "kansas city", "kcmo"]):
            return True
        # Onsite/hybrid but not KC — reject
        return False

    # Remote job — check it's US only (not state restricted to non-MO state)
    us_states = [
        "alabama", "alaska", "arizona", "arkansas", "california",
        "colorado", "connecticut", "delaware", "florida", "georgia",
        "hawaii", "idaho", "illinois", "indiana", "iowa", "kansas",
        "kentucky", "louisiana", "maine", "maryland", "massachusetts",
        "michigan", "minnesota", "mississippi", "montana", "nebraska",
        "nevada", "new hampshire", "new jersey", "new mexico", "new york",
        "north carolina", "north dakota", "ohio", "oklahoma", "oregon",
        "pennsylvania", "rhode island", "south carolina", "south dakota",
        "tennessee", "texas", "utah", "vermont", "virginia",
        "washington", "west virginia", "wisconsin", "wyoming",
    ]
    state_restriction_patterns = [
        r"must (live|reside|be located|be based) in",
        r"only (open|available) to .{0,30} residents?",
        r"may only be hired in.{0,100}location",
        r"only be hired in the following location",
        r"need only locals", r"local candidates? only",
    ]
    for pattern in state_restriction_patterns:
        if _re.search(pattern, check):
            mo_mentioned = "missouri" in check or " mo " in check or "kansas city" in check
            other_state = any(s in check for s in us_states)
            if not mo_mentioned or other_state:
                return False

    return True

# Keep is_us_location as alias for compatibility
def is_us_location(title, description, location=""):
    return is_valid_evan_location(title, description, location)

# ─── SCORING KEYWORDS ────────────────────────────────────────
# All job types weighted equally as requested
CYBERSEC_KEYWORDS = {
    # SOC / Security Operations
    "soc analyst": 50, "security operations": 40, "security operations center": 40,
    "soc tier": 40, "tier 1 soc": 50, "tier 2 soc": 50, "l1 soc": 40,
    "mdr analyst": 50, "managed detection": 40, "managed detection and response": 50,
    "security operations analyst": 50,

    # Cybersecurity Analyst
    "cybersecurity analyst": 50, "cyber analyst": 40, "information security analyst": 50,
    "infosec analyst": 40, "security analyst": 40,

    # Vulnerability Management
    "vulnerability management": 50, "vulnerability analyst": 50,
    "vulnerability assessment": 40, "vulnerability scanning": 35,
    "vulnerability management analyst": 50,

    # Incident Response
    "incident response": 50, "incident response analyst": 50,
    "ir analyst": 40, "digital forensics": 35, "dfir": 50,

    # Penetration Testing
    "penetration tester": 50, "penetration testing": 40,
    "junior penetration tester": 50, "junior pen tester": 50,
    "pen tester": 40, "ethical hacker": 35, "red team": 35,

    # Entry level / Internship keywords
    "internship": 40, "entry level": 30,
    "new grad": 35, "recent graduate": 35, "graduate program": 30,
    "0-2 years": 20, "0-1 years": 20, "less than 1 year": 20,
    "no experience required": 25, "entry-level": 30,
    "associate analyst": 40, "associate security": 40,

    # Federal/Government cybersecurity roles
    "information technology specialist": 40,
    "it specialist": 20, "it cybersecurity": 40,
    "information security specialist": 50,
    "cybersecurity specialist": 50,
    "cyber workforce": 30, "it security": 30,
    "network security": 20, "infosec": 30,
    "public trust": 20, "secret clearance": 25,
    "top secret": 20, "ts/sci": 20,
    "splunk": 20, "microsoft sentinel": 20, "siem": 20,
    "nessus": 20, "openvas": 20, "qualys": 20,
    "security+": 15, "comptia security": 15,
    "aws security": 15, "cloud security": 15,
    "active directory": 15, "iam": 10,
    "threat detection": 20, "threat hunting": 25,
    "log analysis": 15, "ids": 10, "ips": 10,
    "firewall": 10, "network security": 15,
    "public trust": 20, "clearance": 15,
}

TITLE_KEYWORDS = [
    "soc analyst", "security operations", "cybersecurity analyst",
    "cyber analyst", "security analyst", "mdr analyst",
    "vulnerability management", "vulnerability analyst",
    "incident response", "penetration tester", "pen tester",
    "information security analyst", "infosec analyst",
    "security engineer", "threat analyst", "threat hunter",
    "dfir analyst", "junior security", "entry level security",
    "junior cyber", "entry level cyber", "tier 1", "tier 2",
    # Federal/USAJobs title variants
    "information technology specialist",
    "it specialist", "it cybersecurity",
    "information security specialist",
    "cyber workforce", "cybersecurity specialist",
    "it security", "network security",
    # Internships
    "security intern", "cybersecurity intern", "soc intern",
    "security internship", "cybersecurity internship",
    "information security intern", "cyber intern",
]

EXCLUDED_TITLES = [
    "engineering manager", "director", "vp ", "vice president",
    "head of", "chief", "cto", "ciso",
    "sales engineer", "solutions engineer", "pre-sales",
    "freelance", "part-time", "part time",
    "principal engineer", "staff engineer", "staff security", "staff analyst",
    "senior principal",
    "sr. information security", "sr information security",
    "sr. security analyst", "sr security analyst",
    # Senior/experienced exclusions - Evan is entry level
    "senior security engineer", "senior analyst", "senior soc",
    "senior cybersecurity", "senior cyber", "senior information security",
    "senior vulnerability", "senior incident", "senior penetration",
    "sr. soc", "sr soc", "sr. analyst", "sr analyst",
    "sr. cyber", "sr cyber", "sr. security", "sr security",
    "sr. information", "sr. vulnerability", "sr. incident",
    "sr cybersecurity", "sr. cybersecurity",
    "senior cyber security", "senior cybersecurity analyst",
    "lead analyst", "lead soc", "lead security analyst",
    "principal analyst", "staff analyst",
    "analyst ii", "analyst iii", "analyst iv",
    "analyst 2", "analyst 3", "analyst 4",
    "level ii", "level iii", "level 2", "level 3",
    "team lead", "tech lead", "technical lead",
    "manager", "supervisor",
    "senior security analyst", "senior threat", "senior dfir",
    "senior security operations", "senior soc engineer",
    "senior security operations engineer", "senior security operations analyst",
    "senior detection", "senior response analyst",
    "senior engineer", "senior security engineer",
    "experienced security", "experienced analyst",
    "level 3", "level 4", "level iii", "level iv",
    "tier 3", "tier 4", "tier iii",
    "lead penetration", "lead security", "lead soc", "lead cyber",
    "l3 soc", "l2 soc", "l3 analyst", "soc lead",
    "vulnerability management lead", "vulnerability lead",
    "tier 2", "tier ii", "tier 2 soc", "tier ii soc",
]

def has_too_much_experience(title, description):
    """Returns True if job requires more experience than Evan has (new grad)."""
    import re as _re
    text = (title + " " + description).lower()

    # Immediately pass internships/entry-level regardless of experience mention
    if any(kw in text for kw in ["intern", "internship", "new grad", "recent graduate", "entry level", "entry-level"]):
        return False

    # Block jobs requiring 2+ years experience (Evan has <1 year professional)
    exp_patterns = [
        r"(\d+)\+\s*years?\s*(of\s*)?(experience|exp)",
        r"(\d+)\s*\+\s*years?\s*(of\s*)?(experience|exp)",
        r"(\d+)\s*to\s*(\d+)\s*years?\s*(of\s*)?(experience|exp)",
        r"(\d+)\s*-\s*(\d+)\s*years?\s*(of\s*)?(experience|exp)",
        r"minimum\s*(of\s*)?(\d+)\s*years?",
        r"at least\s*(\d+)\s*years?",
        r"(\d+)\s*years?\s*of\s*(relevant|related|professional|work|hands.on)",
        r"requires?\s*(\d+)\s*years?",
        r"(\d+)\s*years?\s*(experience|exp)\s*(required|preferred|minimum)",
        r"(\d+)\s*years?\s*(in|of)\s*(security|cybersecurity|soc|infosec)",
        r"progressive\s*experience",
        r"(\d+)\s*years?\s*(progressive|demonstrated)",
    ]
    for pattern in exp_patterns:
        matches = _re.findall(pattern, text)
        for match in matches:
            try:
                first_num = next((x for x in match if x and x.isdigit()), None)
                if first_num and int(first_num) >= 2:
                    return True
            except:
                pass

    # Block senior/advanced certifications Evan doesn't have
    senior_certs = [
        "cissp", "cism", "ceh", "oscp", "gcia", "gcih", "gpen", "gwapt",
        "gcfe", "gcfa", "gnfa", "grem", "gsec", "casp+", "casp",
        "certified information security manager",
        "certified information systems security",
        "certified ethical hacker",
        "offensive security certified",
    ]
    if any(cert in text for cert in senior_certs):
        return True

    # Block strong seniority language
    strong_exp_phrases = [
        "extensive experience", "proven track record",
        "seasoned professional", "expert level",
        "deep expertise", "extensive background",
        "subject matter expert", "sme ",
        "advanced knowledge of", "advanced experience",
        "highly experienced", "demonstrated expertise",
        "years of hands-on", "significant experience",
        "five years", "five (5) years", "four years", "four (4) years",
        "three years", "three (3) years",
    ]
    if any(phrase in text for phrase in strong_exp_phrases):
        return True

    return False

def clean_title(title):
    """Strip common prefixes that mask the real job title."""
    if not title:
        return ""
    t = str(title).strip()
    prefixes = [
        "job application for ", "apply for ", "apply now: ",
        "hiring: ", "now hiring: ", "careers: ",
    ]
    for p in prefixes:
        if t.lower().startswith(p):
            t = t[len(p):]
    return t.strip()

def is_relevant_title(title):
    import re as _re
    title = clean_title(title)
    t = title.lower()
    # Search page detection
    search_patterns = [
        r"\d+\s+(remote|jobs|vacancies|openings)",
        r"jobs in remote", r"now hiring", r"\d+,\d+ .* jobs",
    ]
    for p in search_patterns:
        if _re.search(p, t):
            return False
    if not any(kw in t for kw in TITLE_KEYWORDS):
        return False
    if any(excl in t for excl in EXCLUDED_TITLES):
        return False
    return True

def score_job(title, description):
    """
    Score title keywords at full value (capped at 100),
    description keywords at 40% (capped at 60).
    Prevents keyword-stuffed descriptions from inflating scores.
    Max possible score: 160 for a perfect title+desc match.
    """
    title_text = clean_title(title or "").lower()
    desc_text = str(description or "").lower()

    title_score = 0
    desc_score = 0
    matched = []

    for kw, pts in CYBERSEC_KEYWORDS.items():
        in_title = kw in title_text
        in_desc = kw in desc_text

        if in_title:
            title_score += pts
            if kw not in matched:
                matched.append(kw)
        elif in_desc:
            desc_score += int(pts * 0.4)
            if kw not in matched:
                matched.append(kw)

    # Cap each component to prevent runaway stacking
    title_score = min(title_score, 100)
    desc_score = min(desc_score, 60)

    return title_score + desc_score, matched

def get_job_track(title, description):
    t = title.lower()
    text = (title + " " + description).lower()
    if any(kw in t for kw in ["intern", "internship"]):
        return "Security Internship"
    if any(kw in t for kw in ["penetration tester", "pen tester", "ethical hacker", "red team"]):
        return "Junior Pen Tester"
    if any(kw in text for kw in ["incident response", "dfir", "digital forensics"]):
        return "Incident Response"
    if any(kw in text for kw in ["vulnerability management", "vulnerability analyst", "vulnerability scanning"]):
        return "Vulnerability Management"
    if any(kw in text for kw in ["mdr analyst", "managed detection"]):
        return "MDR Analyst"
    if any(kw in text for kw in ["soc analyst", "security operations center", "tier 1", "tier 2"]):
        return "SOC Analyst"
    return "Cybersecurity Analyst"

# ─── DATE / FRESHNESS ────────────────────────────────────────
def parse_relative_date(date_str):
    import re
    s = str(date_str).lower().strip()
    now = datetime.now(timezone.utc)
    match = re.match(r"(\d+)\s+(second|minute|hour|day|week|month|year)s?\s+ago", s)
    if match:
        amount = int(match.group(1))
        unit = match.group(2)
        delta_map = {
            "second": timedelta(seconds=amount),
            "minute": timedelta(minutes=amount),
            "hour":   timedelta(hours=amount),
            "day":    timedelta(days=amount),
            "week":   timedelta(weeks=amount),
            "month":  timedelta(days=amount*30),
            "year":   timedelta(days=amount*365),
        }
        return now - delta_map[unit]
    try:
        parsed = dateparser.parse(str(date_str))
        if parsed:
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed
    except:
        pass
    return None

def is_recent(date_str, max_hours=None):
    if not date_str:
        return False
    parsed = parse_relative_date(str(date_str))
    if not parsed:
        return False
    now = datetime.now(timezone.utc)
    age = now - parsed
    limit = max_hours if max_hours else MAX_AGE_HOURS
    return age <= timedelta(hours=limit)

# ─── SEEN JOBS (with 7-day expiry) ──────────────────────────
SEEN_JOBS_EXPIRY_DAYS = 3

def load_seen_jobs():
    """Returns a set of URLs seen within the last 7 days."""
    if not os.path.exists(SEEN_JOBS_FILE):
        return set()
    try:
        with open(SEEN_JOBS_FILE, "r") as f:
            data = json.load(f)

        # Handle legacy flat list format (migrate on first load)
        if isinstance(data, list):
            print(f"   [INFO] Migrating seen_jobs to expiry format ({len(data)} entries)")
            cutoff = datetime.now(timezone.utc) - timedelta(days=SEEN_JOBS_EXPIRY_DAYS)
            # Assume all legacy entries were seen today (conservative)
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            migrated = {url: today for url in data}
            with open(SEEN_JOBS_FILE, "w") as f:
                json.dump(migrated, f, indent=2)
            return set(data)

        # New dict format: {url: "YYYY-MM-DD"}
        cutoff = datetime.now(timezone.utc) - timedelta(days=SEEN_JOBS_EXPIRY_DAYS)
        active = set()
        for url, date_str in data.items():
            try:
                seen_date = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                if seen_date >= cutoff:
                    active.add(url)
            except:
                active.add(url)  # Keep if date unparseable
        return active
    except Exception as e:
        print(f"[WARN] Could not load seen jobs: {e}")
        return set()

def save_seen_jobs(urls):
    """Save URLs with today's date, prune entries older than 7 days."""
    try:
        # Load existing dict (handle legacy)
        existing_dict = {}
        if os.path.exists(SEEN_JOBS_FILE):
            try:
                with open(SEEN_JOBS_FILE, "r") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                    existing_dict = {url: today for url in data}
                else:
                    existing_dict = data
            except:
                pass

        # Add new URLs with today's date
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        for url in urls:
            if url and url not in existing_dict:
                existing_dict[url] = today

        # Prune entries older than expiry
        cutoff = datetime.now(timezone.utc) - timedelta(days=SEEN_JOBS_EXPIRY_DAYS)
        pruned = {
            url: date_str for url, date_str in existing_dict.items()
            if _try_parse_date(date_str) >= cutoff
        }
        removed = len(existing_dict) - len(pruned)
        if removed > 0:
            print(f"   [INFO] Pruned {removed} expired entries from seen_jobs (>{SEEN_JOBS_EXPIRY_DAYS} days old)")

        with open(SEEN_JOBS_FILE, "w") as f:
            json.dump(pruned, f, indent=2)
    except Exception as e:
        print(f"[WARN] Could not save seen jobs: {e}")

def _try_parse_date(date_str):
    """Parse YYYY-MM-DD, return epoch on failure so old entries get pruned."""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except:
        return datetime(2000, 1, 1, tzinfo=timezone.utc)

# ─── SEARCH PAGE FILTER ──────────────────────────────────────
SEARCH_PAGE_INDICATORS = [
    "jobs?q=", "job-search?", "jobs-search?", "/jobs/search",
    "/jobs?", "search?q=", "find-jobs",
    "indeed.com/jobs", "indeed.com/q-",
    "linkedin.com/jobs/search",
    "glassdoor.com/Job/jobs", "glassdoor.com/Job/remote",
    "ziprecruiter.com/Jobs/",
    "naukri.com/",
    "jobs-in-remote", "remote-jobs-in",
    "/remote-jobs?",
    "clearancejobs.com/jobs?", "clearancejobs.com/search",
    "dice.com/jobs?", "dice.com/q-",
    "simplyhired.com/search",
    "themuse.com/jobs",
    "simplyhired.com",
    # Block all Cloudflare careers pages
    "cloudflare.com/careers",
    "/careers/open-positions", "/careers/jobs",
    "/open-positions", "/life-at-",
    "/early-talent",
    # Block all LinkedIn job URLs — unreliable closed job data
    "linkedin.com/jobs/view",
    "linkedin.com/jobs/search",
    # Salary/compensation sites
    "salary.com", "salaryexpert.com", "payscale.com",
    "glassdoor.com/Salaries", "indeed.com/career/",
    "ziprecruiter.com/Salaries", "levels.fyi",
    "comparably.com", "careerbliss.com",
    # Certification/training sites
    "comptia.org", "examtopics.com", "udemy.com",
    "coursera.org", "pluralsight.com", "cybrary.it",
    "sans.org", "isc2.org", "eccouncil.org",
    # News/blog/aggregator
    "builtin.com/jobs", "builtinkc.com",
    "zippia.com", "betterteam.com", "jobhero.com",
]

SEARCH_PAGE_TITLE_PATTERNS = [
    r"\d+\s+(remote|jobs|vacancies|openings|positions)",
    r"jobs in remote", r"jobs in kansas",
    r"now hiring", r"\d+,\d+ .* jobs",
    r"latin america", r"latam",
    r"\$\d+k.*jobs", r"\$\d+-\$\d+.*jobs",
    r"jobs, employment",
    r"jobs \| indeed", r"jobs - indeed",
    r"jobs \(now hiring\)",
    r"flexible.*remote.*jobs",
    r"remote.*jobs.*indeed",
    r"help us build", r"join our team",
    r"open positions", r"life at \w+",
    r"careers at \w+", r"work at \w+",
    # Salary pages
    r"yearly salaries", r"annual salaries", r"average salary",
    r"salary in the", r"salaries in the", r"\$\d+.*salary",
    r"salary range", r"how much does", r"hourly pay",
    r"\$\d+k-\$\d+k", r"\$\d+/hr", r"\$\d+-\$\d+/hr",
    # Certification/training pages
    r"cysa\+", r"cs0-00", r"comptia.*exam", r"certification exam",
    r"study guide", r"practice test", r"exam prep",
    r"security\+ exam", r"cissp exam", r"ceh exam",
    # Aggregator/listing pages
    r"best.*jobs in", r"\d+ best.*jobs",
    r"top \d+.*jobs", r"find.*jobs near",
    r"jobs near me", r"hiring near",
    r"job listings", r"employment in",
    r"jobs, employment in",
    r"now hiring in", r"apply.*today",
    r"\d+.*jobs.*found", r"see all.*jobs",
    r"\d+ .* jobs in ", r"\d+ .* analyst jobs",
    r"entry level .* jobs$", r"jobs \(now hiring\)",
    r"jobs in independence", r"jobs in kansas city",
    r"jobs in overland park", r"jobs in lenexa",
    r"jobs in olathe", r"jobs in lee.s summit",
    r"jobs closing soon", r"closing soon",
    r"analyst jobs$", r"security jobs$",
    r"cybersecurity jobs$", r"analyst jobs\b",
    # News/blog pages
    r"what is a.*analyst", r"how to become",
    r"career guide", r"job description for",
    r"day in the life", r"interview questions",
]

def is_search_page(url, title=""):
    url_lower = str(url).lower()
    if any(ind in url_lower for ind in SEARCH_PAGE_INDICATORS):
        return True
    import re as _re
    t = title.lower()
    for p in SEARCH_PAGE_TITLE_PATTERNS:
        if _re.search(p, t):
            return True
    return False

# ─── SOURCE 1: RemoteOK ──────────────────────────────────────
def search_remoteok():
    print("[SEARCH] Searching RemoteOK...")
    jobs = []
    tags = ["cybersecurity", "security", "soc-analyst", "penetration-testing",
            "information-security", "cloud-security"]
    seen = set()
    for tag in tags:
        try:
            url = f"https://remoteok.com/api?tag={tag}"
            headers = {"User-Agent": "Mozilla/5.0"}
            resp = requests.get(url, headers=headers, timeout=15)
            data = resp.json()
            items = [x for x in data if isinstance(x, dict) and x.get("position")]
            for item in items:
                title   = item.get("position", "")
                desc    = item.get("description", "")
                url_job = item.get("url", "")
                posted  = item.get("date", "")
                if url_job in seen:
                    continue
                seen.add(url_job)
                score, matched = score_job(title, desc)
                track = get_job_track(title, desc)
                if DEBUG_MODE and title:
                    if not is_relevant_title(title):
                        print(f"   [DEBUG] RemoteOK FILTERED-title: {title[:60]}")
                        continue
                    if score == 0:
                        print(f"   [DEBUG] RemoteOK FILTERED-score: {title[:60]}")
                        continue
                if score > 0 and is_recent(posted) and is_relevant_title(title) and is_us_location(title, desc) and not is_blocked_site(url_job):
                    jobs.append({
                        "source": "RemoteOK", "title": title,
                        "company": ", ".join(item.get("tags", [])[:2]),
                        "url": url_job, "posted": posted,
                        "description": desc[:500], "score": score,
                        "matched_keywords": matched, "track": track,
                    })
        except Exception as e:
            print(f"   [ERROR] RemoteOK error ({tag}): {e}")
    print(f"   [OK] RemoteOK: {len(jobs)} relevant jobs found")
    return jobs

# ─── SOURCE 2: Serper Google Jobs ────────────────────────────
def search_serper():
    print("[SEARCH] Searching Google Jobs via Serper...")
    jobs = []
    if not SERPER_API_KEY or SERPER_API_KEY == "YOUR_SERPER_KEY":
        print("   [WARN] Serper skipped - no API key")
        return jobs

    queries = [
        # Direct company job boards - SOC/Security
        'site:jobs.lever.co "SOC analyst" remote',
        'site:boards.greenhouse.io "SOC analyst" remote',
        'site:jobs.ashbyhq.com "security analyst" remote',
        'site:careers.crowdstrike.com "analyst" remote',
        'site:jobs.lever.co "cybersecurity analyst" remote',
        'site:boards.greenhouse.io "security operations" remote',

        # Direct Dice job links
        'site:dice.com/job-detail "SOC analyst" remote',
        'site:dice.com/job-detail "cybersecurity analyst" remote',
        'site:dice.com/job-detail "vulnerability management" remote',
        'site:dice.com/job-detail "incident response" remote',

        # USAJobs direct
        'site:usajobs.gov "cybersecurity analyst"',
        'site:usajobs.gov "information security analyst"',

        # KC Metro broad searches — catches all employers in the area
        '"SOC analyst" "kansas city" remote OR hybrid',
        '"cybersecurity analyst" "kansas city" remote OR hybrid',
        '"security analyst" "kansas city" OR "overland park" OR "lenexa"',
        '"security analyst" "lee\'s summit" OR "independence" OR "blue springs"',
        '"information security analyst" "kansas city"',
        '"incident response" "kansas city" entry level',
        '"vulnerability analyst" "kansas city"',
        '"cybersecurity" "kansas city" entry level OR junior OR associate',

        # Healthcare / Hospitals KC
        '"cybersecurity" OR "security analyst" "kansas city" hospital OR health OR medical',
        '"University of Kansas Health" "cybersecurity" OR "security"',
        '"Children\'s Mercy" "cybersecurity" OR "security analyst"',
        '"Saint Luke\'s" "cybersecurity" OR "information security"',
        '"Truman Medical" OR "University Health" "cybersecurity" OR "security"',
        '"HCA Healthcare" "cybersecurity" OR "SOC analyst" "kansas city"',
        '"CVS Health" OR "Cerner" "cybersecurity analyst" "kansas city"',

        # Banking / Finance KC
        '"cybersecurity" OR "security analyst" "kansas city" bank OR financial OR insurance',
        '"UMB Financial" "cybersecurity" OR "security analyst"',
        '"Commerce Bank" "cybersecurity" OR "security analyst"',
        '"Cerner" OR "Oracle Health" "security" OR "SOC" "kansas city"',
        '"Armed Forces Bank" OR "nbkc bank" "cybersecurity" OR "security"',
        '"Kansas City Life Insurance" "cybersecurity" OR "security"',
        '"Blue Cross Blue Shield" "cybersecurity" OR "SOC" "kansas city"',
        '"Waddell & Reed" OR "Ivy Investments" "cybersecurity" "kansas city"',

        # Government / Federal KC
        '"cybersecurity" OR "security analyst" "kansas city" government OR federal OR agency',
        '"IRS" "cybersecurity" OR "information security" "kansas city"',
        '"VA" OR "Veterans Affairs" "cybersecurity" "kansas city"',
        '"Social Security Administration" "cybersecurity" "kansas city"',
        '"Department of Agriculture" "cybersecurity" "kansas city"',
        '"GSA" OR "general services" "cybersecurity" "kansas city"',

        # Utilities / Energy KC
        '"Evergy" "security" OR "cybersecurity" OR "SOC"',
        '"Black & Veatch" "cybersecurity" OR "security analyst"',
        '"Burns & McDonnell" "cybersecurity" OR "security"',
        '"KCPL" OR "Kansas City Power" "cybersecurity" OR "security"',

        # Retail / Logistics KC
        '"cybersecurity" OR "security analyst" "kansas city" retail OR logistics OR supply chain',
        '"Cerner" OR "Oracle Health" "cybersecurity" entry level',
        '"H&R Block" "cybersecurity" OR "security analyst" "kansas city"',
        '"VinSolutions" "security analyst" OR "cybersecurity"',
        '"Lockton" "security analyst" OR "cybersecurity"',
        '"Garmin" "cybersecurity" OR "security analyst" remote OR "olathe"',
        '"DST Systems" OR "SS&C" "security analyst" "kansas city"',

        # Specific KC employers on major ATS boards
        'site:oracle.com/careers "security" OR "SOC" "kansas city"',
        'site:garmin.com/careers "cybersecurity" OR "security analyst"',
        'site:careers.hrblock.com "security" OR "cybersecurity"',
        'site:jobs.lever.co OR site:boards.greenhouse.io "kansas city" "security"',

        # Direct job board postings
        'site:jobs.lever.co "incident response" remote',
        'site:boards.greenhouse.io "vulnerability management" remote',
        'site:jobs.ashbyhq.com "penetration" OR "pen test" remote',

        # Internships — no LinkedIn
        'site:dice.com/job-detail "security intern" OR "cybersecurity intern"',
        'site:boards.greenhouse.io "security intern" remote',
        'site:jobs.lever.co "security intern" OR "cybersecurity internship"',
        'site:jobs.ashbyhq.com "security internship" OR "cyber intern" 2026',
    ]

    seen = set()
    for query in queries:
        try:
            url = "https://google.serper.dev/search"
            headers = {"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"}
            payload = {"q": query, "gl": "us", "hl": "en", "num": 10}
            resp = requests.post(url, headers=headers, json=payload, timeout=15)
            if resp.status_code == 400:
                if DEBUG_MODE:
                    print(f"   [DEBUG] Serper '{query}': rate limited (400), skipping")
                time.sleep(3)
                continue
            data = resp.json()
            if DEBUG_MODE:
                print(f"   [DEBUG] Serper '{query}': {len(data.get('jobs',[]))} jobs, {len(data.get('organic',[]))} organic, status {resp.status_code}")

            all_results = data.get("jobs", []) + data.get("organic", [])
            for item in all_results:
                title    = item.get("title", "")
                company  = item.get("company", item.get("source", "N/A"))
                desc     = item.get("description", item.get("snippet", ""))
                url_job  = item.get("applyLink", "") or item.get("link", "") or item.get("url", "")
                posted   = item.get("date", item.get("publishedDate", ""))
                location = item.get("location", "")

                if is_search_page(url_job, title):
                    if DEBUG_MODE:
                        print(f"   [DEBUG] Serper FILTERED-searchpage: {title[:50]}")
                    continue
                if is_stale_or_closed(title, desc, posted):
                    if DEBUG_MODE:
                        print(f"   [DEBUG] Serper FILTERED-stale/closed: {title[:50]}")
                    continue
                if is_non_english_posting(title, desc):
                    if DEBUG_MODE:
                        print(f"   [DEBUG] Serper FILTERED-non-english: {title[:50]}")
                    continue
                if is_blocked_company(title):  # company name often appears in title for LinkedIn
                    if DEBUG_MODE:
                        print(f"   [DEBUG] Serper FILTERED-company-in-title: {title[:50]}")
                    continue
                if is_sketchy_job(title, desc):
                    if DEBUG_MODE:
                        print(f"   [DEBUG] Serper FILTERED-sketchy: {title[:50]}")
                    continue
                if url_job in seen:
                    continue
                seen.add(url_job)

                score, matched = score_job(title, desc)
                track = get_job_track(title, desc)

                if score > 0 and is_relevant_title(title) and is_us_location(title, desc, location) and not is_blocked_site(url_job) and not has_too_much_experience(title, desc):
                    jobs.append({
                        "source": "Google Jobs", "title": title,
                        "company": company, "url": url_job,
                        "posted": posted, "description": desc[:500],
                        "score": score, "matched_keywords": matched, "track": track,
                    })
        except Exception as e:
            print(f"   [ERROR] Serper error ({query}): {e}")
        time.sleep(1.2)  # Rate limit: stay under Serper's burst threshold

    print(f"   [OK] Google Jobs: {len(jobs)} relevant jobs found")
    return jobs

# ─── SOURCE 3: Dice ──────────────────────────────────────────
def search_dice():
    print("[SEARCH] Searching Dice...")
    jobs = []
    queries = [
        "SOC analyst", "cybersecurity analyst", "security operations analyst",
        "MDR analyst", "vulnerability analyst", "incident response analyst",
        "junior penetration tester", "information security analyst",
    ]
    seen = set()
    for query in queries:
        try:
            q = requests.utils.quote(query)
            url = f"https://job-search-api.svc.dhigroupinc.com/v1/dice/jobs/search?q={q}&countryCode2=US&radius=30&radiusUnit=mi&page=1&pageSize=20&filters.workplaceTypes=Remote&language=en&eid=S2096"
            headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                items = data.get("data", [])
                if DEBUG_MODE:
                    print(f"   [DEBUG] Dice '{query}': {len(items)} raw results")
                for item in items:
                    title   = item.get("title", "")
                    company = item.get("companyPageUrl", item.get("advertiserName", "N/A"))
                    url_job = f"https://www.dice.com/job-detail/{item.get('id','')}"
                    posted  = item.get("postedDate", "")
                    desc    = item.get("jobDescription", "")[:500]
                    if url_job in seen:
                        continue
                    seen.add(url_job)
                    if is_stale_or_closed(title, desc, posted):
                        continue
                    if is_blocked_company(company):
                        continue
                    if is_sketchy_job(title, desc):
                        continue
                    score, matched = score_job(title, desc)
                    track = get_job_track(title, desc)
                    if score > 0 and is_recent(posted) and is_relevant_title(title) and is_us_location(title, desc) and not is_blocked_site(url_job) and not has_too_much_experience(title, desc):
                        jobs.append({
                            "source": "Dice", "title": title,
                            "company": company, "url": url_job,
                            "posted": posted, "description": desc,
                            "score": score, "matched_keywords": matched, "track": track,
                        })
        except Exception as e:
            print(f"   [ERROR] Dice error ({query}): {e}")
    print(f"   [OK] Dice: {len(jobs)} relevant jobs found")
    return jobs

# ─── SOURCE 4: USAJobs ───────────────────────────────────────
def search_usajobs():
    print("[SEARCH] Searching USAJobs...")
    jobs = []
    USAJOBS_KEY   = os.environ.get("USAJOBS_API_KEY", "")
    USAJOBS_EMAIL = os.environ.get("USAJOBS_EMAIL", "")
    queries = ["cybersecurity analyst", "SOC analyst", "information security",
               "security operations", "incident response", "vulnerability management"]
    for query in queries:
        try:
            url = "https://data.usajobs.gov/api/search"
            headers = {
                "Authorization-Key": USAJOBS_KEY,
                "User-Agent": USAJOBS_EMAIL,
                "Host": "data.usajobs.gov",
                "Accept": "application/json",
            }
            params = {"Keyword": query, "RemoteIndicator": "True",
                      "ResultsPerPage": 20, "SortField": "OpenDate", "SortDirection": "Desc"}
            resp = requests.get(url, headers=headers, params=params, timeout=15)
            data = resp.json()
            items = data.get("SearchResult", {}).get("SearchResultItems", [])
            if DEBUG_MODE:
                print(f"   [DEBUG] USAJobs '{query}': {len(items)} raw results, status {resp.status_code}")
            for item in items:
                mv    = item.get("MatchedObjectDescriptor", {})
                title = mv.get("PositionTitle", "")
                desc  = mv.get("QualificationSummary", "")
                posted = mv.get("PublicationStartDate", "")
                score, matched = score_job(title, desc)
                track = get_job_track(title, desc)
                # USAJobs uses ISO dates — check freshness manually
                posted_str = mv.get("PublicationStartDate", "")
                try:
                    from dateutil import parser as _dp
                    posted_dt = _dp.parse(posted_str)
                    if posted_dt.tzinfo is None:
                        posted_dt = posted_dt.replace(tzinfo=timezone.utc)
                    age_days = (datetime.now(timezone.utc) - posted_dt).days
                    if age_days > 30:  # Allow up to 30 days for federal roles
                        continue
                except:
                    pass  # If date unparseable, include anyway

                if score >= 30 and not has_too_much_experience(title, desc):
                    jobs.append({
                        "source": "USAJobs", "title": title,
                        "company": mv.get("OrganizationName", "Federal Agency"),
                        "url": mv.get("PositionURI", ""),
                        "posted": posted_str,
                        "description": desc[:500], "score": score,
                        "matched_keywords": matched, "track": track,
                    })
        except Exception as e:
            print(f"   [ERROR] USAJobs error ({query}): {e}")
    print(f"   [OK] USAJobs: {len(jobs)} relevant jobs found")
    return jobs

# ─── SOURCE 5: Greenhouse ────────────────────────────────────
def search_greenhouse():
    print("[SEARCH] Searching Greenhouse...")
    jobs = []
    companies = [
        # KC Metro employers — tech
        "oracle", "garmin", "h-r-block", "evergy", "lockton",
        "vinsolutions", "umb-bank", "commerce-bank", "burns-mcdonnell",
        # KC Metro — healthcare
        "childrens-mercy", "saint-lukes-health-system", "hca-healthcare",
        # Major cybersecurity companies (remote)
        "crowdstrike", "paloaltonetworks", "sentinelone", "splunk",
        "ibm", "cisco", "deloitte", "kpmg", "mandiant",
        "rapid7", "tenable", "qualys", "secureworks",
        # Consulting / staffing with heavy cyber practice
        "leidos", "saic", "booz-allen-hamilton", "mantech", "caci",
        "accenture", "cognizant", "infosys",
    ]
    seen = set()
    for company in companies:
        try:
            url = f"https://boards-api.greenhouse.io/v1/boards/{company}/jobs?content=true"
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                items = data.get("jobs", [])
                for item in items:
                    title   = item.get("title", "")
                    url_job = item.get("absolute_url", "")
                    desc    = item.get("content", "")[:500]
                    posted  = item.get("updated_at", "")
                    if url_job in seen:
                        continue
                    seen.add(url_job)
                    if is_stale_or_closed(title, desc, posted):
                        continue
                    if is_sketchy_job(title, desc):
                        continue
                    if has_too_much_experience(title, desc):
                        continue
                    score, matched = score_job(title, desc)
                    track = get_job_track(title, desc)
                    if score > 0 and is_relevant_title(title) and not is_blocked_site(url_job):
                        jobs.append({
                            "source": "Greenhouse", "title": title,
                            "company": company.title(), "url": url_job,
                            "posted": posted, "description": desc,
                            "score": score, "matched_keywords": matched, "track": track,
                        })
        except:
            pass
    print(f"   [OK] Greenhouse: {len(jobs)} relevant jobs found")
    return jobs

# ─── SOURCE 6: Lever ─────────────────────────────────────────
def search_lever():
    print("[SEARCH] Searching Lever...")
    jobs = []
    companies = [
        "crowdstrike", "sentinelone", "recordedfuture",
        "lacework", "snyk", "orca", "wiz",
    ]
    seen = set()
    for company in companies:
        try:
            url = f"https://api.lever.co/v0/postings/{company}?mode=json"
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                items = resp.json()
                for item in items:
                    title   = item.get("text", "")
                    url_job = item.get("hostedUrl", "")
                    desc    = item.get("descriptionPlain", "")[:500]
                    posted  = item.get("createdAt", "")
                    if posted:
                        try:
                            posted = datetime.fromtimestamp(int(posted)/1000, tz=timezone.utc).isoformat()
                        except:
                            pass
                    if url_job in seen:
                        continue
                    seen.add(url_job)
                    if is_stale_or_closed(title, desc, posted):
                        continue
                    if is_sketchy_job(title, desc):
                        continue
                    if has_too_much_experience(title, desc):
                        continue
                    score, matched = score_job(title, desc)
                    track = get_job_track(title, desc)
                    if score > 0 and is_relevant_title(title) and not is_blocked_site(url_job):
                        jobs.append({
                            "source": "Lever", "title": title,
                            "company": company.title(), "url": url_job,
                            "posted": posted, "description": desc,
                            "score": score, "matched_keywords": matched, "track": track,
                        })
        except:
            pass
    print(f"   [OK] Lever: {len(jobs)} relevant jobs found")
    return jobs

# ─── SOURCE 7: Wellfound ─────────────────────────────────────
def search_wellfound():
    print("[SEARCH] Searching Wellfound...")
    jobs = []
    if not SERPER_API_KEY:
        return jobs
    queries = [
        "site:wellfound.com SOC analyst remote",
        "site:wellfound.com cybersecurity analyst remote",
        "site:wellfound.com security operations remote",
        "site:wellfound.com vulnerability analyst remote",
    ]
    seen = set()
    for query in queries:
        try:
            url = "https://google.serper.dev/search"
            headers = {"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"}
            payload = {"q": query, "gl": "us", "hl": "en", "num": 10}
            resp = requests.post(url, headers=headers, json=payload, timeout=15)
            data = resp.json()
            for item in data.get("organic", []):
                title   = item.get("title", "").replace(" | Wellfound", "").replace(" - Wellfound", "").strip()
                desc    = item.get("snippet", "")
                url_job = item.get("link", "")
                posted  = item.get("date", "")
                if not any(x in url_job for x in ["wellfound.com/jobs/", "angel.co/jobs/"]):
                    continue
                if is_search_page(url_job, title):
                    continue
                if is_stale_or_closed(title, desc, posted):
                    continue
                if is_sketchy_job(title, desc):
                    continue
                if url_job in seen:
                    continue
                seen.add(url_job)
                company = item.get("source", "Wellfound")
                score, matched = score_job(title, desc)
                track = get_job_track(title, desc)
                if score > 0 and is_relevant_title(title) and is_us_location(title, desc) and not is_blocked_site(url_job) and not has_too_much_experience(title, desc):
                    jobs.append({
                        "source": "Wellfound", "title": title,
                        "company": company, "url": url_job,
                        "posted": posted, "description": desc[:500],
                        "score": score, "matched_keywords": matched, "track": track,
                    })
        except Exception as e:
            print(f"   [ERROR] Wellfound error: {e}")
    print(f"   [OK] Wellfound: {len(jobs)} relevant jobs found")
    return jobs

# ─── SOURCE 8: Google Custom Search ──────────────────────────
def search_google_jobs():
    print("[SEARCH] Searching Google Custom Search...")
    jobs = []
    if GOOGLE_API_KEY == "YOUR_GOOGLE_API_KEY":
        print("   [WARN]  Google Custom Search skipped  add your API key to the config")
        return jobs

    queries = [
        # Greenhouse - SOC / Security Analyst
        'site:boards.greenhouse.io "soc analyst" "remote"',
        'site:boards.greenhouse.io "security analyst" "entry level"',
        'site:boards.greenhouse.io "cybersecurity analyst" "remote"',
        # Lever - SOC / Security Analyst
        'site:jobs.lever.co "soc analyst" "remote"',
        'site:jobs.lever.co "security analyst" "entry level" "remote"',
        'site:jobs.lever.co "cybersecurity analyst" "remote"',
        # Workday - entry-level cybersecurity
        'site:myworkdayjobs.com "soc analyst" "remote"',
        'site:myworkdayjobs.com "security analyst" "entry level"',
        # Taleo / Oracle
        'site:taleo.net "soc analyst" "remote"',
        'site:taleo.net "cybersecurity analyst" "entry level"',
        # iCIMS
        'site:jobs.icims.com "soc analyst" "remote"',
        'site:jobs.icims.com "security analyst" "entry level"',
        # Jobvite
        'site:jobs.jobvite.com "soc analyst" "remote"',
        'site:jobs.jobvite.com "cybersecurity analyst" "remote"',
        # Ashby
        'site:jobs.ashbyhq.com "security analyst" "remote"',
        # Robert Half (via Google)
        'site:roberthalf.com "soc analyst" "remote"',
        'site:roberthalf.com "cybersecurity analyst" "remote"',
        # Incident Response / DFIR
        '"incident response analyst" "entry level" remote',
        '"dfir analyst" remote',
        # Vulnerability Management
        '"vulnerability analyst" "entry level" remote',
        '"vulnerability management analyst" remote',
        # MDR / Threat Detection
        '"mdr analyst" remote',
        '"threat analyst" "entry level" remote',
        # Internships / Junior roles
        '"security intern" remote',
        '"soc intern" remote',
        '"junior soc analyst" remote',
        # Dice (extra queries)
        'site:dice.com "soc analyst" "remote"',
        'site:dice.com "security analyst" "entry level" "remote"',
    ]
    seen = set()
    for query in queries:
        try:
            url = "https://www.googleapis.com/customsearch/v1"
            params = {
                "key": GOOGLE_API_KEY,
                "cx": GOOGLE_CX,
                "q": query,
                "num": 10,
                "dateRestrict": "d5",  # last 5 days
            }
            resp = requests.get(url, params=params, timeout=15)
            data = resp.json()
            for item in data.get("items", []):
                title   = item.get("title", "")
                desc    = item.get("snippet", "")
                url_job = item.get("link", "")
                if url_job in seen:
                    continue
                seen.add(url_job)
                score, matched = score_job(title, desc)
                track, level_ok = get_job_track(title, desc)
                if score > 0 and level_ok and is_relevant_title(title):
                    jobs.append({
                        "source": "Google Search",
                        "title": title,
                        "company": item.get("displayLink", "N/A"),
                        "url": url_job,
                        "posted": "",
                        "description": desc[:500],
                        "score": score,
                        "matched_keywords": matched,
                        "track": track,
                    })
        except Exception as e:
            print(f"   [ERROR] Google Search error: {e}")
    print(f"   [OK] Google Search: {len(jobs)} relevant jobs found")
    return jobs


# ─── COVER LETTER GENERATION ─────────────────────────────────
def generate_cover_letter(job):
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        prompt = f"""Write a compelling, personalized cover letter for Evan Richardson applying to this cybersecurity job.

JOB: {job['title']}
COMPANY: {job['company']}
TRACK: {job['track']}
MATCHED SKILLS: {', '.join(job['matched_keywords'][:8])}
DESCRIPTION: {job['description'][:400]}

EVAN'S BACKGROUND:
{EVAN_RESUME}

INSTRUCTIONS:
1. Address to the company's hiring team
2. Open with genuine enthusiasm for THIS specific role
3. Highlight his Security+ and AWS certifications
4. Mention his 4.0 GPA from ABET-accredited program
5. Reference his Public Trust clearance (from DHS/USCIS work)
6. Emphasize his hands-on CTF and Hack The Box experience
7. Connect his SIEM (Splunk/Sentinel) knowledge to the role
8. Keep it to 3 paragraphs, professional but confident
9. Close with availability for interview
10. Sign as Evan Richardson

Write ONLY the cover letter, no additional commentary."""

        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}]
        )
        return message.content[0].text
    except Exception as e:
        return f"[Cover letter generation failed: {e}]"

# ─── JOB ID + SUMMARY HELPERS ────────────────────────────────
def generate_job_id(job):
    import hashlib
    raw = f"{job.get('title','')}{job.get('company','')}{job.get('url','')}"
    return hashlib.md5(raw.encode()).hexdigest()[:10]

def load_overnight_summary():
    summary_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "evan_overnight_summary.json")
    try:
        if os.path.exists(summary_file):
            with open(summary_file, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return None

# ─── EMAIL ───────────────────────────────────────────────────
def send_email(jobs):
    try:
        msg = MIMEMultipart("alternative")
        today     = datetime.now().strftime("%B %d, %Y")
        today_key = datetime.now().strftime("%Y-%m-%d")
        msg["Subject"] = f"Evan's Job Search - {len(jobs)} Match{'es' if len(jobs)>1 else ''} for {today}"
        msg["From"]    = SMTP_EMAIL
        msg["To"]      = TARGET_EMAIL

        # ── Decision guide + Google Form button ─────────────────
        FORM_URL = "https://docs.google.com/forms/d/14_Jt5xRxZsjo3KgHM4V4wUuhGQ_soPQk8vFw8cVT9ds/viewform"
        decision_guide = f"""
<div style="background:#eaf3ff;border:1px solid #b5d4f4;border-radius:8px;padding:14px 18px;margin:16px 0 20px;">
  <p style="margin:0 0 10px;font-weight:bold;color:#1a3a5c;font-size:13px;">SUBMIT YOUR DECISIONS</p>
  <p style="margin:0 0 12px;">
    <a href="{FORM_URL}" style="background:#1a3a5c;color:#fff;padding:10px 20px;border-radius:4px;text-decoration:none;font-size:13px;font-weight:bold;">Submit Job Decisions</a>
  </p>
  <p style="margin:8px 0 6px;font-size:12px;color:#555;">Click the button above anytime before midnight to submit your decisions. You can submit one job at a time or all at once.</p>
  <p style="margin:6px 0 4px;font-size:12px;color:#888;"><strong>Decision options:</strong> Applied &nbsp;|&nbsp; Bad Link &nbsp;|&nbsp; Too Senior &nbsp;|&nbsp; Salary Too Low &nbsp;|&nbsp; Not Interested &nbsp;|&nbsp; Already Seen &nbsp;|&nbsp; Search Page &nbsp;|&nbsp; Not in United States &nbsp;|&nbsp; Other</p>
  <p style="margin:4px 0 0;font-size:11px;color:#aaa;"><em>Unanswered jobs are treated as neutral — no action taken.</em></p>
</div>"""

        # ── Overnight summary ────────────────────────────────────
        summary = load_overnight_summary()
        summary_html = ""
        if summary:
            auto_items   = "".join(f"<li>{item}</li>" for item in summary.get("auto_handled", []))
            manual_items = "".join(f"<li>{item}</li>" for item in summary.get("needs_review", []))
            auto_block   = f"<p style='margin:6px 0 2px;color:#0F6E56;font-weight:bold;font-size:12px;'>Auto-handled ✓</p><ul style='margin:0;padding-left:18px;font-size:12px;color:#333;'>{auto_items}</ul>" if auto_items else ""
            manual_block = f"<p style='margin:10px 0 2px;color:#c0392b;font-weight:bold;font-size:12px;'>Needs manual review ⚠</p><ul style='margin:0;padding-left:18px;font-size:12px;color:#333;'>{manual_items}</ul>" if manual_items else ""
            summary_html = f"""
<div style="background:#f9f9f9;border:1px solid #ddd;border-radius:8px;padding:14px 18px;margin:0 0 20px;">
  <p style="margin:0 0 8px;font-weight:bold;color:#1a3a5c;font-size:13px;">Overnight Update Report — {summary.get('date','')}</p>
  <p style="font-size:12px;color:#555;margin:0 0 6px;">
    Decisions received: <strong>{summary.get('decisions_received',0)}</strong> of <strong>{summary.get('jobs_sent',0)}</strong> &nbsp;|&nbsp;
    No response: <strong>{summary.get('no_response',0)}</strong> &nbsp;|&nbsp;
    Git commit: <strong>{summary.get('git_committed','—')}</strong>
  </p>
  {auto_block}{manual_block}
</div>"""

        html_parts = []
        html_parts.append(f"""
<html><body style="font-family:Arial,sans-serif;max-width:750px;margin:0 auto;padding:20px;color:#333;">
<h1 style="color:#1a3a5c;border-bottom:3px solid #1a3a5c;padding-bottom:10px;">
  Evan's Daily Cybersecurity Job Matches
</h1>
<p style="color:#555;font-size:15px;">Hi Evan, here are your top matches for <strong>{today}</strong>.</p>
{summary_html}
{decision_guide}
""")

        track_colors = {
            "SOC Analyst":              "#1a3a5c",
            "Cybersecurity Analyst":    "#2d6a4f",
            "MDR Analyst":              "#6b2d5e",
            "Vulnerability Management": "#c77d0a",
            "Incident Response":        "#c0392b",
            "Junior Pen Tester":        "#1a6b8a",
        }

        if not jobs:
            html_parts.append("""
<div style="background:#fff8e1;border:1px solid #ffe082;border-radius:8px;padding:16px;margin:16px 0;">
  <p style="margin:0;color:#f57f17;font-weight:bold;">No matching jobs found today.</p>
  <p style="margin:8px 0 0;color:#555;">The script ran successfully but found no new cybersecurity jobs matching Evan's criteria. Check back tomorrow!</p>
</div>""")

        for i, job in enumerate(jobs, 1):
            job_id  = generate_job_id(job)
            color   = track_colors.get(job.get("track", ""), "#1a3a5c")
            cover   = job.get("cover_letter", "")
            url     = job.get("url", "")

            is_workday = "myworkdayjobs.com" in url.lower() or "workday.com" in url.lower()
            workday_warning = """
  <div style="background:#fff3cd;border:1px solid #ffc107;border-radius:5px;padding:8px 12px;margin:8px 0;font-size:13px;color:#856404;">
    <strong>Heads up:</strong> This link goes to Workday — these sometimes expire quickly. If the page shows "doesn't exist", the role has been filled. Try searching the company name directly.
  </div>""" if is_workday else ""

            html_parts.append(f"""
<div style="border:1px solid #ddd;border-radius:8px;padding:20px;margin:20px 0;border-left:5px solid {color};">
  <h2 style="margin:0 0 8px;color:{color};">#{i} - {job['title']}</h2>
  <span style="background:{color};color:white;padding:3px 10px;border-radius:12px;font-size:12px;">{job.get('track','')}</span>
  <p style="margin:10px 0 5px;color:#666;font-size:14px;">
    <strong>Company:</strong> {job['company']} &nbsp;|&nbsp;
    <strong>Source:</strong> {job['source']} &nbsp;|&nbsp;
    <strong>Score:</strong> {job['score']} pts
  </p>
  <p style="margin:0 0 5px;color:#666;font-size:14px;">
    <strong>Posted:</strong> <span style="color:#e74c3c;">{job['posted']}</span> &nbsp;|&nbsp;
    <strong>Track:</strong> {job.get('track','')}
  </p>
  <p style="margin:0 0 10px;color:#666;font-size:14px;">
    <strong>Matched Skills:</strong> {', '.join(job['matched_keywords'][:6])}
  </p>
  {workday_warning}
  <a href="{url}" style="background:{color};color:white;padding:10px 20px;border-radius:5px;text-decoration:none;font-weight:bold;font-size:13px;">View and Apply</a>

  <div style="background:#f7f9fc;border:1px solid #dde3ef;border-radius:6px;padding:12px;margin-top:14px;">
    <p style="margin:0 0 6px;font-size:12px;color:#555;"><strong>Job #{i} decision</strong> &nbsp;·&nbsp; <span style="font-family:monospace;font-size:11px;color:#888;">ID: {job_id}</span></p>
    <p style="margin:0;font-size:12px;color:#444;">Reply to this email: &nbsp;<strong>Job {i}: [code]</strong></p>
    <p style="margin:4px 0 0;font-size:11px;color:#888;">1=Applied &nbsp; 2=Bad link &nbsp; 3=Too senior &nbsp; 4=Salary too low &nbsp; 5=Not interested &nbsp; 6=Already seen &nbsp; 7=Search page &nbsp; 8=Other (add reason)</p>
  </div>

  <br>
  <strong>Cover Letter:</strong>
  <div style="background:#f8f9fa;border-left:3px solid {color};padding:15px;margin-top:10px;font-size:14px;line-height:1.6;">
    {cover.replace(chr(10), '<br>')}
  </div>
</div>""")

        html_parts.append("""
<p style="color:#888;font-size:12px;margin-top:30px;border-top:1px solid #eee;padding-top:15px;">
  Powered by Evan's Automated Cybersecurity Job Search System &nbsp;·&nbsp; Reply with decisions anytime before midnight.
</p>
</body></html>""")

        msg.attach(MIMEText("".join(html_parts), "html"))

        # Save today's batch for overnight script
        batch_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "evan_today_jobs.json")
        try:
            batch = {
                "date": today_key,
                "jobs": [
                    {
                        "job_id": generate_job_id(j),
                        "number": idx,
                        "title": j.get("title",""),
                        "company": j.get("company",""),
                        "track": j.get("track",""),
                        "score": j.get("score",0),
                        "url": j.get("url",""),
                        "matched_keywords": j.get("matched_keywords",[]),
                        "source": j.get("source",""),
                    }
                    for idx, j in enumerate(jobs, 1)
                ]
            }
            with open(batch_file, "w") as f:
                json.dump(batch, f, indent=2)
            print(f"   [OK] Saved today's job batch to evan_today_jobs.json")
        except Exception as e:
            print(f"   [WARN] Could not save evan_today_jobs.json: {e}")

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(SMTP_EMAIL, SMTP_PASSWORD)
            server.sendmail(SMTP_EMAIL, TARGET_EMAIL, msg.as_string())
        print(f"\n   [EMAIL] Sent {len(jobs)} jobs to {TARGET_EMAIL}")
    except Exception as e:
        print(f"\n   [ERROR] Email failed: {e}")


def main():
    print("=" * 55)
    print("  Evan Richardson - Cybersecurity Job Search")
    print("  Targets: SOC, DFIR, Vuln Mgmt, MDR, Pen Test")
    print("  Markets: Remote + KC Metro")
    print("=" * 55)

    all_jobs = []
    all_jobs += search_remoteok()
    all_jobs += search_serper()

    all_jobs += search_usajobs()
    all_jobs += search_greenhouse()
    all_jobs += search_lever()
    all_jobs += search_google_jobs()
    all_jobs += search_dice()
    all_jobs += search_wellfound()

    print(f"\n[STATS] Raw jobs found before filtering: {len(all_jobs)}")
    # Sort by score
    all_jobs.sort(key=lambda x: x["score"], reverse=True)

    # Min score threshold
    MIN_SCORE = 20  # Lowered since description hits now score at 40%
    filtered_low = [j for j in all_jobs if j["score"] < MIN_SCORE]
    for j in filtered_low:
        if DEBUG_MODE:
            print(f"   [DEBUG] FILTERED-minscore: {j['title'][:50]} [{j['score']}pts]")
    all_jobs = [j for j in all_jobs if j["score"] >= MIN_SCORE]
    print(f"[OK] {len(filtered_low)} jobs below min score {MIN_SCORE} filtered out")

    # Deduplicate by title and URL
    seen_titles = set()
    seen_urls = set()
    deduped = []
    for job in all_jobs:
        raw_title = job.get("title", "")
        title_key = clean_title(raw_title).lower().strip()[:50]
        url_key = job.get("url", "").strip()
        if title_key not in seen_titles and url_key not in seen_urls:
            seen_titles.add(title_key)
            seen_urls.add(url_key)
            deduped.append(job)
    all_jobs = deduped

    # Remove previously seen jobs
    try:
        seen = load_seen_jobs()
    except Exception as e:
        print(f"[WARN] Could not load seen jobs ({e}), treating all as new")
        seen = set()

    new_jobs = [j for j in all_jobs if j.get("url", "") not in seen]
    dupes = len(all_jobs) - len(new_jobs)
    if dupes > 0:
        print(f"[OK] Removed {dupes} duplicate jobs already sent previously")

    top_jobs = new_jobs[:MAX_JOBS_EMAIL]

    print(f"\n{'='*55}")
    print(f"[STATS] Total relevant jobs found: {len(new_jobs)}")
    print(f"[STATS] Sending top {len(top_jobs)} jobs to {TARGET_EMAIL}")
    print(f"{'='*55}\n")

    # Generate cover letters (only if enabled and API credits available)
    if GENERATE_COVER_LETTERS:
        print(f"[STATS] Generating cover letters for {len(top_jobs)} jobs...")
        for i, job in enumerate(top_jobs, 1):
            posted_short = str(job.get('posted', ''))[:10] or 'unknown'
            print(f"  [{i:02d}] Score:{job['score']:3d} | {job['source'][:12]} | {posted_short} | {job['title'][:45]}")
            job["cover_letter"] = generate_cover_letter(job)
    else:
        print(f"[INFO] Cover letters disabled — set GENERATE_COVER_LETTERS=True to enable")
        for i, job in enumerate(top_jobs, 1):
            posted_short = str(job.get('posted', ''))[:10] or 'unknown'
            print(f"  [{i:02d}] Score:{job['score']:3d} | {job['source'][:12]} | {posted_short} | {job['title'][:45]}")
            job["cover_letter"] = ""

    # Save seen jobs
    try:
        save_seen_jobs([j.get("url", "") for j in top_jobs])
        print(f"\n[OK] Saved {len(top_jobs)} job URLs to {SEEN_JOBS_FILE}")
    except Exception as e:
        print(f"[WARN] Could not save seen jobs: {e}")

    # Send email
    # Send email always so we know the script ran
    send_email(top_jobs)
    if not top_jobs:
        print("\n[INFO] No new jobs found today - check back tomorrow!")

    print(f"\n[DONE] Evan's job search completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        print(f"\n[FATAL] Unhandled exception in main:")
        print(traceback.format_exc())
