"""
GOOGLE SHEETS EXPORT
======================
Appends a submitted scenario as one row in a Google Sheet, using a
Google Cloud service account (no interactive login — the right fit for
a headless deployed app). Credentials come from Streamlit secrets
(st.secrets["gcp_service_account"]), never hardcoded.

One-time setup (see README for the full click-by-click walkthrough):
  1. Create a Google Cloud project, enable the Google Sheets API and
     Google Drive API.
  2. Create a service account, download its JSON key.
  3. Paste the JSON key's fields into this app's Secrets as a
     [gcp_service_account] block.
  4. Create (or pick) a Google Sheet in Drive, and SHARE it with the
     service account's client_email as an Editor — the sheet is not
     writable otherwise, this step is easy to miss.
  5. Paste that sheet's URL (or ID) into the app's "Google Sheet URL"
     field when saving.
"""

import datetime

SHEET_HEADERS = [
    "Submitted At", "Partner Email", "RM Email",
    "Starting Clients", "Starting AUM", "New Clients / Month", "SIP / Client / Month",
    "SIP Step-up %", "Annual Lumpsum / Client", "Lumpsum Step-up %", "Annual Redemption %",
    "Active Years", "Trail Rate %", "Market CAGR %",
    "Life Insurance", "Health Insurance", "PMS", "Demat & Broking",
    "Highlight Year", "Highlight Year Income", "Final Year Income",
]


def _get_client(secrets):
    try:
        import gspread
    except ImportError:
        return None, "The 'gspread' package isn't installed — add `gspread` and `google-auth` to requirements.txt."
    try:
        info = dict(secrets["gcp_service_account"])
    except Exception:
        return None, ("Google Sheets isn't configured yet. Add a [gcp_service_account] block to this "
                       "app's Secrets — see README for the exact format.")
    try:
        client = gspread.service_account_from_dict(info)
        return client, None
    except Exception as e:
        return None, f"Couldn't authenticate with Google: {e}"


def _open_sheet(client, sheet_url_or_id: str):
    import gspread
    try:
        if sheet_url_or_id.strip().startswith("http"):
            sh = client.open_by_url(sheet_url_or_id.strip())
        else:
            sh = client.open_by_key(sheet_url_or_id.strip())
        return sh.sheet1, None
    except gspread.exceptions.SpreadsheetNotFound:
        return None, ("Sheet not found. Check the URL/ID, and make sure the sheet is shared with the "
                       "service account's client_email as an Editor.")
    except gspread.exceptions.APIError as e:
        return None, f"Google Sheets API error: {e}"
    except Exception as e:
        return None, f"Couldn't open the sheet: {e}"


def append_submission(secrets, sheet_url_or_id: str, inputs, projection, highlight_year: int,
                       partner_email: str, rm_email: str) -> tuple:
    """Returns (success: bool, message: str)."""
    if not sheet_url_or_id:
        return False, "Enter a Google Sheet URL or ID first."

    client, err = _get_client(secrets)
    if client is None:
        return False, err

    ws, err = _open_sheet(client, sheet_url_or_id)
    if ws is None:
        return False, err

    try:
        existing_header = ws.row_values(1)
        if not existing_header:
            ws.append_row(SHEET_HEADERS)
    except Exception:
        pass  # non-fatal — proceed to append the data row regardless

    hy = projection[highlight_year - 1]
    y_last = projection[-1]
    row = [
        datetime.datetime.now().isoformat(timespec="seconds"),
        partner_email or "", rm_email or "",
        inputs.starting_clients, round(inputs.starting_aum),
        inputs.new_clients_per_month, inputs.sip_per_client_month,
        inputs.sip_stepup_pct, inputs.annual_lumpsum_per_client, inputs.lumpsum_stepup_pct,
        inputs.annual_redemption_pct, inputs.active_years, inputs.trail_rate_pct, inputs.market_cagr_pct,
        "On" if inputs.life.enabled else "Off", "On" if inputs.health.enabled else "Off",
        "On" if inputs.pms.enabled else "Off", "On" if inputs.demat.enabled else "Off",
        highlight_year, round(hy["total_income"]), round(y_last["total_income"]),
    ]
    try:
        ws.append_row(row)
        return True, "Saved to the Google Sheet."
    except Exception as e:
        return False, f"Couldn't write to the sheet: {e}"
