# Product and showcase

Product recommendations and reproducible product-showcase captures.

[All documentation](../README.md) · [Product showcase](../../README.md)

## Guides, decisions and plans

| Document | Scope |
| --- | --- |
| [Mentra: remaining product recommendations](Mentra_Product_Recommendations_2026-10-17.md) | Feature contracts or implementation reference. |
| [Product improvements — 17 October 2026](Product_Improvements_2026-10-17.md) | Feature contracts or implementation reference. |

## Assets and evidence

| Location | Meaning |
| --- | --- |
| `showcase/` | Capture provenance, screenshots recipe and manifest for the current README gallery. |

The screenshot helper is [capture-showcase.mjs](../../frontend/scripts/capture-showcase.mjs). It uses the real local app and a separate synthetic account. It creates records and may call the configured model/file providers; run it deliberately, not as part of routine tests. Capture provenance is recorded in `showcase/capture-manifest.json`.
