"""
weekly_review_evan.py — Evan Richardson Job Search
===============================================
Runs every Monday at 10:00 AM via Windows Task Scheduler.

- Reads evan_needs_review.json
- Sends a formatted HTML email digest grouped by category
- Marks all pending items as "reviewed" in evan_needs_review.json after sending (data preserved)
- Commits the updated file to GitHub
"""

import os
import json
import smtplib
import subprocess
from datetime import datetime, date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from dotenv import load_dotenv

# ─── SETUP ───────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(SCRIPT_DIR, ".env"))

SMTP_EMAIL        = os.environ.get("SMTP_EMAIL", "")
SMTP_PASSWORD     = os.environ.get("SMTP_PASSWORD", "")
TARGET_EMAIL      = os.environ.get("TARGET_EMAIL", "")
REVIEW_EMAIL      = os.environ.get("REVIEW_EMAIL", TARGET_EMAIL)  # Weekly review goes to Hans, not Evan
NEEDS_REVIEW_FILE = os.path.join(SCRIPT_DIR, "evan_needs_review.json")
TODAY             = date.today().isoformat()

# Category labels and colors for email display
CATEGORY_CONFIG = {
    "other":        {"label": "Other / Unclassified",     "color": "#6c5ce7"},
    "bad_link":     {"label": "Dead Links / Bad URLs",     "color": "#c0392b"},
    "clearance":    {"label": "Clearance Required",        "color": "#d35400"},
    "onsite":       {"label": "Onsite / Not Remote",       "color": "#e17055"},
    "not_in_us":    {"label": "Not in United States",      "color": "#0984e3"},
    "jmeter_only":  {"label": "JMeter-Only (No LoadRunner)","color": "#00b894"},
    "too_senior":   {"label": "Too Senior",                "color": "#fdcb6e"},
    "salary":       {"label": "Salary Too Low",            "color": "#a29bfe"},
    "unknown":      {"label": "Uncategorized",             "color": "#636e72"},
}

