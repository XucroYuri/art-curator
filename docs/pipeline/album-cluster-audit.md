# G3 cluster naming — scoped implementation audit

Authority: FR-ALBUM-MAP-004/005, INV-M and VISION-003/005. This supplements,
not rewrites, the G5 audit. Backend-only work; no client or corpus mutation.

## Verdicts

| Requirement | Verdict | Implemented evidence | Qualification still open |
|---|---|---|---|
| MAP-004 | partial | `test_album_clusters.py`: naming/split/merge/outlier/exclusion stage → confirm → identical-request replay → exact before-state inverse; `test_album_cluster_conflicts.py`: conflicting names rejected or explicitly deferred, six namespaces, mutually exclusive marks; `test_album_g3_cli.py`: real subprocess stage/confirm/undo and bad-token refusal | Existing browser producer is not changed/enabled here; incomplete legacy drafts still need explicit parent enrichment. No end-user visual walkthrough, automatic retrieval support integration, or support-retraction cascade qualification. |
| MAP-005 | partial | `test_album_discovery_lineage.py`: 9/10/11 gate, growth/parameter lineage, wrong-crop refusal; `test_album_promotion.py`: one named batch, membership-only batch and inverses, incompatible-profile cost preview, below-gate selection refusal; `test_album_pool_boundaries.py`: exact eight-state default pool, multiple clusters/noise/missing vectors, committed lineage and split analysis; `test_album_vectors.py`: real saved-vector adapter and full-hash wall ordering | Synthetic vectors are not held-out identity/coherence qualification. No scheduled discovery/client execution, measured runtime/re-embedding pricing, or identity precision claim. |

## Batch and lineage contract

- Naming changes only frozen selected subject/image relations. Preview writes
  nothing; explicit fingerprint confirmation publishes source=human, verified
  relations with actor, evidence and the same operation/batch IDs. Siblings and
  unselected members are untouched. No future members inherit the confirmation.
- Split is disjoint subsets plus nonempty remainder. Merge is visual union,
  never entity merge. Both create content/profile/context/lineage-bound snapshots.
  Conflicting labels either block the entire batch or are retained under explicit
  deferral. Outlier/exclusion creates excluded and remainder snapshots, without
  deleting accepted relations or reference support.
- Re-clustering quotes frozen pool membership/profile/parameters and arithmetic
  comparison bounds. Existing saved-vector loader and clustering/representative
  implementations are reused. Full previous proposals supply overlap-derived
  additions/splits/merges; committed membership supplies parent IDs automatically.
- Promotion selects one cluster even in a multi-cluster proposal. Default seed
  gate is ten distinct selected images; manual naming still handles smaller/noise
  sets. Promotion and membership-only re-clustering each have one reversible batch.
- The original journal, plan and discovery artifacts remain inspectable through
  G5 export/history. No migration or competing transaction/undo engine was added.

## Undo proof and retained limitations

The original G5 before-images and after-token + digest ABA check are unchanged.
`test_cluster_operation_replays_and_undoes_when_confirmed` covers all five
cluster actions; `test_discovery_batch_undo_when_membership_or_name_confirmed`
covers re-clustering and promotion. Eligible rows restore exact pre-operation
models; repeating undo returns the same persistent inverse receipt.
`test_partial_undo_preserves_sibling_edit_when_same_image_row_changes` proves
one later sibling edit preserves the entire image and reports exactly that
image as a conflict, while another image is restored. **The single-image-row
limitation remains deliberately unchanged**, not weakened to an unsafe field diff.
Existing G5 tests retain the separate byte-equivalent ABA/restart proof.

No reference membership is added automatically, so G3 creates no new reference
support requiring retraction. Existing independently supported labels remain.
Visual exclusion does not claim identity/reference rejection. Existing G5 global
writer enrollment, publication fault-class, consent-revocation, memory/support
cascade and physical-power-loss limitations remain open.

## Executed verification

Full suite from the project root: `uv run --no-sync python -m pytest -q`:
**537 passed, 0 failures, 1 warning in 302.30 seconds**. The warning is the
existing scikit-learn HDBSCAN `copy` default FutureWarning. The zero-failure
pytest gate is met; this is not blanket AC/product graduation. The skill's
Python no-excuse checker also reported **no violations in all 15 changed Python
files**. No separate package build was run for this Python-only backend change.
LSP diagnostics were attempted but unavailable: basedpyright is not installed
and the recorded prior installation decline was respected. No clean LSP/type
check or universal durability/precision claim is made.

The implementation modules each have one responsibility: command schema, cluster
planning, saved-vector adaptation, discovery, staged publication, or the existing
mapping schema/browser/CLI boundary. Every changed source module is below 200
nonblank/noncomment lines. Typed parsed models cross the new boundaries; no
new `Any`, casts, broad catch, type-ignore or logging framework was introduced.
No one-off generic abstraction or parameter bag was added. G5 transaction logic
was reused rather than rewritten. Behavioral tests assert state/IDs, not prose.

Wire contract: [album-mapping.md](album-mapping.md#browser-import-wire-contract-clilocal-companion-no-http-server).
