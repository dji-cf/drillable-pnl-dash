"""Golden snapshot of the consolidated page: prove a refactor changed nothing.

Two modes, run on either side of an edit:

    .venv\\Scripts\\python.exe tools\\golden_snapshot.py save    # BEFORE the edit
    .venv\\Scripts\\python.exe tools\\golden_snapshot.py check   # after it

``save`` pulls the master frame once (one SSO login), pickles it, and renders
every main-page output from that pickle: the grid at 3 grains x {no comparison,
Budget, prior forecast} x both change modes, plus collapsed-all, the tiles and
the CSV. ``check`` re-renders THE SAME PICKLE with the current code and diffs
byte for byte. Rendering the old pickle rather than a fresh pull is the point:
a source reload in between cannot produce a false failure.

The pickle carries only the lines the pre-edit SQL fetched, so ``check`` also
proves the new code renders the consolidated page without needing anything
it adds. Files live under the OS temp dir, never in the repo.
"""
from __future__ import annotations

import pickle
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import export  # noqa: E402
import table  # noqa: E402
import transforms as tx  # noqa: E402

DIR = Path(tempfile.gettempdir()) / "drillable_pnl_golden"
FRAME = DIR / "master.pkl"
RENDERS = DIR / "renders.pkl"


def render(df) -> dict[str, bytes]:
    """Every consolidated-page output, keyed by a readable name."""
    cube = tx.build_cube(df)
    fcs = tx.forecast_options(cube)
    forecast = fcs[0]
    budget = tx.year_budget(cube, forecast) or ""
    prior = tx.prior_forecast(cube, forecast) or ""
    out: dict[str, bytes] = {}
    for comp in dict.fromkeys(("", budget, prior)):
        for mode in tx.DELTA_MODES:
            tag = f"{comp or 'solo'}/{mode}"
            for grain in tx.GRAINS:
                out[f"grid {grain} {tag}"] = table.build_statement(
                    cube, forecast=forecast, comp=comp, grain=grain,
                    collapsed={s: False for s in tx.SECTIONS_WITH_HEADER},
                    delta_mode=mode,
                ).encode()
            out[f"tiles {tag}"] = table.build_tiles(
                cube, forecast=forecast, comp=comp, delta_mode=mode).encode()
            out[f"csv monthly {tag}"] = export.to_csv(
                cube, forecast=forecast, comp=comp, grain="monthly", delta_mode=mode)
            for label, _payload, fname, mime in export.downloads(
                    cube, forecast=forecast, comp=comp, grain="monthly",
                    delta_mode=mode, pulled_at=None):
                out[f"download name {label} {tag}"] = f"{fname} {mime}".encode()
    out["grid collapsed-all"] = table.build_statement(
        cube, forecast=forecast, comp=prior, grain="quarterly",
        collapsed={s: True for s in tx.SECTIONS_WITH_HEADER},
    ).encode()
    out["grid static toggle"] = table.build_statement(
        cube, forecast=forecast, comp=prior, grain="annual",
        collapsed={}, toggle_enabled=False,
    ).encode()
    return out


def save() -> None:
    import smoke_render  # live fetch, under the deployed app's role

    DIR.mkdir(parents=True, exist_ok=True)
    df = smoke_render.fetch()
    df.to_pickle(FRAME)
    renders = render(df)
    RENDERS.write_bytes(pickle.dumps(renders))
    print(f"saved {len(df):,} rows -> {FRAME}")
    print(f"saved {len(renders)} renders -> {RENDERS}")


def check() -> None:
    import pandas as pd

    df = pd.read_pickle(FRAME)
    want: dict[str, bytes] = pickle.loads(RENDERS.read_bytes())
    got = render(df)
    problems = []
    for name in sorted(set(want) | set(got)):
        a, b = want.get(name), got.get(name)
        if a != b:
            if a is None or b is None:
                problems.append(f"{name}: {'missing now' if b is None else 'new output'}")
                continue
            i = next((k for k, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
            problems.append(f"{name}: differs at byte {i}: "
                            f"{a[max(0, i - 40):i + 60]!r}\n    vs {b[max(0, i - 40):i + 60]!r}")
    print(f"{len(want)} golden renders from {FRAME}")
    if problems:
        print("PROBLEMS:", *problems, sep="\n  ")
        raise SystemExit(1)
    print("GOLDEN MATCH -- byte-identical")


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    {"save": save, "check": check}[sys.argv[1] if len(sys.argv) > 1 else "check"]()
