## What this changes

<!-- One or two sentences. Link the plan item (PLAN.md #N) or the issue (#N). -->

## How you checked it

<!-- Paste the output of the test run. For a change in matching, thresholds or models: the benchmark before and after. -->

```
pytest -m "not nli"
```

## Checklist

- [ ] Every commit is signed off (`git commit -s`, see CONTRIBUTING).
- [ ] There is a test that fails without this change.
- [ ] The suite passes, and the output is above.
- [ ] Nothing returns a truth percentage, and no artifact is stored or logged.
- [ ] Thresholds and model versions come from `config.toml`, not from code.
- [ ] If I changed the platform, I changed it in both Python (`factiz_site/`) and TypeScript (`site/src/platform/`).
- [ ] No key, no `.env`, nothing from `data/`, no text copied from a newsroom's article.
