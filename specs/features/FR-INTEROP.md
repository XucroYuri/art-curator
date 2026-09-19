> 中文摘要
> 互操作先声明版本和损失，再进行预览与显式导入。
> 外部标签仅用于人类组织，不得成为视觉质量特征。
> 任何交换格式都不能绕过可撤销计划与许可证门禁。

# Interoperability

Status: deferred until curation protocol graduation. Candidate formats: content-bound JSON, CSV, and an explicitly scoped XMP mapping. No Picasa, digiKam, Immich or PhotoPrism compatibility is presently asserted. UX inspiration is not interchange support.

### FR-INTEROP-001 — Loss-aware exchange
When exchanging curation records with a named application/format version, the adapter shall publish a field/loss mapping, preview changes and preserve content binding and decision provenance without granting filesystem action authority.

Scope: S: approved protocol-to-format mappings / E: local import/export / T0–T4. Status: deferred.
- Map identity labels, confirmed versus unconfirmed states, tags, manual decision events and family relationships explicitly. Do not collapse unknown into negative, archive candidate into delete, or model proposal into human approval. Unsupported data stays in the native sidecar or is reported as loss; no silent discard.
- Paths/metadata/tags are organizational fields only under INV-2. Import cannot train weights, change semantic thresholds silently, upload images or execute moves. Original-file metadata writes are excluded from initial exchange scope; sidecar-only export avoids changing source hashes.
- AC-FR-INTEROP-001-01: round-trip PROTOCOL-v1 through each named format/application version; exact preservation for declared lossless fields, all losses/conflicts enumerated and zero implicit mutation/authorization; evidence `evidence/AC-FR-INTEROP-001-01.json`. Target versions and fixture digests TBD.

### FR-INTEROP-002 — Distribution boundary
When packaging an interop adapter or sample artifact, the maintainer shall clear its code, schema, documentation and bundled-model rights independently and ship only synthetic or explicitly licensed examples.

Scope: S: approved mappings / E: distribution bundles / T0–T4. Status: deferred.
- AC-FR-INTEROP-002-01: LICENSE-v1 bundle audit under NFR-GATE-009; zero unknown/incompatible licenses or private corpus paths/images in distributed samples; evidence `evidence/AC-FR-INTEROP-002-01.json`.

Prerequisites: FR-PROTOCOL-001/002, INV-2/3/4, NFR-GATE-008/009. Graduating one mapping never certifies another application version.
