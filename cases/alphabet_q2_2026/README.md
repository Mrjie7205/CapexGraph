# Alphabet Q2 2026 live acceptance case

This case exercises CapexGraph against a newly released, non-fixture disclosure.

See `ACCEPTANCE_REPORT.md` for the first live baseline, observed defects, and research outcome.

Subject:

```text
Alphabet Q2 2026 AI CapEx Transmission
```

The evidence pack contains only first-party Alphabet/Google materials. The normalized financial
facts are transcribed from those materials and retain an evidence ID. The case is intended to test:

- public PDF/HTML capture, hashing, and review;
- period-, unit-, and evidence-linked financial facts;
- separation of operating results from the large equity-securities gain;
- Theme Scan mapping from AI infrastructure demand to bottleneck layers without inventing named
  suppliers; and
- honest failure states for missing provider configuration and unimplemented Catalyst Scan.

Create the live run:

```powershell
$subject = "Alphabet Q2 2026 AI CapEx Transmission"
capexgraph theme $subject --market US --as-of 2026-07-22
capexgraph evidence pack <run-id> .\cases\alphabet_q2_2026\evidence_pack.json
capexgraph evidence review <run-id> alphabet-q2-2026-earnings-release
capexgraph evidence review <run-id> alphabet-q2-2026-ceo-remarks
capexgraph financials import <run-id> .\cases\alphabet_q2_2026\financial_metrics.csv
```

Run the no-key, deterministic replay:

```powershell
capexgraph demo-alphabet-q2
```

Running Theme Scan still requires an explicit structured-output provider. The current OpenAI
provider requires `OPENAI_API_KEY` and `CAPEXGRAPH_MODEL`; it does not discover sources itself.
This acceptance case must not be advertised as a completed model-generated report when those
requirements are absent.
