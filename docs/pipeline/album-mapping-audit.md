# G5 entry audit — 2026-09-21

Authority: accepted ADR-0006 and FR-ALBUM-MAP. This is the **pre-change**
audit of the interrupted implementation, not a graduation receipt. All five
modules were read. The three existing tests are scoped evidence, not proof of
contracts they do not exercise.

| Requirement / AC | Entry verdict | Concrete evidence and gap |
|---|---|---|
| MAP-001 | partial | `test_prepared_mapping_is_hidden_when_reopened` exercises one pending record. Schema has all named fields, eight states and six types, but relation ownership and persisted revision stamping are incomplete; exchange and typed views absent. |
| MAP-002 | missing | No album first-pass policy in the five modules; G4 remains separate. |
| MAP-003 | partial | `test_undo_preserves_aba_when_later_edit_returns_to_same_value` exercises all-conflict row-level ABA and repeat inverse. No disjoint subject undo, support cascade, preview cost or crash matrix. |
| MAP-004 | missing | No browser staging or naming/split/merge service. G3 wall/client is not this task. |
| MAP-005 | missing | No frozen pool, compatible vector preview, reclustering or promotion adapter. |
| MAP-006 | partial | Schema carries notes/hypotheses/review_after/trigger_revisions/archived. No behavioral tests or tray operations; fields alone are not proof. |
| MAP-007 | missing | No mapping-to-move adapter. G6 remains separately authorized; mapping modules contain no source move operation. |
| NFR-MAP-001 | partial | P/C transactions, WAL/FULL, migration 1 checksum, manifest replay, path lock and binding are present. `test_reconcile_refuses_tampered_unchanged_row` covers one divergence. No fault matrix, backup/exchange, global library enrollment, retained external receipt comparison, capacity gate or migration upgrade tests. |
| INV-M | unverifiable | No source writes apparent in these modules; no filesystem-trace fixture executed at entry. |
| VISION-003 | partial | Literal taxonomy present; no complete matrix or additive v2 adapters. |
| VISION-005 | satisfied (dependency policy only) | This audit keeps G3/G4/G6 and G5 qualification open; no graduation asserted. |
| ADR § contract revisions | partial | Only `album-mapping-execution-v1` exists. Label/Registry/consent/negotiation/presentation additive boundaries absent. |
| ADR recovery | partial | Prepared replay hidden and unchanged-row tampering covered; pending before-image/token validation, inverse semantics and evidence completeness need strengthening. |

Final implementation scope, executed evidence and explicit remaining gaps are in
`album-mapping.md` and `specs/evidence/AC-*.json`. A partial AC cannot be promoted
to pass merely because the full project test suite is green.
