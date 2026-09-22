# bscheck

A bullshit type checker for Markdown. Jev supplies atomic judgments; Python supplies the compiler errors and questionable bedside manner.

```sh
uv sync
# Set TYPESAFE_API_KEY in .env (or export it in your shell).
uv run bscheck examples/pitch.md
uv run bscheck examples/concrete.md --format json
uv run bscheck examples/pitch.md --threshold 0.75
cat proposal.md | uv run bscheck -
uv run bscheck --rules
```

`.env` and `.env.*` are ignored by Git, except the placeholder `.env.example`. Existing environment variables take precedence. Use `--env-file PATH` to load another dotenv file. The CLI reads `.env` in the current working directory, not an ancestor directory.

Example diagnostic format (illustrative, not a fixed model response):

```text
pitch.md:3:1: warning BS001: causal claim without mechanism
    3 | Our platform increases team productivity by 300%.
      | ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
      = Causality has entered the chat. The mechanism has not.
      help: Explain the steps connecting the cause to the outcome.
```

| Code | Complaint |
| --- | --- |
| BS001 | Causal claim without an explanatory mechanism |
| BS002 | Jargon substituting for concrete meaning |
| BS003 | Substantive claim with no observable way to disprove it |
| BS004 | Empirical assertion without supplied evidence |
| BS005 | Prose removable without losing useful information |

Exit codes: **0** means no diagnostics, **1** means warnings found, **2** means input, configuration, or service failure. JSON goes to stdout; errors go to stderr. Reports are only printed after all batches succeed.

## How it works

CommonMark parsing locates prose in paragraphs, list items, and blockquotes. Headings, fenced/indented code, and HTML blocks are skipped. Conservative sentence splitting preserves original line/column ranges (one-based, end exclusive); abbreviations, links, and inline code can keep multiple sentences in one unit. This is a prose linter, not a complete linguistic parser. Markdown extensions such as tables and footnotes are treated as ordinary CommonMark text.

For each unit, eight independent [Noul questions](https://docs.typesafe.ai/primitives/noul) ask about claim presence, causation, falsifiability, need for evidence, supplied evidence, mechanism, jargon, and removability. Up to eight units share a request, with the entire document as context. A definition, mechanism, or measurement in another paragraph can therefore count. Source text is explicitly treated as data, not instructions.

Python composes those answers: BS001 needs both a causal claim and an absent mechanism; BS003 needs a claim and absent falsifiability; BS004 needs a claim requiring evidence and absent evidence. Every required signal must independently meet `--threshold` (default **0.8**). For negative signals the support is `1 - P(yes)`. This is **not** a calculated joint probability. Uncertain signals produce no warning; raw probabilities remain in JSON for inspection and threshold tuning.

The [Python SDK](https://docs.typesafe.ai/sdk/python) handles requests and retries. The default model is pinned to `jev-1.13.0`; use `--model jev-latest` to opt into changing releases. JSON records the actual model version, raw judgments, token usage, and diagnostic spans. A conservative **24,000 UTF-8 byte** document limit keeps request context bounded; larger files must be split explicitly, and nothing is silently truncated.

The Markdown is sent to TypeSafe for analysis. No source text or responses are cached locally. A citation counts as supplied evidence; the checker does not fetch sources or verify their truth. Model judgments can be wrong, and the threshold is a starting point rather than a calibrated guarantee. The jokes are aimed at the prose. Passing is not a truth certificate.

## Development

```sh
uv sync --group dev
uv run pytest
uv run ruff check .
```

Tests use a fake typed client and do not spend API credits. To run a real smoke check using `.env`, run either example above. The examples exercise both marketing fog and a concrete mechanism with reported measurements; model outputs are intentionally not hard-coded snapshots.

In the initial live check, the pitch produced seven warnings and the concrete example produced none. The self-sealing “failure is success on a higher plane” claim received `P(falsifiable) = 0.24`: it was flagged as word salad but missed BS003 at the default 0.8 threshold (absence support was only 0.76). This is a known semantic miss at that threshold, not a reason to force the model's answer. Inspect JSON judgments or try 0.75 for a more sensitive pass; these two examples are smoke checks, not an accuracy benchmark.