print(f"\n{'='*55}")
print(f"  Evan Weekly Review — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(f"{'='*55}\n")

def load_needs_review():
    """Load evan_needs_review.json and return pending items."""
    try:
        if os.path.exists(NEEDS_REVIEW_FILE):
            with open(NEEDS_REVIEW_FILE, "r") as f:
                data = json.load(f)
            items = [i for i in data.get("items", []) if i.get("status") == "pending"]
            return items
    except Exception as e:
        print(f"[WARN] Could not load evan_needs_review.json: {e}")
    return []

def group_by_category(items):
    """Group items by their category."""
    groups = {}
    for item in items:
        cat = item.get("category", "unknown")
        if cat not in groups:
            groups[cat] = []
        groups[cat].append(item)
    return groups

def build_email(items, groups):
    """Build the weekly review HTML email."""
    week_start = TODAY
    total = len(items)

    # Count by date range
    dates = sorted(set(i.get("date","") for i in items))
    date_range = f"{dates[0]} to {dates[-1]}" if len(dates) > 1 else dates[0] if dates else TODAY

    html = f"""<html><body style="font-family:Arial,sans-serif;max-width:800px;margin:auto;color:#333;">
<div style="background:#1F3864;color:white;padding:20px 24px;border-radius:8px 8px 0 0;margin-bottom:0;">
  <h2 style="margin:0;font-size:20px;">Evan Weekly Job Search Review</h2>
  <p style="margin:6px 0 0;font-size:13px;opacity:0.85;">Week ending {TODAY} &nbsp;|&nbsp; {total} item(s) need your attention</p>
</div>

<div style="background:#f0f4ff;border:1px solid #c5d0e8;border-top:none;padding:14px 24px;margin-bottom:20px;border-radius:0 0 8px 8px;">
  <p style="margin:0;font-size:13px;color:#444;">
    These items were flagged during nightly processing and could not be auto-resolved.
    Review each one and bring patterns to Claude for code fixes.
    <strong>After sending, these items will be marked as reviewed (data is preserved).</strong>
  </p>
</div>"""

    if total == 0:
        html += """
<div style="background:#d4edda;border:1px solid #c3e6cb;border-radius:8px;padding:20px;text-align:center;">
  <p style="margin:0;color:#155724;font-size:16px;font-weight:bold;">Nothing to review this week!</p>
  <p style="margin:8px 0 0;color:#155724;font-size:13px;">All job decisions were handled automatically. Great week!</p>
</div>"""
    else:
        # Summary table
        html += """<table style="width:100%;border-collapse:collapse;margin-bottom:24px;">
  <tr style="background:#f8f9fa;">
    <th style="text-align:left;padding:8px 12px;font-size:12px;color:#555;border-bottom:2px solid #dee2e6;">Category</th>
    <th style="text-align:right;padding:8px 12px;font-size:12px;color:#555;border-bottom:2px solid #dee2e6;">Count</th>
  </tr>"""
        for cat, cat_items in sorted(groups.items(), key=lambda x: -len(x[1])):
            cfg = CATEGORY_CONFIG.get(cat, CATEGORY_CONFIG["unknown"])
            html += f"""
  <tr>
    <td style="padding:8px 12px;font-size:13px;border-bottom:1px solid #f0f0f0;">
      <span style="display:inline-block;width:10px;height:10px;background:{cfg['color']};border-radius:50%;margin-right:6px;"></span>
      {cfg['label']}
    </td>
    <td style="text-align:right;padding:8px 12px;font-size:13px;font-weight:bold;border-bottom:1px solid #f0f0f0;">{len(cat_items)}</td>
  </tr>"""
        html += "</table>"

        # Detail sections by category
        for cat, cat_items in sorted(groups.items(), key=lambda x: -len(x[1])):
            cfg = CATEGORY_CONFIG.get(cat, CATEGORY_CONFIG["unknown"])
            html += f"""
<div style="margin-bottom:24px;">
  <h3 style="color:{cfg['color']};border-bottom:2px solid {cfg['color']};padding-bottom:6px;font-size:15px;margin-bottom:12px;">
    {cfg['label']} ({len(cat_items)})
  </h3>"""
            for item in cat_items:
                title   = item.get("title", "Unknown Job")
                reason  = item.get("reason", "No reason provided")
                track   = item.get("track", "")
                url     = item.get("url", "")
                dt      = item.get("date", "")
                job_id  = item.get("job_id", "")

                html += f"""
  <div style="background:#f9f9f9;border:1px solid #e0e0e0;border-left:4px solid {cfg['color']};border-radius:4px;padding:12px 14px;margin-bottom:10px;">
    <p style="margin:0 0 4px;font-weight:bold;font-size:13px;color:#222;">{title}</p>
    <p style="margin:0 0 4px;font-size:12px;color:#666;">
      Track: {track} &nbsp;|&nbsp; Date: {dt} &nbsp;|&nbsp;
      <span style="font-family:monospace;font-size:11px;">ID: {job_id}</span>
    </p>
    <p style="margin:0 0 6px;font-size:12px;color:#444;"><strong>Reason:</strong> {reason}</p>
    {f'<a href="{url}" style="font-size:11px;color:#1F3864;">View Job →</a>' if url else ''}
  </div>"""
            html += "</div>"

    # ── Data retention note ───────────────────────────────────
    html += f"""
<div style="background:#e8f5e9;border:1px solid #a5d6a7;border-radius:8px;padding:12px 16px;margin-top:8px;">
  <p style="margin:0 0 4px;font-weight:bold;color:#1b5e20;font-size:12px;">Data Retention Note</p>
  <p style="margin:0;font-size:11px;color:#2e7d32;">
    <strong>evan_needs_review.json</strong> — items marked as reviewed after this email (data preserved) ✓<br>
    <strong>evan_job_decisions.json</strong> — NEVER cleared — permanent training dataset for future K-Means analysis<br>
    <strong>K-Means milestone:</strong> After 4-6 weeks of decisions (~200+ entries), run analyze_decisions.py to discover hidden patterns
  </p>
</div>

<hr style="margin:16px 0;border:none;border-top:1px solid #eee;"/>
<p style="font-size:11px;color:#aaa;text-align:center;">
  Evan Richardson Weekly Job Search Review &nbsp;·&nbsp; Generated {datetime.now().strftime('%Y-%m-%d %H:%M')} &nbsp;·&nbsp; evan_needs_review.json items marked as reviewed after send
</p>
</body></html>"""

    return html

def send_weekly_email(html, total):
    """Send Evan's weekly review email with evan_needs_review.json attached."""
    from email.mime.base import MIMEBase
    from email import encoders

    subject = f"Evan Weekly Job Search Review — {total} Item(s) to Review — {TODAY}"
    if total == 0:
        subject = f"Evan Weekly Job Search Review — Nothing to Review! — {TODAY}"
    try:
        msg = MIMEMultipart("mixed")
        msg["Subject"] = subject
        msg["From"]    = f"Job Search Weekly <{SMTP_EMAIL}>"
        msg["To"]      = REVIEW_EMAIL

        # HTML body
        msg.attach(MIMEText(html, "html"))

        # Attach evan_needs_review.json if it exists
        if os.path.exists(NEEDS_REVIEW_FILE):
            with open(NEEDS_REVIEW_FILE, "rb") as f:
                attachment = MIMEBase("application", "octet-stream")
                attachment.set_payload(f.read())
            encoders.encode_base64(attachment)
            attachment.add_header(
                "Content-Disposition",
                f"attachment; filename=evan_needs_review_{TODAY}.json"
            )
            msg.attach(attachment)
            print(f"   [OK] Attached evan_needs_review_{TODAY}.json to email")

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(SMTP_EMAIL, SMTP_PASSWORD)
            server.sendmail(SMTP_EMAIL, REVIEW_EMAIL, msg.as_string())
        print(f"[OK] Evan weekly review email sent to {REVIEW_EMAIL}")
        return True
    except Exception as e:
        print(f"[ERROR] Email failed: {e}")
        return False

def clear_needs_review():
    """Mark all pending items as reviewed and save."""
    try:
        if not os.path.exists(NEEDS_REVIEW_FILE):
            return
        with open(NEEDS_REVIEW_FILE, "r") as f:
            data = json.load(f)

        cleared = 0
        for item in data.get("items", []):
            if item.get("status") == "pending":
                item["status"] = "reviewed"
                item["reviewed_date"] = TODAY
                cleared += 1

        data["last_cleared"] = TODAY
        data["pending_count"] = 0
        with open(NEEDS_REVIEW_FILE, "w") as f:
            json.dump(data, f, indent=2)
        print(f"[OK] Marked {cleared} pending item(s) as reviewed in evan_needs_review.json")
    except Exception as e:
        print(f"[WARN] Could not update evan_needs_review.json: {e}")

def git_commit_push():
    """Commit and push the updated evan_needs_review.json."""
    print("[GIT] Committing weekly review update...")
    try:
        subprocess.run(["git", "add", "."], cwd=SCRIPT_DIR, check=True)
        commit_msg = f"Evan weekly review sent — items marked reviewed — {TODAY}"
        result = subprocess.run(
            ["git", "commit", "-m", commit_msg],
            cwd=SCRIPT_DIR, capture_output=True, text=True
        )
        if "nothing to commit" in result.stdout:
            print("   [INFO] Nothing to commit")
            return
        subprocess.run(["git", "push"], cwd=SCRIPT_DIR, check=True)
        print(f"   [OK] Pushed: '{commit_msg}'")
    except subprocess.CalledProcessError as e:
        print(f"   [ERROR] Git failed: {e}")

def main():
    # Load pending items
    items = load_needs_review()
    print(f"[OK] Found {len(items)} pending item(s) in evan_needs_review.json")

    # Group by category
    groups = group_by_category(items)

    # Build and send email
    html = build_email(items, groups)
    sent = send_weekly_email(html, len(items))

    if sent:
        # Mark pending items as reviewed after successful send
        clear_needs_review()
        git_commit_push()

    print(f"\n[DONE] Weekly review completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        print(f"\n[FATAL] {traceback.format_exc()}")
