"""
Weather Planning Report Generator
------------------------------------
Builds a structured planning report from agent results.
Can output:
  - A structured dict (for JSON API)
  - A Markdown string (for email body / download)
  - An HTML string (for rendered display)
"""

from __future__ import annotations
from datetime import datetime


def generate_report(
    options: list[dict],
    intent: dict,
    activity: str,
    explanation: str = "",
    generated_at: str | None = None,
) -> dict:
    """
    Build a structured planning report dict from agent options.
    The dict can be serialised to JSON for the API or rendered as Markdown/HTML.
    """
    now_str = generated_at or datetime.now().strftime("%Y-%m-%d %H:%M UTC")

    if not options:
        return {
            "title": f"Weather Planning Report — {activity}",
            "generated_at": now_str,
            "summary": "No data available.",
            "recommendation": None,
            "alternatives": [],
            "markdown": f"# Weather Planning Report\n\nNo forecast data could be retrieved.",
        }

    winner = options[0]
    alternatives = options[1:]

    # ── Summary block ────────────────────────────────────────────
    summary_lines = [
        f"Activity: {activity}",
        f"Recommendation: {winner['location']} on {winner['date']}",
        f"Overall Score: {winner['score']}/100 (Grade {winner.get('grade', '?')})",
        f"Comfort: {winner.get('comfort', '?')}/100 | "
        f"Safety: {winner.get('safety', '?')}/100 | "
        f"Suitability: {winner.get('suitability', '?')}/100",
        f"Confidence: {winner.get('confidence_label', 'Historical climate estimate')}",
    ]

    # ── Build Markdown ───────────────────────────────────────────
    md_lines = [
        f"# Weather Planning Report",
        f"**Generated:** {now_str}",
        f"",
        f"## Activity",
        f"{activity}",
        f"",
        f"## Top Recommendation",
        f"**{winner['location']} — {winner['date']}**",
        f"",
        f"| Metric | Score |",
        f"|--------|-------|",
        f"| Overall | {winner['score']}/100 (Grade {winner.get('grade','?')}) |",
        f"| Comfort | {winner.get('comfort','?')}/100 |",
        f"| Safety | {winner.get('safety','?')}/100 |",
        f"| Suitability | {winner.get('suitability','?')}/100 |",
        f"",
        f"**Weather Conditions:**",
        f"- Temperature (feels-like): {winner.get('temp', '?')}°C",
        f"- Actual Temperature: {winner.get('temp_actual', winner.get('temp', '?'))}°C",
        f"- Rainfall: {winner.get('rain', '?')} mm/day",
        f"- Wind Speed: {winner.get('wind', '?')} km/h",
        f"- Humidity: {winner.get('humidity', '?')}%",
        f"- Cloud Cover: {winner.get('cloud_pct', '?')}%",
        f"",
        f"**Forecast Confidence:** {winner.get('confidence_label', 'Historical climate estimate')}",
        f"",
    ]

    if explanation:
        md_lines += [f"## Analysis", explanation, ""]

    if winner.get("positives"):
        md_lines += ["## Strengths"]
        for p in winner["positives"]:
            md_lines.append(f"- {p}")
        md_lines.append("")

    if winner.get("risks"):
        md_lines += ["## Risks & Cautions"]
        for r in winner["risks"]:
            md_lines.append(f"- {r}")
        md_lines.append("")

    if winner.get("tips"):
        md_lines += ["## Preparation Tips"]
        for t in winner["tips"]:
            md_lines.append(f"- {t}")
        md_lines.append("")

    if alternatives:
        md_lines += ["## Alternative Options", ""]
        for alt in alternatives[:3]:
            md_lines += [
                f"### {alt['location']} — {alt['date']}",
                f"Overall: {alt['score']}/100 | "
                f"Comfort: {alt.get('comfort','?')} | "
                f"Safety: {alt.get('safety','?')} | "
                f"Suitability: {alt.get('suitability','?')}",
                f"Temp: {alt.get('temp','?')}°C | Rain: {alt.get('rain','?')}mm | Wind: {alt.get('wind','?')}km/h",
                "",
            ]

    if winner.get("venues"):
        md_lines += ["## Nearby Venues & Accommodation", ""]
        for v in winner["venues"][:6]:
            line = f"- **{v['name']}** ({v['type']}, {v['distance_km']}km)"
            if v.get("address"):
                line += f" — {v['address']}"
            if v.get("website"):
                line += f" — [Website]({v['website']})"
            line += f" — [Map]({v['osm_link']})"
            md_lines.append(line)
        md_lines.append("")

    if winner.get("farming"):
        f = winner["farming"]
        md_lines += [
            "## Agricultural Assessment",
            f"**Crop:** {f['crop_name']}",
            f"**Farming Score:** {f['farming_score']}/100 ({f['suitability_label']})",
            f"{f['advice']}",
            "",
        ]
        if f.get("risks"):
            md_lines.append("**Risks:**")
            for r in f["risks"]:
                md_lines.append(f"- {r}")
        if f.get("opportunities"):
            md_lines.append("**Opportunities:**")
            for o in f["opportunities"]:
                md_lines.append(f"- {o}")
        md_lines.append("")

    md_lines += [
        "---",
        f"*Report generated by Weatherly AI on {now_str}.*",
        "*Weather data sourced from NASA POWER (20-year historical). Prophet time-series forecasting. Scores are estimates, not guarantees.*",
    ]

    markdown = "\n".join(md_lines)

    return {
        "title": f"Weather Planning Report — {activity} at {winner['location']}",
        "generated_at": now_str,
        "summary": " | ".join(summary_lines),
        "recommendation": winner,
        "alternatives": alternatives[:3],
        "explanation": explanation,
        "markdown": markdown,
    }


