# bscheck

A bullshit type checker for Markdown. Jev supplies atomic judgments; Python supplies the compiler errors and questionable bedside manner.

```sh
uv sync
# Set TYPESAFE_API_KEY in .env (or export it in your shell).
uv run bscheck examples/pitch.md
uv run bscheck examples/pitch.md --brief
uv run bscheck examples/concrete.md --format json
uv run bscheck examples/pitch.md --threshold 0.75
cat proposal.md | uv run bscheck -
uv run bscheck --rules
```

`.env` and `.env.*` are ignored by Git, except the placeholder `.env.example`. Existing environment variables take precedence. Use `--env-file PATH` to load another dotenv file. The CLI reads `.env` in the current working directory, not an ancestor directory.

Example diagnostic format (illustrative, not a fixed model response):

```text
pitch.md:3:1: warning BS001: causal claim without mechanism
      certainty: 92.0% (minimum rule support)
      type: analytical / missing-mechanism
    3 | Our platform increases team productivity by 300%.
      | ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
      = Cause and effect connected by assertion.
      help: Explain the steps connecting the cause to the outcome.
```

The seven families follow [Jeff's Bullshit Detectors](https://fffej.substack.com/p/bullshit-detectors). The subtypes below extend that taxonomy into checks against prose. Each rule has a primary family; one sentence can earn several warnings. BS001–BS005 retain their codes and signal conditions.

| Family | Code | Subtype | Complaint |
| --- | --- | --- | --- |
| Philosophical | BS003 | self-sealing-claim | A claim with no possible losing condition |
| Philosophical | BS006 | decorative-profundity | Depth without an identifiable meaning |
| Linguistic | BS002 | jargon-fog | Terminology doing meaning's job badly |
| Linguistic | BS005 | empty-calories | Prose that can leave without being missed |
| Analytical | BS001 | missing-mechanism | Cause and effect, with the middle missing |
| Analytical | BS004 | unsupported-assertion | Empirical assertion without supplied evidence |
| Analytical | BS007 | orphaned-number | A number missing essential interpretive context |
| Analytical | BS008 | precision-laundering | Conclusions more impressive than their inputs permit |
| Technological | BS009 | technical-costume | Technology names standing in for an explanation |
| Technological | BS010 | solution-in-search-of-problem | Adoption prescribed regardless of need |
| Organizational | BS011 | strategy-shaped-sentence | Direction that cannot guide a decision |
| Organizational | BS012 | decision-first-evidence-later | Research commissioned to agree |
| Social | BS013 | applause-as-evidence | Popularity or repetition offered as proof |
| Social | BS014 | certainty-on-credit | Authority or certainty beyond supplied grounds |
| Professional | BS015 | credit-boomerang | Success claimed, failure assigned elsewhere |
| Professional | BS016 | achievement-shaped-activity | Added value with no identifiable contribution |

`--rules` groups the catalogue by family. Text diagnostics and JSON include `category` and `subtype`; these are additive fields in report schema 1. Subtype names are our implementation, not quotations from the essay. There is no aggregate bullshit score. Decimal places would only encourage it.

`--brief` gives a text overview grouped by category and rule, with occurrence counts, certainty ranges, and up to eight distinct starting lines per rule. Omit it for excerpts and fixes. It performs the same checks and preserves exit codes; it cannot be combined with `--format json`.

Exit codes: **0** means no diagnostics, **1** means warnings found, **2** means input, configuration, or service failure. JSON goes to stdout; errors go to stderr. Reports are only printed after all batches succeed.

## How it works

CommonMark parsing locates prose in paragraphs, list items, and blockquotes. Headings, fenced/indented code, and HTML blocks are skipped. Conservative sentence splitting preserves original line/column ranges (one-based, end exclusive); abbreviations, links, and inline code can keep multiple sentences in one unit. This is a prose linter, not a complete linguistic parser. Markdown extensions such as tables and footnotes are treated as ordinary CommonMark text.

For each unit, 19 independent [Noul questions](https://docs.typesafe.ai/primitives/noul) ask about the original eight signals and eleven additional rhetorical patterns. Requests contain at most 64 questions (currently three prose units), with the entire document as context. A definition, mechanism, or measurement in another paragraph can therefore count. Source text is explicitly treated as data, not instructions; clearly critiqued or illustrative examples are excluded from warnings. The expanded coverage uses more judgments per unit than the original checker.

Python composes those answers: BS001 needs both a causal claim and an absent mechanism; BS003 needs a claim and absent falsifiability; BS004 needs a claim requiring evidence and absent evidence. Every required signal must independently meet `--threshold` (default **0.8**). For negative signals the support is `1 - P(yes)`. Each diagnostic displays **certainty**, the minimum support across its required signals, as a percentage. JSON includes the same `certainty` as a number from 0 to 1, alongside the individual `signal_support` values. For a single-signal rule this is that signal's support; for a composite rule it is the weakest required signal. This is **not** a calculated joint probability. Uncertain signals produce no warning; raw probabilities remain in JSON for inspection and threshold tuning.

The [Python SDK](https://docs.typesafe.ai/sdk/python) handles requests and retries. The default model is pinned to `jev-1.13.0`; use `--model jev-latest` to opt into changing releases. JSON records the actual model version, raw judgments, token usage, and diagnostic spans. A conservative **24,000 UTF-8 byte** document limit keeps request context bounded; larger files must be split explicitly, and nothing is silently truncated.

The Markdown is sent to TypeSafe for analysis. No source text or responses are cached locally. A citation counts as supplied evidence; the checker does not fetch sources or verify their truth. Model judgments can be wrong, and the threshold is a starting point rather than a calibrated guarantee. The jokes are aimed at the prose. Passing is not a truth certificate.

The new checks inspect textual symptoms: they cannot establish indifference to truth, diagnose Dunning–Kruger, inspect an unseen graph, or reconstruct office politics. Precision laundering and asymmetric credit require a visible mismatch in the document. Legitimate technical language, bounded estimates, candid uncertainty, and concrete work without a measured impact are explicitly excluded from the corresponding questions.

## Development

```sh
uv sync --group dev
uv run pytest
uv run ruff check .
```

Tests use a fake typed client and do not spend API credits. To run a real smoke check using `.env`, run either example above. The examples exercise both marketing fog and a concrete mechanism with reported measurements; model outputs are intentionally not hard-coded snapshots.

In the original five-rule live check (before the taxonomy expansion), the pitch produced seven warnings and the concrete example produced none. The self-sealing “failure is success on a higher plane” claim received `P(falsifiable) = 0.24`: it was flagged as word salad but missed BS003 at the default 0.8 threshold (absence support was only 0.76). This is a known semantic miss at that threshold, not a reason to force the model's answer. Inspect JSON judgments or try 0.75 for a more sensitive pass; these two examples are smoke checks, not an accuracy benchmark.

`examples/field-guide.md` pairs each new subtype with a concrete alternative. These are manual semantic evaluation cases, not claims of measured model accuracy.
