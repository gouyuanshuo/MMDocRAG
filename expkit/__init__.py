"""Experiment infrastructure: paths, result writers, artifact registry, runner.

This package exists because the project's numbers used to live in terminal
scrollback. A table printed to stdout is not a result: it cannot be re-read, it
cannot be diffed against the next run, and the moment the terminal scrolls it is
gone. Everything here serves one rule -- every number a report cites must be
loadable from a file that records how it was produced.

    paths      where artifacts live, and the run directory layout
    results    the writer an experiment uses to emit metrics and per-question rows
    artifacts  the derived-artifact registry (embeddings, indexes, corpora)
    runner     subprocess execution with tee'd logs and honest status
    report     summary.{json,csv,md,html} aggregated FROM metrics, never from prose
    verify     assertions that pin down contested numbers
    apilog     per-request persistence for anything that costs money
"""

__all__ = ["paths", "results", "artifacts", "runner", "report", "verify", "apilog"]