def report_to_html(report: dict) -> str:
    """Converts the Markdown report to simple HTML for email or browser display."""
    import re
    md = report.get("markdown", "No report available.")

    # Very basic Markdown → HTML (avoids a markdown library dependency)
    html = md
    # Headers
    html = re.sub(r"^# (.+)$", r"<h1>\1</h1>", html, flags=re.M)
    html = re.sub(r"^## (.+)$", r"<h2>\1</h2>", html, flags=re.M)
    html = re.sub(r"^### (.+)$", r"<h3>\1</h3>", html, flags=re.M)
    # Bold
    html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)
    # Lists
    html = re.sub(r"^- (.+)$", r"<li>\1</li>", html, flags=re.M)
    html = re.sub(r"(<li>.*</li>)", r"<ul>\1</ul>", html, flags=re.S)
    # Links
    html = re.sub(r"\[(.+?)\]\((.+?)\)", r'<a href="\2">\1</a>', html)
    # Table rows
    html = re.sub(r"^\|(.+)\|$", lambda m: "<tr>" + "".join(f"<td>{c.strip()}</td>" for c in m.group(1).split("|")) + "</tr>", html, flags=re.M)
    # Horizontal rule
    html = html.replace("---", "<hr>")
    # Newlines
    html = html.replace("\n\n", "</p><p>")

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
  body {{ font-family: sans-serif; max-width: 700px; margin: 40px auto; color: #1e293b; }}
  h1 {{ color: #0f172a; }} h2 {{ color: #1e40af; border-bottom: 1px solid #e2e8f0; padding-bottom:4px; }}
  table {{ border-collapse: collapse; width: 100%; margin: 12px 0; }}
  td, th {{ border: 1px solid #e2e8f0; padding: 6px 12px; }}
  li {{ margin: 4px 0; }} hr {{ border: none; border-top: 1px solid #e2e8f0; }}
  p {{ line-height: 1.6; }}
</style>
</head><body>
<p>{html}</p>
</body></html>"""
