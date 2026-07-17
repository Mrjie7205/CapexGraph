# The self-contained report intentionally keeps compact inline CSS declarations.
# ruff: noqa: E501
from __future__ import annotations

import html
import json
from pathlib import Path

from capexgraph.runtime.artifacts import atomic_write_text
from capexgraph.runtime.store import runs_dir
from capexgraph.workflows import load_run


def _read_artifact(run_id: str, filename: str) -> dict:
    path = runs_dir() / run_id / filename
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def render_run_report(run_id: str, output_path: Path | None = None) -> Path:
    run = load_run(run_id)
    if run is None:
        raise KeyError(f"Research run not found: {run_id}")
    decision = _read_artifact(run_id, "decision.json")
    financials = _read_artifact(run_id, "financials.json")
    node_by_id = {node.id: node for node in run.nodes}

    edge_rows = "".join(
        "<tr>"
        f"<td>{html.escape(node_by_id.get(edge.source, edge.source).label if edge.source in node_by_id else edge.source)}</td>"
        f"<td>{html.escape(edge.relationship.value)}</td>"
        f"<td>{html.escape(node_by_id.get(edge.target, edge.target).label if edge.target in node_by_id else edge.target)}</td>"
        f"<td>{html.escape(edge.product)}</td>"
        f"<td><span class='confidence {html.escape(edge.confidence.value)}'>{html.escape(edge.confidence.value)}</span></td>"
        f"<td>{len(edge.evidence_ids)}</td>"
        "</tr>"
        for edge in run.edges
    ) or "<tr><td colspan='6'>No relationship edges were produced.</td></tr>"

    candidate_cards = "".join(
        "<article class='candidate'>"
        f"<div><span>{html.escape(candidate.verdict.value)}</span><b>{html.escape(candidate.confidence.value)}</b></div>"
        f"<h3>{html.escape(node_by_id[candidate.node_id].label if candidate.node_id in node_by_id else candidate.node_id)}</h3>"
        f"<p>{html.escape(candidate.thesis)}</p>"
        f"<small>Risks · {html.escape(' / '.join(candidate.risks) or 'not supplied')}</small>"
        "</article>"
        for candidate in run.candidates
    ) or "<p>No candidates were produced.</p>"

    source_items = "".join(
        "<li>"
        f"<span>{html.escape(item.status.value)}</span>"
        f"<strong>{html.escape(item.title)}</strong>"
        f"<small>{html.escape(str(item.source_url or 'No URL'))}</small>"
        "</li>"
        for item in run.evidence
    ) or "<li>No evidence items were produced.</li>"

    limitations = "".join(
        f"<li>{html.escape(str(item))}</li>" for item in decision.get("limitations", [])
    ) or "<li>No structured limitations artifact was available.</li>"
    next_actions = "".join(
        f"<li>{html.escape(str(item))}</li>" for item in decision.get("next_actions", [])
    ) or "<li>Review the graph and evidence ledger.</li>"
    financial_note = (
        f"{len(financials.get('comparisons', []))} source-linked comparisons"
        if financials
        else "No structured financial comparison for this mode"
    )

    document = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>CapexGraph · {html.escape(run.subject)}</title>
  <style>
    :root {{ --paper:#f3efe5; --ink:#211f1b; --muted:#736c60; --line:#c9c0b1; --wine:#6f1f2b; --green:#2d6854; }}
    * {{ box-sizing:border-box; }} body {{ margin:0; color:var(--ink); background:var(--paper); font-family:Georgia,serif; }}
    main {{ max-width:1120px; margin:auto; padding:56px 42px 80px; }}
    header {{ display:grid; grid-template-columns:1fr auto; border-bottom:2px solid var(--ink); padding-bottom:26px; }}
    .kicker, small, th, .meta, .confidence, .candidate span, .candidate b {{ font-family:Consolas,monospace; text-transform:uppercase; letter-spacing:.08em; }}
    .kicker {{ color:var(--wine); font-size:11px; }} h1 {{ margin:12px 0 0; font-size:62px; line-height:.92; font-weight:400; }}
    .meta {{ text-align:right; font-size:10px; line-height:1.8; color:var(--muted); }}
    .summary {{ display:grid; grid-template-columns:1.3fr .7fr; gap:42px; padding:35px 0; border-bottom:1px solid var(--line); }}
    .summary p {{ font-size:24px; line-height:1.45; margin:0; }} .summary ul {{ margin:0; padding-left:18px; color:var(--muted); }}
    section {{ margin-top:38px; }} h2 {{ font-size:14px; font-family:Consolas,monospace; text-transform:uppercase; letter-spacing:.1em; color:var(--wine); }}
    table {{ width:100%; border-collapse:collapse; font-size:14px; }} th,td {{ text-align:left; border-bottom:1px solid var(--line); padding:12px 9px; }} th {{ font-size:9px; color:var(--muted); }}
    .confidence {{ font-size:8px; color:var(--wine); }} .confidence.high {{ color:var(--green); }}
    .candidates {{ display:grid; grid-template-columns:repeat(3,1fr); gap:12px; }} .candidate {{ border:1px solid var(--line); padding:18px; }}
    .candidate div {{ display:flex; justify-content:space-between; }} .candidate span,.candidate b {{ font-size:8px; color:var(--wine); }}
    .candidate h3 {{ font-size:24px; margin:18px 0 8px; }} .candidate p {{ line-height:1.45; min-height:62px; }} .candidate small {{ color:var(--muted); line-height:1.5; }}
    .sources {{ list-style:none; padding:0; }} .sources li {{ display:grid; grid-template-columns:90px 1fr; gap:8px 14px; border-bottom:1px solid var(--line); padding:12px 0; }}
    .sources span {{ color:var(--green); font:9px Consolas,monospace; text-transform:uppercase; }} .sources small {{ grid-column:2; color:var(--muted); text-transform:none; overflow-wrap:anywhere; }}
    .actions {{ display:grid; grid-template-columns:1fr 1fr; gap:40px; }} footer {{ border-top:2px solid var(--ink); margin-top:50px; padding-top:18px; color:var(--muted); font:10px Consolas,monospace; }}
    @media(max-width:760px) {{ main {{ padding:32px 18px; }} h1 {{ font-size:42px; }} .summary,.actions {{ grid-template-columns:1fr; }} .candidates {{ grid-template-columns:1fr; }} header {{ grid-template-columns:1fr; }} .meta {{ text-align:left; margin-top:18px; }} }}
  </style>
</head>
<body><main>
  <header><div><div class="kicker">CapexGraph / {html.escape(run.mode.value)} scan</div><h1>{html.escape(run.subject)}</h1></div><div class="meta">RUN {html.escape(run.id)}<br>AS OF {run.as_of_date}<br>STATUS {html.escape(run.status.value)}</div></header>
  <div class="summary"><p>{html.escape(decision.get('summary', 'Structured decision not available.'))}</p><ul><li>{len(run.nodes)} nodes / {len(run.edges)} edges</li><li>{len(run.evidence)} evidence items</li><li>{len(run.candidates)} candidates</li><li>{html.escape(financial_note)}</li></ul></div>
  <section><h2>01 / Grounded relationship map</h2><table><thead><tr><th>Source</th><th>Relation</th><th>Target</th><th>Product</th><th>Confidence</th><th>Sources</th></tr></thead><tbody>{edge_rows}</tbody></table></section>
  <section><h2>02 / Research queue</h2><div class="candidates">{candidate_cards}</div></section>
  <section><h2>03 / Evidence ledger</h2><ul class="sources">{source_items}</ul></section>
  <section class="actions"><div><h2>Limitations</h2><ul>{limitations}</ul></div><div><h2>Next actions</h2><ol>{next_actions}</ol></div></section>
  <footer>{html.escape(decision.get('disclaimer', 'Research and education only; not investment advice.'))}</footer>
</main></body></html>"""
    destination = output_path or (runs_dir() / run_id / "report.html")
    atomic_write_text(destination.resolve(), document)
    return destination.resolve()
