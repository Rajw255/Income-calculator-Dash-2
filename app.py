"""
Partner Income Calculator
===========================
Run locally:   streamlit run app.py
Deploy free:   push this folder to GitHub, then deploy on
               https://share.streamlit.io (Streamlit Community Cloud)
"""

import hashlib

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from formatting import format_inr, format_count, format_pct
from income_projection import ProjectionInputs, CrossSellAssumption, simulate, milestone_years
import income_report_export as export
import email_sender
import sheets_webhook

st.set_page_config(page_title="Partner Income Calculator", layout="wide")

PRIMARY = "#0B3D66"
ACCENT = "#C89B3C"

st.markdown(f"""
<style>.block-container {{
    padding-top: 3rem !important;
}}

h1, h2, h3 {{
    color: {PRIMARY};
}}

h1 {{
    font-size: 28px !important;
}}

/* Reduce vertical gap between Streamlit elements */
[data-testid="stVerticalBlock"] {{
    gap: 0.3rem;
}}

/* Submit button color */
div.stButton > button[kind="primary"] {{
    background-color: #198754 !important;
    color: white;
    border: none;
}}

.insight-card {{
    background: White;
    border-left: 4px solid {ACCENT};
    border-radius: 6px;
    padding: 10px 14px;
    margin-bottom: 8px;
    box-shadow: 0 1px 2px rgba(0,0,0,0.04);
}}

.submitted-banner {{
    background: #e8f5e9;
    border: 1px solid #a5d6a7;
    border-radius: 8px;
    padding: 12px 16px;
    margin: 10px 0;
}}

</style>
""", unsafe_allow_html=True)

st.title("Partner Income Calculator")
st.caption("Adjust assumptions and watch the projection update live. When you've landed on a scenario you like, "
           "click **Submit** to lock it in, then download, email, or save it.")


def _inputs_signature(p: ProjectionInputs) -> str:
    """A stable fingerprint of every input, used to detect whether the
    submitted scenario is still current."""
    parts = [
        p.starting_clients, p.starting_aum, p.new_clients_per_month, p.sip_per_client_month,
        p.sip_stepup_pct, p.annual_lumpsum_per_client, p.lumpsum_stepup_pct, p.annual_redemption_pct,
        p.active_years, p.trail_rate_pct, p.market_cagr_pct,
        p.life.enabled, p.health.enabled, p.pms.enabled, p.demat.enabled,
    ]
    return hashlib.md5(str(parts).encode()).hexdigest()


if st.button("↺ Reset to defaults"):
    for k in list(st.session_state.keys()):
        if k.startswith("ic_"):
            del st.session_state[k]
    st.session_state.pop("submitted", None)
    st.rerun()

col_inputs, col_results = st.columns([1, 2.6])

with col_inputs:
    st.markdown("**Partner & RM Details**")
    partner_email = st.text_input("Partner Email", key="ic_partner_email", placeholder="partner@example.com")
    rm_email = st.text_input("RM Email", key="ic_rm_email", placeholder="rm@wealthy.in")

    st.markdown("**Your Book**")
    starting_clients = st.number_input("Starting Clients", min_value=0, value=0, step=1, key="ic_start_clients")
    starting_aum_cr = st.number_input("Starting AUM (₹ Cr)", min_value=0.0, value=0.0, step=0.5, key="ic_start_aum")
    new_clients_pm = st.number_input("New Clients / Month", min_value=0, value=0, step=1, key="ic_new_clients")
    sip_per_client = st.number_input("SIP / Client / Month (₹)", min_value=0, value=10, step=500, key="ic_sip_amt")
    sip_stepup = st.number_input("SIP Step-up % p.a.", min_value=0.0, value=1.0, step=0.5, key="ic_sip_stepup")
    lumpsum_amt = st.number_input("Annual Lumpsum / Client (₹)", min_value=0, value=1000, step=1000, key="ic_lumpsum")
    lumpsum_stepup = st.number_input("Lumpsum Step-up % p.a.", min_value=0.0, value=1.0, step=0.5, key="ic_lumpsum_stepup")
    redemption_pct = st.number_input("Annual Redemption %", min_value=0.0, value=0.0, step=0.5, key="ic_redemption")
    active_years = st.number_input("Active Years (effort)", min_value=1, max_value=40, value=25, step=1, key="ic_years")

    st.markdown("**Assumptions**")
    trail_rate = st.number_input("Trail Rate % p.a.", min_value=0.0, value=0.7, step=0.1, key="ic_trail")
    market_cagr = st.number_input("Market CAGR % p.a.", min_value=0.0, value=12.0, step=0.5, key="ic_cagr")

    st.markdown("**Cross-Sell Income** *(toggle to add)*")
    life_on = st.toggle("Life Insurance", key="ic_life_on")
    health_on = st.toggle("Health Insurance ", key="ic_health_on")
    pms_on = st.toggle("PMS ", key="ic_pms_on")
    demat_on = st.toggle("Demat & Broking ", key="ic_demat_on")

    #st.caption("Cross-sell commission rates above are illustrative placeholders — "
    #           "confirm your real payout structure with Finance before relying on these numbers.")

