# Contributing

Open an issue describing the problem and a synthetic reproduction before large changes.
Keep scoring changes separate from UI, packaging, and dependency upgrades. Do not
silently substitute models, preprocessing, precision, or calibrated-sounding claims.

Use Python 3.12. The minimal CI suite needs only pytest:

```sh
uv venv --python 3.12 .venv-ci
uv pip install --python .venv-ci/bin/python pytest==8.4.2
.venv-ci/bin/python -m pytest tests/test_build_gallery.py -q
```

On Windows, use `.venv-ci\Scripts\python.exe`. The wider suite also needs NumPy,
Pillow, ImageHash, PyYAML and Pydantic; GPU inference requires the separate setup
in the README. Tests must use temporary/generated data, never a real library.

Never submit personal configuration, real images, model weights, database files,
generated production galleries, decision journals, absolute personal paths, or
benchmark receipts containing them. Inspect compressed gallery payloads as well as
plain text. Demo screenshots must come only from `tests/fixtures/gallery`.

Include regression tests for behavioral changes. Contributions are licensed under
AGPL-3.0-only; third-party dependencies and model weights retain their own terms.
