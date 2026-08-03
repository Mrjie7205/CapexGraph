from __future__ import annotations

from datetime import date

from capexgraph.market import MarketDataProvider, MarketDataService, build_market_provider
from capexgraph.tools.identity import TickerResolver, canonical_ticker
from capexgraph.tracking.models import (
    Scorecard,
    TrackedCandidate,
    TrackingSnapshot,
    TrackingStage,
    TriggerEvent,
)
from capexgraph.tracking.store import TrackingStore
from capexgraph.workflows import load_run


class TrackingService:
    def __init__(self, store: TrackingStore | None = None) -> None:
        self.store = store or TrackingStore()

    @staticmethod
    def _pair_prices(
        ticker: str,
        benchmark_ticker: str,
        provider: MarketDataProvider,
    ) -> tuple[date, float, float]:
        market = MarketDataService(provider=provider)
        primary = market.sync(ticker).bar_set.bars
        benchmark = market.sync(benchmark_ticker).bar_set.bars
        primary_by_date = {bar.date: bar.return_close for bar in primary}
        benchmark_by_date = {bar.date: bar.return_close for bar in benchmark}
        common_dates = sorted(set(primary_by_date) & set(benchmark_by_date))
        if not common_dates:
            raise ValueError("Ticker and benchmark have no common market date")
        as_of = common_dates[-1]
        return as_of, primary_by_date[as_of], benchmark_by_date[as_of]

    def track_run_candidate(
        self,
        run_id: str,
        node_id: str,
        *,
        benchmark_ticker: str = "000300.SH",
        call_date: date | None = None,
        call_price: float | None = None,
        call_benchmark_price: float | None = None,
        provider: MarketDataProvider | None = None,
        capture_live: bool = True,
    ) -> TrackedCandidate:
        run = load_run(run_id)
        if run is None:
            raise KeyError(f"Research run not found: {run_id}")
        candidate = next((item for item in run.candidates if item.node_id == node_id), None)
        node = next((item for item in run.nodes if item.id == node_id), None)
        if candidate is None or node is None:
            raise KeyError(f"Candidate not found in run: {node_id}")
        if not node.ticker:
            raise ValueError("Tracked candidates require a ticker")
        identity = TickerResolver().resolve(node.ticker)
        benchmark = canonical_ticker(benchmark_ticker)
        if (call_price is None) != (call_benchmark_price is None):
            raise ValueError("Candidate and benchmark baseline prices must be supplied together")
        source = "manual"
        if call_price is None and capture_live:
            active_provider = provider or build_market_provider()
            call_date, call_price, call_benchmark_price = self._pair_prices(
                identity.ticker,
                benchmark,
                active_provider,
            )
            source = active_provider.provider_name
        effective_date = call_date or (date.today() if call_price is not None else run.as_of_date)
        tracked = TrackedCandidate(
            id=f"{run.id}:{node.id}",
            run_id=run.id,
            node_id=node.id,
            ticker=identity.ticker,
            label=node.label,
            benchmark_ticker=benchmark,
            call_date=effective_date,
            call_price=call_price,
            call_benchmark_price=call_benchmark_price,
            stage=TrackingStage.WATCH,
            thesis=candidate.thesis,
            invalidation=candidate.invalidation,
            triggers=candidate.triggers,
        )
        stored = self.store.add_candidate(tracked)
        if call_price is not None and call_benchmark_price is not None:
            self.add_snapshot(
                stored.id,
                as_of_date=effective_date,
                price=call_price,
                benchmark_price=call_benchmark_price,
                source=source,
            )
        return stored

    @staticmethod
    def _return_pct(value: float, baseline: float) -> float:
        return round((value / baseline - 1) * 100, 2)

    @staticmethod
    def _compare(value: float, operator: str, threshold: float) -> bool:
        operations = {
            ">": value > threshold,
            ">=": value >= threshold,
            "<": value < threshold,
            "<=": value <= threshold,
            "==": value == threshold,
        }
        return operations[operator]

    def add_snapshot(
        self,
        tracked_id: str,
        *,
        as_of_date: date,
        price: float,
        benchmark_price: float,
        source: str = "manual",
    ) -> TrackingSnapshot:
        tracked = self.store.get_candidate(tracked_id)
        if tracked is None:
            raise KeyError(f"Tracked candidate not found: {tracked_id}")
        if tracked.call_price is None or tracked.call_benchmark_price is None:
            raise ValueError("Tracking baseline is missing")
        return_pct = self._return_pct(price, tracked.call_price)
        benchmark_return = self._return_pct(benchmark_price, tracked.call_benchmark_price)
        snapshot = self.store.save_snapshot(
            TrackingSnapshot(
                tracked_id=tracked.id,
                as_of_date=as_of_date,
                price=price,
                benchmark_price=benchmark_price,
                return_pct=return_pct,
                benchmark_return_pct=benchmark_return,
                alpha_pct=round(return_pct - benchmark_return, 2),
                source=source,
            )
        )
        self._evaluate_triggers(tracked, snapshot)
        return snapshot

    def capture_live_snapshot(
        self,
        tracked_id: str,
        *,
        provider: MarketDataProvider | None = None,
    ) -> TrackingSnapshot:
        tracked = self.store.get_candidate(tracked_id)
        if tracked is None:
            raise KeyError(f"Tracked candidate not found: {tracked_id}")
        active_provider = provider or build_market_provider()
        as_of, price, benchmark_price = self._pair_prices(
            tracked.ticker,
            tracked.benchmark_ticker,
            active_provider,
        )
        return self.add_snapshot(
            tracked.id,
            as_of_date=as_of,
            price=price,
            benchmark_price=benchmark_price,
            source=active_provider.provider_name,
        )

    def _evaluate_triggers(
        self,
        tracked: TrackedCandidate,
        snapshot: TrackingSnapshot,
    ) -> list[TriggerEvent]:
        metrics = {
            "price": snapshot.price,
            "return_pct": snapshot.return_pct,
            "benchmark_return_pct": snapshot.benchmark_return_pct,
            "alpha_pct": snapshot.alpha_pct,
        }
        events: list[TriggerEvent] = []
        for trigger in tracked.triggers:
            value = metrics.get(trigger.metric)
            if value is None or not self._compare(value, trigger.operator, trigger.value):
                continue
            events.append(
                self.store.save_event(
                    TriggerEvent(
                        tracked_id=tracked.id,
                        metric=trigger.metric,
                        operator=trigger.operator,
                        threshold=trigger.value,
                        observed_value=value,
                        note=trigger.note,
                        as_of_date=snapshot.as_of_date,
                    )
                )
            )
        return events

    def scorecard(self, tracked_id: str) -> Scorecard:
        tracked = self.store.get_candidate(tracked_id)
        if tracked is None:
            raise KeyError(f"Tracked candidate not found: {tracked_id}")
        snapshots = self.store.list_snapshots(tracked.id)
        latest = snapshots[-1] if snapshots else None
        end_date = latest.as_of_date if latest else date.today()
        return Scorecard(
            tracked=tracked,
            latest=latest,
            events=self.store.list_events(tracked.id),
            snapshot_count=len(snapshots),
            days_tracked=max(0, (end_date - tracked.call_date).days),
        )

    def scoreboard(self) -> list[Scorecard]:
        return [self.scorecard(item.id) for item in self.store.list_candidates()]

    def stage_board(self) -> dict[str, list[Scorecard]]:
        board = {stage.value: [] for stage in TrackingStage}
        for card in self.scoreboard():
            board[card.tracked.stage.value].append(card)
        return board