inputs = ProjectionInputs(
    starting_clients=starting_clients,
    starting_aum=starting_aum_cr * 1_00_00_000,
    new_clients_per_month=new_clients_pm,
    sip_per_client_month=sip_per_client,
    sip_stepup_pct=sip_stepup,
    annual_lumpsum_per_client=lumpsum_amt,
    lumpsum_stepup_pct=lumpsum_stepup,
    annual_redemption_pct=redemption_pct,
    active_years=int(active_years),
    trail_rate_pct=trail_rate,
    market_cagr_pct=market_cagr,
    life=CrossSellAssumption(enabled=life_on, commission_pct=40, rate=10),
    health=CrossSellAssumption(enabled=health_on, commission_pct=30, rate=15),
    pms=CrossSellAssumption(enabled=pms_on, commission_pct=1, rate=5),
    demat=CrossSellAssumption(enabled=demat_on, rate=210),
)
projection = simulate(inputs)
milestones = milestone_years(int(active_years))
current_signature = _inputs_signature(inputs)

with col_results:
    highlight_year = st.selectbox("Highlight year", milestones, index=min(3, len(milestones) - 1))
    hy = projection[highlight_year - 1]
    y5 = projection[min(5, len(projection)) - 1]
    y_last = projection[-1]

   #st.markdown(f"**{active_years}-Year Income Projections** — {len(milestones)} milestones")
    table_rows = []
    for y in milestones:
        r = projection[y - 1]
        table_rows.append({
            "Year": y, "Clients": format_count(r["clients"]),
            "SIP Contrib.": format_inr(r["sip_contrib"]),
            "Step-up Inflows": format_inr(r["stepup_inflow"]) if r["stepup_inflow"] else "—",
            "Lumpsum / Yr": format_inr(r["lumpsum"]),
            "Mkt. Gains": format_inr(r["mkt_gains"]),
            "Total AUM": format_inr(r["total_aum"]),
            "SIP Book /Mo": format_inr(r["sip_book_mo"]),
            "Trail / Yr": format_inr(r["trail_yr"]),
            "Cross-sell / Yr": format_inr(r["cross_sell_total"]) if r["cross_sell_total"] else "—",
            "Demat / Yr": format_inr(r["demat_yr"]) if r["demat_yr"] else "—",
            "Total Income": format_inr(r["total_income"]),
            "Uplift": format_pct(r["uplift_pct"]) if r["uplift_pct"] is not None else "—",
        })
    st.dataframe(pd.DataFrame(table_rows), use_container_width=True, hide_index=True)
    #st.caption(f"Illustrative projections. Trail: {trail_rate}% p.a. · Market CAGR: {market_cagr}% · "
             #  f"Cross-sell: Life 40% · Health 30% · PMS 1% (of AUM) · Demat ₹210/active client/mo.")

    # -----------------------------------------------------------------
    # Submit → lock in this scenario → download / email / save (right under the table)
    # -----------------------------------------------------------------
    st.markdown("---")
    st.caption("Click Submit to lock in "
               "this scenario for download, email, or saving.")

    if st.button("Submit this scenario", type="primary"):
        if partner_email and not email_sender.is_valid_email(partner_email):
            st.error(f"'{partner_email}' doesn't look like a valid Partner Email.")
        elif rm_email and not email_sender.is_valid_email(rm_email):
            st.error(f"'{rm_email}' doesn't look like a valid RM Email.")
        else:
            st.session_state["submitted"] = {
                "inputs": inputs, "projection": projection, "milestones": milestones,
                "signature": current_signature, "highlight_year": highlight_year,
                "partner_email": partner_email, "rm_email": rm_email,
            }

    submitted = st.session_state.get("submitted")
    if submitted:
        stale = submitted["signature"] != current_signature
        if stale:
            st.warning("Inputs have changed since you last submitted — the actions below still reflect the "
                       "**previously submitted** scenario. Click Submit again to refresh them.")
        else:
            st.markdown("<div class='submitted-banner'>Scenario submitted and ready.</div>", unsafe_allow_html=True)

        sub_inputs = submitted["inputs"]
        sub_projection = submitted["projection"]
        sub_milestones = submitted["milestones"]
        sub_highlight = submitted["highlight_year"]
        sub_partner_email = submitted.get("partner_email", "")
        sub_rm_email = submitted.get("rm_email", "")

        pdf_bytes = export.build_pdf_bytes(sub_inputs, sub_projection, sub_milestones)
        csv_bytes = export.build_csv_bytes(sub_inputs, sub_projection)

        tab_download, tab_email, tab_sheet = st.tabs(["📄 Download", "📧 Email PDF", "☁️ Save to Google Sheet"])

        with tab_download:
            dl1, dl2 = st.columns(2)
            dl1.download_button("Download PDF", pdf_bytes, file_name="income_projection.pdf",
                                 mime="application/pdf", use_container_width=True)
            dl2.download_button("Download CSV", csv_bytes, file_name="income_projection.csv",
                                 mime="text/csv", use_container_width=True)

        with tab_email:
            to_email = st.text_input("Send to", value=sub_partner_email, key="email_to")
            also_rm = False
            if sub_rm_email:
                also_rm = st.checkbox(f"Also send to RM ({sub_rm_email})", value=True, key="email_also_rm")
            email_subject = st.text_input("Subject", value="Your Income Projection", key="email_subject")
            email_body = st.text_area(
                "Message", key="email_body",
                value="Hi,\n\nPlease find attached your income projection.\n\nRegards,\nWealthy Partner Desk",
            )
            if st.button("Send Email", key="send_email_btn"):
                recipients = [to_email] + ([sub_rm_email] if also_rm else [])
                ok, message = email_sender.send_email_with_pdf(
                    st.secrets, recipients, email_subject, email_body, pdf_bytes,
                )
                (st.success if ok else st.error)(message)

        with tab_sheet:
            if sheets_webhook.get_webhook_config(st.secrets) is None:
                st.info("Google Sheets saving isn't set up yet — ask whoever administers this app to add a "
                        "[sheet_webhook] block to Secrets (see README). Once that's done, this becomes a "
                        "one-click Save for everyone — no per-user setup needed.")
            if st.button("Save to Google Sheet", key="save_sheet_btn"):
                ok, message = sheets_webhook.append_submission(
                    st.secrets, sub_inputs, sub_projection, sub_highlight,
                    sub_partner_email, sub_rm_email,
                )
                (st.success if ok else st.error)(message)

