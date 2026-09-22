# bscheck

A bullshit type checker for Markdown. Jev judges based on some Bullshit rules.
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

Example diagnostic format

```text
pitch.md:3:1: warning BS001: causal claim without mechanism
      certainty: 92.0% (minimum rule support)
      type: analytical / missing-mechanism
    3 | Our platform increases team productivity by 300%.
      | ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
      = Cause and effect connected by assertion.
      help: Explain the steps connecting the cause to the outcome.
```

The seven families follow [Jeff's Bullshit Detectors](https://fffej.substack.com/p/bullshit-detectors). The subtypes below extend that taxonomy into checks against prose. 

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

`--rules` groups the catalogue by family. Text diagnostics and JSON include `category` and `subtype`; these are additive fields in report schema

`--brief` gives a text overview grouped by category and rule, with occurrence counts, certainty ranges, and up to eight distinct starting lines per rule. 
