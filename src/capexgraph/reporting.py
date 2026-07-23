# The self-contained report intentionally keeps compact inline CSS declarations.
# ruff: noqa: E501
from __future__ import annotations

import html
import json
from pathlib import Path

from capexgraph.runtime.artifacts import atomic_write_text
from capexgraph.runtime.store import runs_dir
from capexgraph.workflows import load_run

RELATIONSHIP_ZH = {
    "supplies": "供应",
    "customer": "客户",
    "peer": "同业",
    "depends_on": "依赖",
    "two_hop": "二阶关联",
}
STATUS_ZH = {
    "proposed": "待采集",
    "captured": "已采集",
    "reviewed": "已审核",
    "rejected": "已驳回",
    "created": "已创建",
    "running": "运行中",
    "needs_review": "待复核",
    "completed": "已完成",
    "failed": "失败",
    "cancelled": "已取消",
}
VERDICT_ZH = {
    "candidate": "候选",
    "watch": "观察",
    "exclude": "排除",
    "unrated": "未评级",
}
CONFIDENCE_ZH = {"high": "高", "medium": "中", "low": "低"}
METRIC_ZH = {
    "revenue": "营收",
    "revenue_yoy": "营收同比",
    "google_cloud_revenue": "Google Cloud收入",
    "google_cloud_revenue_yoy": "Google Cloud收入同比",
    "google_cloud_operating_income": "Google Cloud营业利润",
    "capital_expenditures": "资本开支",
    "free_cash_flow": "自由现金流",
    "equity_securities_gain": "股权证券收益",
    "equity_gain_eps_effect": "股权收益对EPS影响",
    "cloud_backlog": "云业务积压订单",
    "model_api_tokens_per_minute": "模型API每分钟Token",
}
UNIT_ZH = {
    "USD_million": "百万美元",
    "percent": "%",
    "USD_per_share": "美元/股",
    "tokens": "Token",
}


def _read_artifact(run_id: str, filename: str) -> dict:
    path = runs_dir() / run_id / filename
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _uses_chinese(subject: str) -> bool:
    return any("\u4e00" <= character <= "\u9fff" for character in subject)


