"""
GOOGLE SHEETS — VIA APPS SCRIPT WEBHOOK
==========================================
A simpler alternative to google_sheets.py's service-account route: this
posts a submission straight to a small Google Apps Script "Web App"
that lives INSIDE your Google Sheet itself.

Why this instead of the service account: Apps Script is a built-in
feature of every Google Sheet — no Google Cloud project, no API
enablement, no service account, no IT/admin approval typically needed.
You (or anyone with edit access to the sheet) can deploy it in about 3
minutes from Extensions > Apps Script inside the sheet. See README for
the exact script to paste and the deployment steps.

Configuration (one-time, org-wide — see README):
    [sheet_webhook]
    url = "https://script.google.com/macros/s/AKfycb.../exec"
    secret = "any password you make up"

Every RM/user of the app then just clicks "Save to Google Sheet" with
no per-user setup — the webhook URL and secret are configured once,
centrally, by whoever set up the app (not exposed to end users).
"""

import datetime
import json
import urllib.request
import urllib.error

ROW_KEYS = [
    "submitted_at", "partner_email", "rm_email",
    "starting_clients", "starting_aum", "new_clients_per_month", "sip_per_client_month",
    "sip_stepup_pct", "annual_lumpsum_per_client", "lumpsum_stepup_pct", "annual_redemption_pct",
    "active_years", "trail_rate_pct", "market_cagr_pct",
    "life_insurance", "health_insurance", "pms", "demat_broking",
    "highlight_year", "highlight_year_income", "final_year_income",
]


def get_webhook_config(secrets):
    try:
        cfg = dict(secrets["sheet_webhook"])
    except Exception:
        return None
    if "url" not in cfg:
        return None
    return cfg


def append_submission(secrets, inputs, projection, highlight_year: int,
                       partner_email: str, rm_email: str) -> tuple:
    """Returns (success: bool, message: str)."""
    cfg = get_webhook_config(secrets)
    if cfg is None:
        return False, ("Google Sheets isn't configured yet. Add a [sheet_webhook] block (url + secret) "
                        "to this app's Secrets — see README for the Apps Script setup.")

    hy = projection[highlight_year - 1]
    y_last = projection[-1]
    row = {
        "submitted_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "partner_email": partner_email or "", "rm_email": rm_email or "",
        "starting_clients": inputs.starting_clients, "starting_aum": round(inputs.starting_aum),
        "new_clients_per_month": inputs.new_clients_per_month, "sip_per_client_month": inputs.sip_per_client_month,
        "sip_stepup_pct": inputs.sip_stepup_pct, "annual_lumpsum_per_client": inputs.annual_lumpsum_per_client,
        "lumpsum_stepup_pct": inputs.lumpsum_stepup_pct, "annual_redemption_pct": inputs.annual_redemption_pct,
        "active_years": inputs.active_years, "trail_rate_pct": inputs.trail_rate_pct,
        "market_cagr_pct": inputs.market_cagr_pct,
        "life_insurance": "On" if inputs.life.enabled else "Off",
        "health_insurance": "On" if inputs.health.enabled else "Off",
        "pms": "On" if inputs.pms.enabled else "Off",
        "demat_broking": "On" if inputs.demat.enabled else "Off",
        "highlight_year": highlight_year, "highlight_year_income": round(hy["total_income"]),
        "final_year_income": round(y_last["total_income"]),
    }
    payload = {**row, "secret": cfg.get("secret", "")}

    try:
        req = urllib.request.Request(
            cfg["url"],
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = resp.read().decode("utf-8")
        try:
            parsed = json.loads(body)
        except Exception:
            parsed = {}
        if parsed.get("status") == "success":
            return True, "Saved to the Google Sheet."
        if parsed.get("status") == "error":
            return False, f"The sheet rejected the write: {parsed.get('message', 'unknown error')}"
        return True, "Saved (unexpected response format, but no error reported)."
    except urllib.error.HTTPError as e:
        return False, f"Couldn't reach the Apps Script webhook (HTTP {e.code}). Check the URL in Secrets."
    except Exception as e:
        return False, f"Couldn't save to the sheet: {e}"
