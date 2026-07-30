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

Or run through either explicit live-model channel:

```powershell
capexgraph anchor "兆易创新" --provider codex_subscription --execute
capexgraph anchor "兆易创新" --provider openai --execute
```

The Codex subscription path requires the official local Codex CLI plus a ChatGPT login; Connection
Center can detect or start that login and choose an account-available model. It does not require an
OpenAI Platform API key. The OpenAI path requires `OPENAI_API_KEY` and
`CAPEXGRAPH_OPENAI_MODEL` and is billed separately. Neither path silently falls back to the other.
Once the first step is attempted, the run is locked to its selected provider and model so resumed
checkpoints cannot drift from their manifest.

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
