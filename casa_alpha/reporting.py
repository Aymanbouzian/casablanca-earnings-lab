import base64
import html
import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .events import net_return, price_ratio


def pct(x):
    return "n/a" if pd.isna(x) else f"{x * 100:+.2f}%"


def money(x):
    return f"{x:,.2f} MAD"


def mdtable(headers, rows):
    return "\n".join(
        ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
        + ["| " + " | ".join(str(x).replace("|", "/") for x in row) + " |" for row in rows]
    )


def htable(headers, rows):
    return (
        "<table><thead><tr>"
        + "".join("<th>" + html.escape(str(x)) + "</th>" for x in headers)
        + "</tr></thead><tbody>"
        + "".join(
            "<tr>" + "".join("<td>" + html.escape(str(x)) + "</td>" for x in row) + "</tr>"
            for row in rows
        )
        + "</tbody></table>"
    )


def case_chart(root, d, base, cfg):
    selected = base[(base.event_id == "AKT_FY2024") & (base.window_status == "complete")]
    if selected.empty:
        return None
    e = selected.iloc[0]
    cal = d.calendar[e.entry_index : int(e.exit_index) + 1]
    ratios = np.array([price_ratio(d.frames[e.ticker], e.entry_date, x) for x in cal])
    net = np.array([net_return(x, cfg.fee_rate, cfg.slippage_rate) for x in ratios])
    peers = e.peer_tickers.split(";") if e.peer_tickers else []
    peer = (
        np.mean(
            [[price_ratio(d.frames[t], e.entry_date, x) - 1 for x in cal] for t in peers], axis=0
        )
        if peers
        else None
    )
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 10,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.spines.left": False,
            "axes.edgecolor": "#cbd5df",
            "text.color": "#182c3c",
            "axes.labelcolor": "#536575",
            "xtick.color": "#536575",
            "ytick.color": "#536575",
        }
    )
    fig, ax = plt.subplots(figsize=(9, 4.2), dpi=180)
    x = np.arange(len(cal))
    ax.axhline(0, color="#b3bec7", lw=1)
    ax.plot(x, 100 * (ratios - 1), color="#18847a", lw=2.5, label="Akdital: price return")
    ax.plot(x, 100 * net, color="#b64a32", lw=2.5, label="Akdital: net if sold at each close")
    if peer is not None:
        ax.plot(
            x,
            100 * peer,
            color="#7b8795",
            lw=2,
            linestyle="--",
            label=f"Eligible peer: {e.peer_tickers} (gross)",
        )
    ax.set_xticks(x)
    ax.set_xticklabels([str(i) for i in x])
    ax.set_xlabel("Exchange sessions after entry (entry = 0)")
    ax.set_ylabel("Return (%)")
    ax.grid(axis="y", color="#e7edf1")
    ax.legend(frameon=False, loc="lower left", fontsize=9)
    ax.set_title(
        "Akdital FY2024: exploratory case study", loc="left", fontweight="bold", fontsize=14, pad=15
    )
    ax.text(
        1.0,
        1.02,
        f"{e.entry_date:%d %b} - {e.exit_date:%d %b %Y}",
        transform=ax.transAxes,
        ha="right",
        fontsize=9,
        color="#536575",
    )
    fig.tight_layout(pad=1.5)
    path = root / "outputs/earnings/akdital_event_path.png"
    fig.savefig(path, facecolor="white")
    plt.close(fig)
    return path