def render_run_report(run_id: str, output_path: Path | None = None) -> Path:
    run = load_run(run_id)
    if run is None:
        raise KeyError(f"Research run not found: {run_id}")
    decision = _read_artifact(run_id, "decision.json")
    financials = _read_artifact(run_id, "financials.json")
    financial_metrics = _read_artifact(run_id, "financials/metrics.json").get("items", [])
    node_by_id = {node.id: node for node in run.nodes}
    report_language = str(run.manifest.get("report_language") or "")
    chinese = report_language == "zh-CN" or (
        not report_language and _uses_chinese(run.subject)
    )

    def localized(value: str, mapping: dict[str, str]) -> str:
        return mapping.get(value, value) if chinese else value

    def metric_value(value: object) -> str:
        if isinstance(value, (int, float)):
            return f"{value:,.4f}".rstrip("0").rstrip(".")
        return str(value)

    edge_rows = "".join(
        "<tr>"
        f"<td>{html.escape(node_by_id.get(edge.source, edge.source).label if edge.source in node_by_id else edge.source)}</td>"
        f"<td>{html.escape(localized(edge.relationship.value, RELATIONSHIP_ZH))}</td>"
        f"<td>{html.escape(node_by_id.get(edge.target, edge.target).label if edge.target in node_by_id else edge.target)}</td>"
        f"<td>{html.escape(edge.product)}</td>"
        f"<td><span class='confidence {html.escape(edge.confidence.value)}'>{html.escape(localized(edge.confidence.value, CONFIDENCE_ZH))}</span></td>"
        f"<td>{len(edge.evidence_ids)}</td>"
        "</tr>"
        for edge in run.edges
    ) or (
        "<tr><td colspan='6'>未生成关系边。</td></tr>"
        if chinese
        else "<tr><td colspan='6'>No relationship edges were produced.</td></tr>"
    )

    candidate_cards = "".join(
        "<article class='candidate'>"
        f"<div><span>{html.escape(localized(candidate.verdict.value, VERDICT_ZH))}</span><b>{html.escape(localized(candidate.confidence.value, CONFIDENCE_ZH))}</b></div>"
        f"<h3>{html.escape(node_by_id[candidate.node_id].label if candidate.node_id in node_by_id else candidate.node_id)}</h3>"
        f"<p>{html.escape(candidate.thesis)}</p>"
        f"<small>{'风险' if chinese else 'Risks'} · {html.escape(' / '.join(candidate.risks) or ('未提供' if chinese else 'not supplied'))}</small>"
        "</article>"
        for candidate in run.candidates
    ) or ("<p>未生成候选对象。</p>" if chinese else "<p>No candidates were produced.</p>")

    source_items = "".join(
        "<li>"
        f"<span>{html.escape(localized(item.status.value, STATUS_ZH))}</span>"
        f"<strong>{html.escape(item.title)}</strong>"
        f"<small>{html.escape(str(item.source_url or ('无链接' if chinese else 'No URL')))}</small>"
        "</li>"
        for item in run.evidence
    ) or ("<li>未生成证据条目。</li>" if chinese else "<li>No evidence items were produced.</li>")

    limitations = "".join(
        f"<li>{html.escape(str(item))}</li>" for item in decision.get("limitations", [])
    ) or (
        "<li>暂无结构化局限性说明。</li>"
        if chinese
        else "<li>No structured limitations artifact was available.</li>"
    )
    next_actions = "".join(
        f"<li>{html.escape(str(item))}</li>" for item in decision.get("next_actions", [])
    ) or (
        "<li>复核关系图和证据台账。</li>"
        if chinese
        else "<li>Review the graph and evidence ledger.</li>"
    )
    if financial_metrics:
        financial_note = (
            f"{len(financial_metrics)}项有来源关联的财务指标"
            if chinese
            else f"{len(financial_metrics)} source-linked financial metrics"
        )
    elif financials:
        count = len(financials.get("comparisons", []))
        financial_note = (
            f"{count}项有来源关联的财务比较"
            if chinese
            else f"{count} source-linked comparisons"
        )
    else:
        financial_note = (
            "本模式暂无结构化财务比较"
            if chinese
            else "No structured financial comparison for this mode"
        )
    metric_rows = "".join(
        "<tr>"
        f"<td>{html.escape(str(item.get('ticker', '')))}</td>"
        f"<td>{html.escape(METRIC_ZH.get(str(item.get('metric', '')), str(item.get('metric', ''))) if chinese else str(item.get('metric', '')))}</td>"
        f"<td>{html.escape(str(item.get('period_end', '')))}</td>"
        f"<td>{html.escape(metric_value(item.get('value', '')))}</td>"
        f"<td>{html.escape(localized(str(item.get('unit', '')), UNIT_ZH))}</td>"
        f"<td>{html.escape(str(item.get('source_evidence_id') or '—'))}</td>"
        "</tr>"
        for item in financial_metrics
    )
    financial_section = (
        "<section><h2>04 / 财务与经营指标</h2>"
        "<table><thead><tr><th>标的</th><th>指标</th><th>报告期</th><th>数值</th>"
        f"<th>单位</th><th>证据ID</th></tr></thead><tbody>{metric_rows}</tbody></table></section>"
        if chinese and metric_rows
        else (
            "<section><h2>04 / Financial and operating metrics</h2>"
            "<table><thead><tr><th>Ticker</th><th>Metric</th><th>Period</th><th>Value</th>"
            f"<th>Unit</th><th>Evidence ID</th></tr></thead><tbody>{metric_rows}</tbody></table></section>"
            if metric_rows
            else ""
        )
    )

    lang = "zh-CN" if chinese else "en"
    mode_label = "主题扫描" if chinese and run.mode.value == "theme" else (
        "锚点扫描" if chinese and run.mode.value == "anchor" else f"{run.mode.value} scan"
    )
    summary_fallback = "暂无结构化结论。" if chinese else "Structured decision not available."
    disclaimer_fallback = (
        "仅供研究和教育，不构成投资建议。"
        if chinese
        else "Research and education only; not investment advice."
    )

    document = f"""<!doctype html>
<html lang="{lang}">
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
  <header><div><div class="kicker">CapexGraph / {html.escape(mode_label)}</div><h1>{html.escape(run.subject)}</h1></div><div class="meta">{'运行' if chinese else 'RUN'} {html.escape(run.id)}<br>{'研究日期' if chinese else 'AS OF'} {run.as_of_date}<br>{'状态' if chinese else 'STATUS'} {html.escape(localized(run.status.value, STATUS_ZH))}</div></header>
  <div class="summary"><p>{html.escape(decision.get('summary', summary_fallback))}</p><ul><li>{len(run.nodes)} {'个节点' if chinese else 'nodes'} / {len(run.edges)} {'条关系' if chinese else 'edges'}</li><li>{len(run.evidence)} {'项证据' if chinese else 'evidence items'}</li><li>{len(run.candidates)} {'个研究对象' if chinese else 'candidates'}</li><li>{html.escape(financial_note)}</li></ul></div>
  <section><h2>01 / {'有证据支撑的关系图' if chinese else 'Grounded relationship map'}</h2><table><thead><tr><th>{'来源节点' if chinese else 'Source'}</th><th>{'关系' if chinese else 'Relation'}</th><th>{'目标节点' if chinese else 'Target'}</th><th>{'产品或能力' if chinese else 'Product'}</th><th>{'置信度' if chinese else 'Confidence'}</th><th>{'证据数' if chinese else 'Sources'}</th></tr></thead><tbody>{edge_rows}</tbody></table></section>
  <section><h2>02 / {'研究队列' if chinese else 'Research queue'}</h2><div class="candidates">{candidate_cards}</div></section>
  <section><h2>03 / {'证据台账' if chinese else 'Evidence ledger'}</h2><ul class="sources">{source_items}</ul></section>
  {financial_section}
  <section class="actions"><div><h2>{'局限性' if chinese else 'Limitations'}</h2><ul>{limitations}</ul></div><div><h2>{'下一步行动' if chinese else 'Next actions'}</h2><ol>{next_actions}</ol></div></section>
  <footer>{html.escape(decision.get('disclaimer', disclaimer_fallback))}</footer>
</main></body></html>"""
    destination = output_path or (runs_dir() / run_id / "report.html")
    atomic_write_text(destination.resolve(), document)
    return destination.resolve()
