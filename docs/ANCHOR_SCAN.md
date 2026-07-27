# Anchor Scan

Anchor Scan starts from a company that the market has already repriced and asks a stricter
question: which disclosed operating drivers and adjacent companies deserve the next research
hour?

The workflow is:

1. resolve the anchor identity and product boundary;
2. separate disclosed operating drivers from market inference;
3. map direct neighbours and product peers;
4. audit every relationship edge;
5. compare source-linked financial facts while preserving missing data;
6. run a symmetric bull/bear review; and
7. issue a research-priority decision for human review.

Run the no-key golden case:

```powershell
capexgraph demo-anchor
```

Or run the OpenAI-backed workflow after installing the optional dependency and configuring
`OPENAI_API_KEY`:

```powershell
capexgraph anchor "兆易创新" --provider openai --execute
```

The golden case intentionally uses only peer relationships. Product overlap is not converted
into a customer, supplier, or beneficiary claim. Outputs are written as `graph.json`,
`evidence.json`, `financials.json`, `candidates.json`, and `decision.json` under the run folder.

For live runs, captured/reviewed source text and versioned filing facts are injected into every
uncompleted stage through the same bounded context used by Theme Scan. Existing captured evidence
is preserved when a model proposes the same stable identity; its hash and human-review status are
not replaced by a model excerpt. Partial mode downgrades unsupported relationships. Strict mode
checkpoints missing review or unsupported medium/high relationship claims and can resume after the
evidence ledger is corrected.

This workflow produces research priorities, not a buy list or investment recommendation.