def build_reports(root, d, results, summary, cfg):
    base = results["base_10"]
    sources = json.loads((root / "data/earnings/sources.json").read_text(encoding="utf-8"))
    src = {s["source_id"]: s for s in sources}
    chart = case_chart(root, d, base, cfg)
    case = (
        base[base.event_id == "AKT_FY2024"].iloc[0]
        if base.event_id.eq("AKT_FY2024").any()
        else None
    )
    sections = []

    def section(title, paras, headers=None, rows=None):
        sections.append(dict(title=title, paragraphs=paras, headers=headers, rows=rows))

    section(
        "Decision",
        [
            "Do not deploy the new earnings sleeve. This investigation did not establish a strong, tradable alpha. The appropriate allocation to this unvalidated sleeve is 0%; the live-order file is empty. This does not prescribe changes to an existing account or the earlier momentum strategy.",
            f"The supplied archive contains {summary['price_histories']} stock histories through {summary['last_price_session']}. The collected event sample covers {summary['collected_events']} annual releases, {summary['collected_event_issuers']} issuers and {summary['forecast_records']} forecast records. There are {summary['verified_signals']} fully verified qualifying signals. This is a feasibility sample, not a complete market scrape or a representative historical panel.",
            "A failed deployment gate is not proof that earnings drift cannot exist in Morocco. It means this dataset and experiment cannot support putting money behind it. No statistical alpha, t-statistic or annualized Sharpe is claimed from one exploratory event.",
        ],
    )
    case_rows = []
    if case is not None:
        case_rows = [
            [
                "Forecast / reported profit",
                f"{case.forecast:,.0f} / {case.actual:,.0f} million MAD",
            ],
            ["Apparent surprise", pct(case.surprise)],
            ["Publication", f"{case.publication_date:%Y-%m-%d}"],
            ["Modeled entry", f"{case.entry_date:%Y-%m-%d} at {case.entry_close:,.2f} MAD"],
            ["Modeled exit", f"{case.exit_date:%Y-%m-%d} at {case.exit_close:,.2f} MAD"],
            ["Holding intervals", str(int(case.holding_intervals))],
            ["Price return", pct(case.gross_return)],
            ["Net return", pct(case.net_return)],
            ["Peer / gross return", f"{case.peer_tickers} / {pct(case.peer_gross_return)}"],
            ["Net minus peer gross", f"{case.net_sector_excess * 100:+.2f} percentage points"],
        ]
        section(
            "The Akdital case",
            [
                "The July 2024 document gives a management-plan-derived, pre-money RNPG assumption of 276 million MAD; the March 2025 release reports 315 million. The arithmetic gap is 14.13%. Scope equivalence and intervening revisions are not fully verified, so this is a case study rather than a clean analyst-surprise observation.",
                f"The fixed ten-session trade lost {abs(case.net_return) * 100:.2f}% after modeled costs. Its one eligible peer, {case.peer_tickers}, also fell. A positive relative difference against one weak peer is not evidence of a repeatable profitable strategy. Pharmaceutical businesses are also imperfect comparators for a hospital operator; the inherited sector grouping is provisional.",
                "Sources: AGR_AKT_JUL24, page 5; AKT24, page 1; AKT_INDEX. The chart deducts both sides of the hypothetical round trip at every close, so the net series starts below zero.",
            ],
            ["Measure", "Observed / modeled value"],
            case_rows,
        )
    scenario_rows = []
    for name, label in [
        ("base_10", "10 sessions (fixed main test)"),
        ("hold_20", "20 sessions (diagnostic)"),
        ("entry_plus_1", "Entry one session later"),
        ("double_cost", "Double fees and slippage"),
    ]:
        rows = results[name]
        r = rows[rows.event_id == "AKT_FY2024"]
        if not r.empty:
            e = r.iloc[0]
            scenario_rows.append(
                [
                    label,
                    pct(e.gross_return),
                    pct(e.net_return),
                    f"{e.net_sector_excess * 100:+.2f} pp"
                    if pd.notna(e.net_sector_excess)
                    else "n/a",
                ]
            )
    section(
        "Robustness, without choosing a winner",
        [
            "These variants were specified before return inspection. They use the same exploratory Akdital observation, not independent confirming samples. The original ten-session rule remains the primary test. Neither a longer holding period nor a later entry is promoted because it looks better.",
            "Release-year summaries for all collected events are saved in scenario_summary.csv. Pooling small beats, negative surprises, stale forecasts and unresolved releases would not test the strong-surprise rule. Issuer-cluster confidence intervals are withheld because the verified signal sample is empty.",
        ],
        ["Variant", "Gross", "Net", "Net - peer gross"],
        scenario_rows,
    )
    section(
        "Data traps that changed the conclusion",
        [
            "Marsa Maroc: the November 2024 reported-RNPG forecast of 1,150 million implies a 10.17% gap against the 1,267 million result. A February 2025 update exists before publication and shows recurring RNPG of 1,200 million. Comparing 1,267 with 1,200 gives only 5.58%, but recurring and reported profit still require a verified bridge. The engine therefore blocks the obsolete forecast rather than treating either comparison as a verified signal.",
            "Banks FY2025: six matched July 2025 forecasts are retained for diagnostics. An AGR banking update dated 6 February 2026 predates their annual releases; its public summary lacks the detailed numerical table. The earlier forecasts cannot be asserted to be the latest expectations.",
            "Akdital FY2025: the collected 402 million forecast is more than 270 days old and is excluded. A different Akdital presentation forecasts total consolidated net income, not RNPG, so it cannot be substituted.",
            "Publication date matters: a board meeting, first press release, regulator upload and annual-report filing can be different dates. Proxy dates are labeled and excluded from the verified cohort. Reported and recurring profit, thousands and millions, and annual and half-year periods are matched explicitly.",
        ],
    )
    p = summary["portfolio"]["case_study"]
    v = summary["portfolio"]["verified"]
    section(
        "Portfolio and risk implementation",
        [
            "The verified-signal simulation holds its virtual capital in cash because no qualifying verified signal exists. A separately labeled exploratory simulation measures the Akdital case with realistic cash accounting and position limits. Cash yield is set to zero; this is not a recommendation for the user's entire account.",
            "Orders use prior-close prices and NAV to set desired whole shares. Simulated fills are bounded by 1% of lagged 60-session average shares and 1% of actual session shares. Actual full-day volume is a retrospective fill bound, not information assumed known when placing an order. Close execution and constant slippage remain approximations.",
            "A first partial entry cancels the remainder; no averaging down or top-up is allowed. Entry expires after three sessions. Scheduled exits remain queued while liquidity is unavailable. Price-driven weight breaches queue trims for the next session. A 5% portfolio drawdown disables entries and queues liquidation for the next session; it cannot guarantee a 5% maximum loss.",
            "The illustrative trade bought 39 shares of AKT, trimmed 1 share after a weight breach, and sold the remaining 38 at the scheduled exit. This explains why its portfolio outcome differs from simply multiplying the event return by a 5% allocation."
            if p["buy_fills"] == 1 and case is not None
            else "Consult the separate fill and order ledgers for executed and unfilled quantities.",
        ],
        ["Control / result", "Value"],
        [
            ["Starting virtual capital", money(cfg.initial_capital)],
            ["Stock / sector / gross entry caps", "5% / 20% / 30%"],
            ["Fees / slippage per side", "0.77% / 0.10%"],
            ["Verified portfolio: final NAV", money(v["end_nav"])],
            ["Exploratory portfolio: final NAV", money(p["end_nav"])],
            ["Exploratory P&L", money(p["net_pnl"])],
            ["Exploratory return", pct(p["total_return"])],
            ["Exploratory max drawdown", pct(p["max_drawdown"])],
            ["Exploratory fees paid", money(p["fees_paid"])],
            ["Open positions at end", str(p["open_positions_at_end"])],
            ["Live orders", "0"],
        ],
    )
    section(
        "What would make the hypothesis testable",
        [
            "Build a much broader event panel without looking at each event's return during collection. Archive the first release, accounting measure, fiscal period, source hash and every intervening forecast revision. Use expectations that were actually available before each event; a later annual report or a current consensus cannot reconstruct them automatically.",
            "The frozen minimum screen is 30 verified events across at least 10 issuers and 3 release years, with positive net sector-relative results and an issuer-cluster 95% lower bound above zero. Require positive latest-year and double-cost results, plus complete corporate actions, historical universe and calendar. Thirty events alone is not sufficient statistical power or proof.",
            "The present archive has incomplete dividends and actions, a selected current universe, an inferred calendar, incomplete peer announcements and provisional sectors. This is price-return research. The period has already been inspected for other strategies, so no segment is described as untouched out-of-sample evidence.",
            "An event-screened peer comparison excludes peers with collected releases during the holding window. That exclusion uses future event dates and is explicitly an ex-post descriptive control, not an investable benchmark. A second comparison keeps the publication-date liquid peer set unchanged. Neither comparison enters the signal or portfolio decisions.",
            "No short selling, leverage, broker integration or order submission is implemented. Settlement constraints, taxes, auction queues, suspensions, spreads and complete distribution income are not modeled. The ten-session rule was not modified after seeing returns.",
        ],
    )
    audit_rows = []
    for _, e in base.iterrows():
        status = (
            "verified match; below threshold"
            if e.verified_match and not e.verified_signal
            else ("verified signal" if e.verified_signal else e.issues.replace("_", " "))
        )
        audit_rows.append(
            [
                e.event_id,
                f"{e.publication_date:%Y-%m-%d}",
                pct(e.surprise),
                pct(e.net_return),
                status,
            ]
        )
    section(
        "Every collected event, including exclusions",
        [
            "Returns below are descriptive ten-session outcomes for the collected rows, not the returns of a tradable strong-surprise portfolio. Unverified forecasts, proxy dates and stale estimates remain visible. No losing observation was dropped."
        ],
        ["Event", "Date used", "Nominal gap", "Net return", "Status"],
        audit_rows,
    )
    sections.append(
        dict(
            title="Reproduce and extend",
            paragraphs=[
                "Open RESEARCH_REPORT.html for this report. On Windows, extract the ZIP and double-click RUN_RESEARCH.bat. It creates a local virtual environment, installs requirements, runs the tests and regenerates the study. No PowerShell activation or execution-policy change is needed.",
                "Manual commands: python -m venv .venv; .venv\\Scripts\\python.exe -m pip install -r requirements.txt; .venv\\Scripts\\python.exe -m unittest discover -s tests; .venv\\Scripts\\python.exe run_research.py. Run each command separately.",
                "The default study runs offline. collect_sources.py is an optional public-document downloader that writes hashes and errors; it does not convert arbitrary PDF numbers into approved earnings records. Review dates and accounting scope before adding events.csv or forecasts.csv rows. Sources are linked, not redistributed as full reports.",
                "Input and code hashes are in outputs/earnings/input_manifest_sha256.json. PROTOCOL.md is hash-checked before each run. The source archive and thresholds are versioned; a parameter change is a new exploratory experiment, not an untouched validation.",
            ],
            headers=None,
            rows=None,
        )
    )
    heading = f"Casablanca earnings research | v7\nAs of {summary['research_as_of']} - prices through {summary['last_price_session']}"
    md = [
        "# Casablanca earnings research - v7",
        f"Research as of {summary['research_as_of']}; prices through {summary['last_price_session']}. **RESEARCH ONLY - NO VALIDATED ALPHA**",
    ]
    parts = []
    for s in sections:
        md += ["\n## " + s["title"]] + ["\n" + x for x in s["paragraphs"]]
        parts.append(
            "<section><h2>"
            + html.escape(s["title"])
            + "</h2>"
            + "".join("<p>" + html.escape(x) + "</p>" for x in s["paragraphs"])
        )
        if s["headers"]:
            md.append("\n" + mdtable(s["headers"], s["rows"]))
            parts.append(htable(s["headers"], s["rows"]))
        if s["title"] == "The Akdital case" and chart:
            md.append("\n![Akdital event path](outputs/earnings/akdital_event_path.png)")
            parts.append(
                '<img class="chart" alt="Akdital event path" src="data:image/png;base64,'
                + base64.b64encode(chart.read_bytes()).decode()
                + '">'
            )
        parts.append("</section>")
    key_sources = [
        "AGR_AKT_JUL24",
        "AKT24",
        "AGR_MSA_NOV24",
        "AGR_MSA_FEB25",
        "MSA24",
        "AGR_BANK_JAN25",
        "AGR_BANK_JUL25",
        "AGR_BANK_FEB26",
        "AKT_INDEX",
    ]
    md.append("\n## Primary sources")
    src_html = "<section><h2>Primary sources</h2><ul>"
    for sid in key_sources:
        s = src[sid]
        label = (
            sid
            + " - "
            + s["title"]
            + (f"; PDF page {s['pdf_page_1_based']}" if s["pdf_page_1_based"] else "")
        )
        md.append(f"\n- [{label}]({s['url']})")
        src_html += (
            '<li><a href="'
            + html.escape(s["url"], quote=True)
            + '">'
            + html.escape(label)
            + "</a></li>"
        )
    src_html += "</ul><p>Full source register: data/earnings/sources.json. Forecast and actual rows carry source IDs. Retrieval date: 10 November 2026.</p></section>"
    md.append(
        "\nFull source register: `data/earnings/sources.json`. Data collection is incomplete; see integrity.json and the download log."
    )
    (root / "RESEARCH_REPORT.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    css = "body{margin:0;background:#eef2f5;color:#203544;font:16px/1.65 system-ui,Arial}main{max-width:1050px;margin:auto;padding:45px 40px;background:white}header{border-top:7px solid #18847a;padding:30px 0}h1{font-size:38px;line-height:1.15;margin:15px 0}h2{font-size:24px;color:#123f52;margin-top:0}section{padding:28px 0;border-top:1px solid #dbe4e9}p{max-width:92ch}.label{letter-spacing:2px;font-size:12px;font-weight:bold;color:#18847a}.status{padding:12px 18px;background:#fff0e8;color:#9c3f26;border-left:4px solid #b64a32;font-weight:bold}table{width:100%;border-collapse:collapse;font-size:14px;margin:22px 0}th{text-align:left;background:#143e50;color:white}th,td{padding:10px 12px;vertical-align:top;border-bottom:1px solid #e0e7ec}tbody tr:nth-child(even){background:#f5f8fa}a{color:#08786d;overflow-wrap:anywhere}.chart{width:100%;height:auto}footer{font-size:12px;color:#697985}@media(max-width:700px){main{padding:20px}table{font-size:11px}th,td{padding:6px}h1{font-size:30px}}@media print{body{background:white}main{padding:0}section{break-inside:avoid}table{font-size:10px}}"
    doc = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Casablanca earnings research v7</title><style>'
        + css
        + '</style></head><body><main><header><div class="label">CASABLANCA / QUANT RESEARCH / V7</div><h1>Testing an earnings edge</h1><p>'
        + html.escape(heading.split("\n")[1])
        + '</p><div class="status">NO VALIDATED ALPHA - NEW SLEEVE ALLOCATION: 0%</div></header>'
        + "".join(parts)
        + src_html
        + "<footer>Retrospective exploratory research. Exact arithmetic and reproducible software do not repair missing historical information.</footer></main></body></html>"
    )
    (root / "RESEARCH_REPORT.html").write_text(doc, encoding="utf-8")
    (root / "outputs/earnings/report_sections.json").write_text(
        json.dumps(
            dict(
                sections=sections,
                case_rows=case_rows,
                scenario_rows=scenario_rows,
                primary_sources=[src[x] for x in key_sources],
            ),
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