st.markdown("---")
chart_years = [r["year"] for r in projection]
c1, c2, c3 = st.columns(3)
with c1:
    fig = go.Figure()
    fig.add_bar(x=chart_years, y=[r["trail_yr"] for r in projection], name="Trail")
    fig.add_bar(x=chart_years, y=[r["cross_sell_total"] for r in projection], name="Cross-Sell")
    fig.add_bar(x=chart_years, y=[r["demat_yr"] for r in projection], name="Demat")
    fig.update_layout(barmode="stack", title="Total Income Growth")
    st.plotly_chart(fig, use_container_width=True)
with c2:
    fig = go.Figure()
    fig.add_bar(x=chart_years, y=[r["fresh_investment_cum"] for r in projection], name="Fresh Investment")
    fig.add_bar(x=chart_years, y=[r["market_gains_cum"] for r in projection], name="Market Appreciation")
    fig.update_layout(barmode="stack", title="AUM Composition")
    st.plotly_chart(fig, use_container_width=True)
with c3:
    fig = go.Figure()
    totals = [max(r["total_income"], 1) for r in projection]
    fig.add_bar(x=chart_years, y=[100 * r["trail_yr"] / t for r, t in zip(projection, totals)], name="Trail")
    fig.add_bar(x=chart_years, y=[100 * r["cross_sell_total"] / t for r, t in zip(projection, totals)], name="Cross-sell")
    fig.add_bar(x=chart_years, y=[100 * r["demat_yr"] / t for r, t in zip(projection, totals)], name="Demat")
    fig.update_layout(barmode="stack", title="Income Mix %", yaxis_range=[0, 100])
    st.plotly_chart(fig, use_container_width=True)

in this the date is not taking IST, whilte saving data to google sheet
