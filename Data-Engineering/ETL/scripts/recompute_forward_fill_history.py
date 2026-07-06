"""One-off maintenance script: recompute the 'forward-filled candlestick' measurement
for every major pair and granularity.

Why this is needed: ForwardFillInator previously had an ordering bug --
account_for_holiday_market_closure() ran BEFORE forward_fill_it() and called a bare
dropna() (no subset=) on the pre-ffill frame, which drops every row with ANY missing
OHLCV value -- i.e. every gap, not just holiday closures. That made forward_fill_it()'s
ffill() a no-op, so whatever wrote the 'forward-filled candlestick' measurement before
this fix may have written data with missing timestamps rather than genuinely filled
ones. Separately, is_forward_filled is a brand new field -- no existing point has it,
regardless of the bug.

InfluxDB overwrites a point when the same measurement + tags + timestamp is written
again, so this does NOT delete anything first for the common case -- it just re-runs
the (now-corrected) pipeline and lets every point get overwritten in place. The one
case this does NOT handle: if the OLD process ever wrote timestamps outside the range
this corrected run reproduces, those stale points would need an explicit delete first.
That's not done here -- if you're not confident the old data's time range matches,
delete the measurement (scoped by tag) yourself before running this, rather than
having this script do it silently.

Usage (from the repo root, with the package installed -- `pip install -e ".[dev]"`):

    cd Data-Science/Data-Engineering/ETL
    python scripts/recompute_forward_fill_history.py

Edit GRANULARITIES / INSTRUMENTS below to scope down a run (e.g. to just the
granularities forex-ML actually trains on, H1 and M15, skipping D).
"""

from __future__ import annotations

from forex.flows.candlestick_flow import MAJOR_PAIRS
from forex.flows.forward_fill_flow import forward_fill_flow

GRANULARITIES = ['D', 'H1', 'M15']
INSTRUMENTS = [pair.replace('_', '/') for pair in MAJOR_PAIRS]


def main() -> int:
    total = len(GRANULARITIES) * len(INSTRUMENTS)
    succeeded: list[tuple[str, str]] = []
    failed: list[tuple[str, str, Exception]] = []

    done = 0
    for granularity in GRANULARITIES:
        for instrument in INSTRUMENTS:
            done += 1
            print(f'[{done}/{total}] {instrument} {granularity} ...', flush=True)
            try:
                forward_fill_flow(instrument=instrument, granularity=granularity)
                succeeded.append((instrument, granularity))
            except Exception as exc:  # noqa: BLE001 -- deliberately broad: one pair's
                                       # failure must not abort the rest of the batch
                print(f'  FAILED: {exc}', flush=True)
                failed.append((instrument, granularity, exc))

    print()
    print(f'{len(succeeded)}/{total} succeeded, {len(failed)}/{total} failed')
    if failed:
        print('\nFailed pairs (re-run just these once you\'ve investigated):')
        for instrument, granularity, exc in failed:
            print(f'  {instrument} {granularity}: {exc}')
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
