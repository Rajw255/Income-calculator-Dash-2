"""
INCOME PROJECTION ENGINE
==========================
Powers the "Income Calculator" page — a long-horizon (multi-year) partner
income simulator in the style of wealthy.in's Partner Income Calculator:
starting book + monthly client acquisition + SIP step-ups + lumpsum +
market compounding + trail income + optional cross-sell income streams,
projected out year by year.

This is intentionally a SEPARATE tool from the "Target Projection"
page (which answers "will I hit THIS month/quarter's target"). This one
answers "what could my trail book and income look like in 5/10/25 years
if I keep acquiring clients at this pace" — a business-planning /
recruitment-pitch tool, not a period-actuals tool. It runs entirely on
user-entered assumptions, not on Transaction Fact.

All money amounts are in plain rupees internally; the UI layer
(formatting.format_inr) handles L/Cr display.
"""

from dataclasses import dataclass, field


@dataclass
class CrossSellAssumption:
    enabled: bool = False
    commission_pct: float = 0.0
    # meaning of `rate` depends on the stream — see simulate() below
    rate: float = 0.0


@dataclass
class ProjectionInputs:
    starting_clients: int = 0
    starting_aum: float = 0.0          # rupees
    new_clients_per_month: int = 5
    sip_per_client_month: float = 5000.0
    sip_stepup_pct: float = 1.0
    annual_lumpsum_per_client: float = 10000.0
    lumpsum_stepup_pct: float = 0.0
    annual_redemption_pct: float = 5.0
    active_years: int = 25
    trail_rate_pct: float = 0.7
    market_cagr_pct: float = 12.0
    life: CrossSellAssumption = field(default_factory=lambda: CrossSellAssumption(commission_pct=40, rate=10))    # rate = % of clients/yr taking a policy
    health: CrossSellAssumption = field(default_factory=lambda: CrossSellAssumption(commission_pct=30, rate=15))  # rate = % of clients/yr taking a policy
    pms: CrossSellAssumption = field(default_factory=lambda: CrossSellAssumption(commission_pct=1, rate=5))       # rate = % of AUM allocated to PMS/yr
    demat: CrossSellAssumption = field(default_factory=lambda: CrossSellAssumption(rate=210))                     # rate = ₹/active client/month
    life_avg_premium: float = 15000.0
    health_avg_premium: float = 8000.0


def simulate(p: ProjectionInputs):
    """Month-by-month simulation, aggregated to one row per year.

    Returns a list of dicts (one per year, 1..active_years) with the same
    fields shown in the reference UI: clients, sip_contrib, stepup_inflow,
    lumpsum, mkt_gains, total_aum, sip_book_mo, trail_yr, cross-sell
    breakdown, demat_yr, total_income.
    """
    clients = p.starting_clients
    aum = p.starting_aum
    years_out = []

    prev_year_sip_rate = p.sip_per_client_month

    for year in range(1, p.active_years + 1):
        sip_rate = p.sip_per_client_month * (1 + p.sip_stepup_pct / 100) ** (year - 1)
        lumpsum_rate = p.annual_lumpsum_per_client * (1 + p.lumpsum_stepup_pct / 100) ** (year - 1)

        sip_contrib_year = 0.0
        mkt_gains_year = 0.0
        trail_year = 0.0
        clients_sum_for_avg = 0
        new_clients_this_year = 0

        for _m in range(12):
            clients += p.new_clients_per_month
            new_clients_this_year += p.new_clients_per_month
            clients_sum_for_avg += clients

            mkt_gain = aum * (p.market_cagr_pct / 100 / 12)
            aum += mkt_gain
            mkt_gains_year += mkt_gain

            sip_inflow = clients * sip_rate
            aum += sip_inflow
            sip_contrib_year += sip_inflow

            trail_year += aum * (p.trail_rate_pct / 100 / 12)

        avg_clients = clients_sum_for_avg / 12

        lumpsum_year = clients * lumpsum_rate
        aum += lumpsum_year

        redemption_year = aum * (p.annual_redemption_pct / 100)
        aum -= redemption_year

        stepup_inflow = (sip_rate - prev_year_sip_rate) * clients * 12 if year > 1 else 0.0
        prev_year_sip_rate = sip_rate

        cross_sell = {}
        if p.life.enabled:
            cross_sell["Life Insurance"] = new_clients_this_year * (p.life.rate / 100) * p.life_avg_premium * (p.life.commission_pct / 100)
        if p.health.enabled:
            cross_sell["Health Insurance"] = new_clients_this_year * (p.health.rate / 100) * p.health_avg_premium * (p.health.commission_pct / 100)
        if p.pms.enabled:
            cross_sell["PMS"] = aum * (p.pms.rate / 100) * (p.pms.commission_pct / 100)
        demat_year = avg_clients * p.demat.rate * 12 if p.demat.enabled else 0.0

        total_income = trail_year + sum(cross_sell.values()) + demat_year

        years_out.append({
            "year": year,
            "clients": clients,
            "sip_contrib": sip_contrib_year,
            "stepup_inflow": stepup_inflow,
            "lumpsum": lumpsum_year,
            "mkt_gains": mkt_gains_year,
            "total_aum": aum,
            "sip_book_mo": clients * sip_rate,
            "trail_yr": trail_year,
            "cross_sell": cross_sell,
            "cross_sell_total": sum(cross_sell.values()),
            "demat_yr": demat_year,
            "total_income": total_income,
            "fresh_investment_cum": None,   # filled below
        })

    # cumulative fresh investment (for the AUM-composition chart)
    cum = 0.0
    for row in years_out:
        cum += row["sip_contrib"] + row["lumpsum"]
        row["fresh_investment_cum"] = cum
        row["market_gains_cum"] = row["total_aum"] - cum if row["total_aum"] > cum else 0.0

    # uplift vs previous row in the FULL yearly series (not just milestones)
    prev_income = None
    for row in years_out:
        row["uplift_pct"] = None if prev_income in (None, 0) else round((row["total_income"] - prev_income) / prev_income * 100, 1)
        prev_income = row["total_income"]

    return years_out


def milestone_years(active_years: int):
    candidates = [1, 3, 5, 10, 15, 20, 25, 30]
    return [y for y in candidates if y <= active_years] or [active_years]
