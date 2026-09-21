# Synthetic demo screenshots

`studio.png`, `table.png` and `legend.png` are captured from
`tests/fixtures/gallery/gallery.html` over a loopback-only read-only HTTP server.
All 60 rows contain synthetic metadata and non-existent `/synthetic/` paths.
There are no source images, thumbnails or previews: visible image areas are UI
placeholders. These screenshots must never be replaced with private-corpus views.

`v10-fixture-fit.png` and `v10-fixture-narrow.png` show the ranked face-candidate
popover on the same synthetic fixture (fit 1440px and narrow 520px). Private
corpus captures stay under `out/` and are not repository assets.

`v12-fixture-model.png`, `v12-fixture-demotion.png`, `v12-fixture-768.png` and
`v12-fixture-375.png` show the separate unverified model tier, reference-gated
tier and contradiction demotion. All use the synthetic fixture only. See
[the execution receipt](../model-suggestions.md) for measurements and limitations.

`alias-1280.png`, `alias-768.png`, `alias-375.png`, `alias-confirmed-375.png`,
`alias-rejected-375.png` and `alias-bottom-375.png` show the alias-review dialog,
pending decisions and narrow-screen scroll state. They were captured from
`out/alias-synthetic/gallery.html`, built by `tools/build_alias_demo.py`, using
synthetic evidence and placeholders only. No private corpus images appear here.
Private gallery captures remain under `out/`. See the
[alias execution receipt](../alias-reconciliation.md).
