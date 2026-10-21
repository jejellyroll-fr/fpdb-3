"""tools/benchmark_import.py runs and reports its phases (#443)."""

from __future__ import annotations

import pytest

from tools import benchmark_import

ONE_FILE = "regression-test-files/cash/Stars/Flop/NLHE-6max-EUR-0.05-0.10-200911.txt"


def test_the_benchmark_imports_and_reports_each_phase(capsys) -> None:
    assert benchmark_import.main(["--files", ONE_FILE]) == 0

    report = capsys.readouterr().out
    assert "1 files," in report
    for phase in ("total", "parse", "derive", "write"):
        assert phase in report


def test_an_empty_corpus_is_refused() -> None:
    with pytest.raises(SystemExit, match="no file matches"):
        benchmark_import.corpus_files(["no/such/*.txt"])


@pytest.mark.perf
def test_equity_workers_make_the_bulk_import_faster() -> None:
    """Advisory: the default corpus with and without workers."""
    files = benchmark_import.corpus_files(benchmark_import.DEFAULT_CORPUS)
    sequential = min(benchmark_import.benchmark(files, 1, workers=1), key=lambda timing: timing.seconds)
    parallel = min(benchmark_import.benchmark(files, 1, workers=4), key=lambda timing: timing.seconds)
    print(f"\nsequential {sequential.hands_per_second:.1f} hands/s, 4 workers {parallel.hands_per_second:.1f} hands/s")

    assert parallel.hands == sequential.hands
    assert parallel.seconds < sequential.seconds
