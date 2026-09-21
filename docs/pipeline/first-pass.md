# G4 first-pass disposition — backend contract v1

Authority: FR-ALBUM-MAP-002 (policy), MAP-001/003 (existing store and undo),
VISION INV-M, ADR-0005, and the existing G2 mode-negotiation wire contract.
This is a backend/CLI implementation, not a new UI or a semantic precision claim.
G2 receipts remain intent-only and are not rewritten into execution receipts.

## Policy and measured justification

All numbers below are **engineering policy defaults, not calibrated optima**.
Changing configurable thresholds changes the canonical Policy SHA-256 used as
the decider version. Nondefault values require `evaluation_ref` (a predeclared
evaluation digest) and a new exact preview confirmation. The policy never lowers
thresholds to reach a coverage target. No training or reference enrollment occurs.

| Tier / gate | Default | Rationale and consequence |
|---|---|---|
| Candidate enumeration | WD **> .35**, visual cosine **> .35** | Reuses strict v2 enumeration. The historical whole-image audit used **>= .35**, so its counts must not be presented as identical to strict-v2 counts. |
| `auto` similarity | >= max(**.90**, calibration minimum) | Existing .90 fallback and observed anchor calibration near .9484 motivate a conservative floor, not an estimated optimum. A stricter receipt wins. |
| `auto` stable margin | >= max(**.05**, calibration minimum) | Minimum of centroid-winner and same-winner individual-reference margins. The exploratory .00682 anchor margin is not permission to lower the album .05 floor. |
| Model-tail hypothesis | WD >= **.85**, other-canonical margin >= **.20** | Engineering tail/separation rule, never identity authority. Missing compact runner-up contributes an upper bound .35, not zero; the derived margin is labelled `lower`. Lesser enumerated candidates remain reviewable. |
| `review` | Any contradiction, ambiguity, failed auto prerequisite, model-only suggestion, human-first mode | High WD score and margin do not defeat independent reference or human disagreement. No generic blacklist or corpus-name inference. |
| `none` | No actionable valid candidate | 1,285/1,580 (81.33%) lacked a character tag >= .35, and scaffold coverage was 32/43. Unknown is normal; no minimum coverage promise, nearest-name forcing, original-design or non-character inference. Existing pending/unknown/deferred state survives. |
| `audit-5%` overlay | ceil(**.05** × each stratum's distinct image count) | Workload policy, not a statistical accuracy certificate. Tiny nonempty strata get one item; zero gets zero. It does not verify sampled or unsampled identities. |

Auto additionally requires: explicit `auto-first`, valid non-self visual evidence,
two supported competing identities, a unique centroid winner agreeing with the
individual-reference winner, a matching reference-only leave-one-out calibration,
and winning human-support digests resolving to currently committed verified human
relations on the supplied reference images. Invented or removed support cannot
enable auto. The raw evidence/receipt is retained; model confidence never becomes
`verified=true`. Scores retain separate units/profiles and are never fused.

Contradiction is tested **before** reference auto gates: the strongest independent
profile-valid non-self individual reference above cosine .35 can demote model advice
even when it fails .90/.05. Tied leaders containing the model are ambiguous, not
contradictory. `model_demoted`, alternatives, their own scores, and the raw model
input remain inspectable. Existing human relations/exclusions are not overwritten.
The 143-proposal synthetic replay uses WD .97 and runner-up .60 for every row:
all clear .85/.20, but all become review with `model_demoted`.

## Authority, context and manual fallback

Both preview and execution call G2 `current`: sealed measurements, report digest,
snapshot, analysis profile and frozen source hashes are revalidated. Execution holds
the G2 lease through G5 publication, excluding concurrent consent retraction. Missing
or revoked affirmative consent, missing/tampered/stale report, changed source or
out-of-snapshot content refuses the run before mapping mutation. The submitted
before snapshot must equal the live store (except exact committed-operation replay).

* `human-first` / 人审优先: candidates are proposals, never auto assignments.
* `auto-first` / 自动优先: auto is possible only after every independent gate passes.
* `inherit-only` / 仅继承目录: zero AI mapping mutations and no AI audit sampling.
  This endpoint does not materialize the separately human-directed folder collections.

Contextual grouping remains **disabled**: folder names, membership and timestamps
never affect scores or eligibility. Consent alone does not license contextual use.
Consequently G4 creates no contextual index/cache/mapping residue to retract. G2
retraction blocks further runs and replay; it does not silently erase already
committed context-free mappings. Undo those with their explicit batch action.
Existing manual mapping/naming paths remain available without this AI gate.

## JSON contract

Pydantic models are in `src/artcurator/first_pass_schema.py`; use
`Run.model_json_schema()`, `Preview.model_json_schema()` and
`Incident.model_json_schema()` (the latter from `first_pass_audit`) for machine
schemas. Unknown input fields and nonfinite/out-of-range metrics are refused.
This is a local CLI contract, not an HTTP service.

`Run` (`schema_version="album-first-pass-input-v1"`):

* `operation_id`: fresh identifier; one batch per run, reused unchanged for retry.
* `timestamp`: timezone-qualified operational time, pinned for exact preview replay.
* `snapshot_digest`, `profile`: current G2 snapshot and analysis-profile digests.
* `policy`: defaults above, optional stricter settings and predeclared evaluation ref.
* `rows[]`: unique `(image_id, subject_id)` targets. Every row binds the same snapshot
  and profile. `image_id` is a full SHA-256. Subject targets additionally bind the
  committed crop and detection profile; image scope is refused on multi-subject rows.
* Row `valid`, `conflicts[]`, optional `model{entity_id,entity_type,name,score,
  runner_up,profile}`, and `visuals[]{entity_id,entity_type,name,source,
  centroid,individual,reference_images[],reference_crops[],human_support_refs[],
  profile_valid}` retain evidence rather than a producer's claimed auto tier.
* `source` on visual candidates is `memory|anchors`; model-only input stays model.
  Entity types reuse work/artist/original-series/character/ordinary-person/undetermined.
* Optional `calibration{profile,reference_digest,method:"reference-only-leave-one-out",
  min_similarity,min_margin}` must agree with the row's profile/reference digest.
  Missing calibration leaves candidates in review.

`Preview` (`album-first-pass-preview-v1`) contains the original run and G2 consent,
complete `before` snapshot, per-target `outcomes`, `audit`, `summary`, and the exact
G5 `request` with proposed after-images. Compare request rows against `before` for
previous→next states/entities/verification. `summary` provides base-tier counts,
overlapping audit count, reason counts, evidence-basis counts and changed image
count. Tier counts count evaluated targets; audit denominators count distinct images.
The original input, consent, individual evidence, summary and audit selection are
content-addressed G5 artifacts. No external file is moved or rewritten.

`audit` records the literal seed `album-first-pass-v1`, snapshot digest, separate
auto/none denominators and selected IDs. Sort each eligible stratum by ascending
SHA-256 of the UTF-8 string:

```text
album-first-pass-v1\n<snapshot_digest>\n<auto|none>\n<image_full_hash>
```

There is no trailing newline. Break a hash tie by full image hash; select the first
`(n+19)//20`. Duplicates are collapsed. An image with a review target is already
scheduled and excluded from both audit strata; all evaluated targets must be auto,
or all must be eligible-none, respectively. Invalid/unconsented/protected rows are
not eligible-none. Selected records retain base dispositions and add `audit-5%`.

Execution requires the exact `Preview.fingerprint()` and re-derives its contents.
Only the returned existing `album-mapping-execution-v1` receipt means published.
Store P/C preserves before-images, operation IDs, immutable evidence and history.
All new mapping/subject/relation decisions carry source, separate scores, unverified
status, batch/operation, policy decider/version, timestamps and evidence references.
No sibling face or automatic reference support is created.

## CLI

```powershell
.venv\Scripts\python.exe -m artcurator.cli album-map --album-db out\album.sqlite --album-op first-pass-preview --first-pass-root out\ingest\demo --album-file run.json
.venv\Scripts\python.exe -m artcurator.cli album-map --album-db out\album.sqlite --album-op first-pass-execute --first-pass-root out\ingest\demo --album-file preview.json --album-authorize <preview-fingerprint>
.venv\Scripts\python.exe -m artcurator.cli album-map --album-db out\album.sqlite --album-op undo --album-batch <operation-id>
.venv\Scripts\python.exe -m artcurator.cli album-map --album-db out\album.sqlite --album-op first-pass-audit-error --album-file incident.json
```

Capture the preview JSON exactly; do not edit or restamp it during retry. Generic
G5 prepare/publish are low-level store primitives, not substitutes for G4's guarded
execute endpoint. Initialization and destination-path rules remain those of G5.

An audit incident is `{batch_id,image_id,actor,timestamp}`. It durably freezes that
batch, aborts any remaining prepared publication, and returns
`action="review-or-undo-entire-batch"`. Committed publication is atomic, so it has
no partly unpublished tail. The client offers the existing batch undo, not a silent
threshold adjustment. Later human edits cause `partial_undo=true` with conflict IDs;
one inverse restores all other rows, and repeat/restarted undo is idempotent.

## Evidence and deliberately open limits

Receipt: `specs/evidence/AC-FR-ALBUM-MAP-002-01.json`. Synthetic tests cover exact and
just-below thresholds, absent/stale calibration, unsupported and self references,
143 confusable proposals, tied/disagreeing winners, compact runner-up bounds,
multi-face isolation, live consent, real SQLite publication, CLI and partial undo.

* Evidence input is an explicit reviewed adapter boundary. This change does not
  automatically extract every legacy candidate/anchor artifact into `Run`, recompute
  embeddings or independently reproduce a supplied LOO calibration's measurements.
  Producer-declared visual validity/reference-set digests must not be marketed as
  authenticated measurements from arbitrary untrusted clients. End-to-end producer
  enrollment and held-out calibration/precision qualification remain open.
* No legacy `suggested_verified` field is interpreted as human confirmation. Older
  candidates must be adapted as evidence; missing producer tiers grant no auto label.
* G2's existing presentation and scheduler still truthfully describe its own
  intent-only API; G4 is an explicit additive backend endpoint, not an enabled UI
  or an automatically resumed ingest stage. Cost prediction/enforcement is not added.
* G5 undo remains conservatively image-row granular, retaining all later edits to
  that row. Library-global enrollment, physical power-loss and external writer
  qualification remain the existing store's open obligations.
* No real corpus was mutated or re-measured; the 81.33% and 143 counts are supplied
  historical design evidence, not new measured accuracy. No contextual grouping,
  automatic memory enrollment, physical export or UI is enabled here.
