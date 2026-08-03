from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from capexgraph.domain import (
    LiveDeskSettings,
    LiveRuleAssessment,
    LiveSignalCategory,
    LiveSignalVersion,
    SignalObservation,
)

RULESET_VERSION = "live-rules-v1"
DEFAULT_THEME_KEYWORDS: dict[str, list[str]] = {
    "半导体": ["半导体", "芯片", "晶圆", "光刻", "封装", "semiconductor", "chip"],
    "存储": ["存储", "内存", "dram", "nand", "hbm", "memory"],
    "资本开支": ["资本开支", "扩产", "产能", "capex", "capacity"],
    "宏观流动性": ["美联储", "通胀", "非农", "利率", "fed", "inflation", "rate"],
}
_URGENT = (
    "突发",
    "紧急",
    "上调",
    "下调",
    "暂停",
    "制裁",
    "禁令",
    "爆炸",
    "停产",
    "超预期",
    "不及预期",
    "breaking",
    "halt",
    "sanction",
    "guidance",
)
_INJECTION_PATTERNS: dict[str, tuple[str, ...]] = {
    "instruction_override": (
        "ignore previous",
        "ignore all",
        "忽略之前",
        "忽略上述",
        "system prompt",
    ),
    "credential_request": (
        "api key",
        "secret key",
        "password",
        "token",
        "密钥",
        "密码",
    ),
    "tool_instruction": (
        "call tool",
        "execute command",
        "运行命令",
        "调用工具",
    ),
}


def _contains(text: str, keyword: str) -> bool:
    return keyword.casefold() in text.casefold()


def _number(value: object) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


class LiveRuleEngine:
    """Fast deterministic gate before any optional model call."""

    def __init__(
        self,
        settings: LiveDeskSettings | None = None,
        *,
        graph_nodes: dict[str, list[str]] | None = None,
    ) -> None:
        self.settings = settings or LiveDeskSettings()
        self.graph_nodes = graph_nodes or {}

    @property
    def ruleset_hash(self) -> str:
        payload = {
            "version": RULESET_VERSION,
            "threshold": self.settings.alert_score_threshold,
            "include": self.settings.include_keywords,
            "exclude": self.settings.exclude_keywords,
            "entities": self.settings.entity_aliases,
            "graph_nodes": self.graph_nodes,
            "themes": self._themes(),
            "urgent": _URGENT,
            "injection": _INJECTION_PATTERNS,
        }
        return hashlib.sha256(
            json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()

    def _themes(self) -> dict[str, list[str]]:
        return {
            **DEFAULT_THEME_KEYWORDS,
            **self.settings.theme_keywords,
        }

    def assess(
        self,
        signal: LiveSignalVersion,
        observations: list[SignalObservation],
        *,
        now: datetime | None = None,
    ) -> LiveRuleAssessment:
        created_at = (now or datetime.now(UTC)).astimezone(UTC)
        text = " ".join(
            [
                signal.title,
                *(item.title for item in observations),
                *(item.content for item in observations if item.content),
            ]
        )
        excluded = [
            item for item in self.settings.exclude_keywords if _contains(text, item)
        ]
        included = [
            item for item in self.settings.include_keywords if _contains(text, item)
        ]
        themes = sorted(
            name
            for name, keywords in self._themes().items()
            if any(_contains(text, item) for item in keywords)
        )
        entities = sorted(
            name
            for name, aliases in self.settings.entity_aliases.items()
            if _contains(text, name)
            or any(_contains(text, alias) for alias in aliases)
        )
        graph_nodes = sorted(
            node_id
            for node_id, aliases in self.graph_nodes.items()
            if any(_contains(text, alias) for alias in aliases if alias)
        )
        category_base = {
            LiveSignalCategory.FLASH: 32,
            LiveSignalCategory.CALENDAR: 28,
            LiveSignalCategory.NEWS: 26,
            LiveSignalCategory.QUOTE: 8,
            LiveSignalCategory.OTHER: 15,
        }[signal.category]
        relevance = min(
            100.0,
            category_base
            + min(36, len(themes) * 18)
            + min(24, len(entities) * 12)
            + min(18, len(graph_nodes) * 9)
            + min(30, len(included) * 15),
        )
        if self.settings.include_keywords and not included and not themes and not entities:
            relevance = min(relevance, 22)
        if excluded:
            relevance = 0
        urgent_matches = [item for item in _URGENT if _contains(text, item)]
        urgency = min(100.0, 18 + len(urgent_matches) * 22)
        important_values = [
            _number(item.metadata.get("important")) for item in observations
        ]
        star_values = [
            _number(item.metadata.get("star")) for item in observations
        ]
        importance = min(
            100.0,
            20
            + (45 if max(important_values, default=0) > 0 else 0)
            + min(35, max(star_values, default=0) * 7),
        )
        novelty = (
            1.0
            if signal.version == 1
            else 0.65
            if signal.revision_reason == "channel_observation_added"
            else 0.45
        )
        injection_flags = sorted(
            name
            for name, patterns in _INJECTION_PATTERNS.items()
            if any(_contains(text, pattern) for pattern in patterns)
        )
        total = round(
            relevance * 0.36
            + urgency * 0.22
            + importance * 0.22
            + novelty * 100 * 0.20,
            2,
        )
        should_alert = (
            not excluded
            and signal.category != LiveSignalCategory.QUOTE
            and total >= self.settings.alert_score_threshold
        )
        rationale = [
            f"relevance={relevance:.0f}",
            f"urgency={urgency:.0f}",
            f"importance={importance:.0f}",
            f"novelty={novelty:.2f}",
        ]
        if themes:
            rationale.append(f"themes={','.join(themes)}")
        if entities:
            rationale.append(f"entities={','.join(entities)}")
        if graph_nodes:
            rationale.append(f"graph_nodes={','.join(graph_nodes)}")
        if excluded:
            rationale.append(f"excluded={','.join(excluded)}")
        if injection_flags:
            rationale.append("untrusted-content flags require model isolation")
        assessment_id = hashlib.sha256(
            f"{signal.id}:{self.ruleset_hash}".encode()
        ).hexdigest()[:24]
        return LiveRuleAssessment(
            id=f"live-rule-{assessment_id}",
            signal_version_id=signal.id,
            signal_key=signal.signal_key,
            ruleset_version=RULESET_VERSION,
            ruleset_hash=self.ruleset_hash,
            relevance=relevance,
            urgency=urgency,
            novelty=novelty,
            importance=importance,
            total_score=total,
            matched_entities=entities,
            matched_themes=themes,
            matched_graph_nodes=graph_nodes,
            injection_flags=injection_flags,
            should_alert=should_alert,
            rationale=rationale,
            created_at=created_at,
        )
