# Third-party licenses and model terms

Art Curator's original source is **AGPL-3.0-only**. That license does not relicense
dependencies, pretrained weights, training datasets, or images you process.
No third-party packages or model weights are vendored in this repository.
This is a direct-dependency notice, not an exhaustive transitive SBOM or legal advice.
Inspect the exact installed release and selected model revision before redistribution.

## Important restrictions

- **pyiqa / IQA-PyTorch: PolyForm Noncommercial 1.0.0**, with applicable upstream
  notices including NTU S-Lab terms. Treat the configured inference stack as
  personal/research/noncommercial use only under upstream terms. It is **not**
  MIT-licensed and the AGPL on this repository does not grant commercial rights
  to pyiqa. Review [upstream LICENSE](https://github.com/chaofengc/IQA-PyTorch/blob/main/LICENSE).
- **aesthetic-predictor-v2-5: AGPL-3.0**. Preserve its copyleft/source obligations;
  see [upstream LICENSE](https://github.com/discus0434/aesthetic-predictor-v2-5/blob/main/LICENSE).
- AGPL and noncommercial restrictions cannot simply be combined into an
  unrestricted redistributable bundle. This source-only repository is **not a
  claim of license compatibility for a bundled inference product**. Obtain
  appropriate permissions or a legal review before distributing such a product.
- **Model weights carry their own licenses**, possibly different from their
  loader code. A model card, data license and code license are not interchangeable.

## Direct dependencies

| Dependency | Upstream license / notice |
|---|---|
| [PyTorch](https://github.com/pytorch/pytorch) | BSD-3-Clause; bundled components have additional notices |
| [torchvision](https://github.com/pytorch/vision) | BSD-3-Clause |
| [Transformers](https://github.com/huggingface/transformers) | Apache-2.0 |
| [Accelerate](https://github.com/huggingface/accelerate) | Apache-2.0 |
| [pyiqa](https://github.com/chaofengc/IQA-PyTorch) | **PolyForm Noncommercial**, see restrictions above |
| [aesthetic-predictor-v2-5](https://github.com/discus0434/aesthetic-predictor-v2-5) | **AGPL-3.0** |
| [ImageHash](https://github.com/JohannesBuchner/imagehash) | BSD-2-Clause |
| [Pillow](https://github.com/python-pillow/Pillow) | HPND / PIL license; bundled codecs have their own notices |
| [NumPy](https://github.com/numpy/numpy) | BSD-3-Clause; bundled numerical libraries have additional notices |
| [PyYAML](https://github.com/yaml/pyyaml) | MIT |
| [Pydantic](https://github.com/pydantic/pydantic) | MIT |
| [ONNX Runtime](https://github.com/microsoft/onnxruntime) | MIT |
| [scikit-learn](https://github.com/scikit-learn/scikit-learn) | BSD-3-Clause; supplies the identity HDBSCAN/DBSCAN implementations |
| [psutil](https://github.com/giampaolo/psutil) | BSD-3-Clause |
| [OpenCV](https://github.com/opencv/opencv) | Apache-2.0 for current code; optional YuNet artifact terms reviewed separately |
| [Hatchling](https://github.com/pypa/hatch) (build) | MIT |
| [pytest](https://github.com/pytest-dev/pytest) (test) | MIT |
| [uv](https://github.com/astral-sh/uv) (tooling) | MIT / Apache-2.0 |

Hugging Face Hub, timm, SciPy, safetensors and other transitive dependencies are
resolved by the installed packages and have their own licenses. In particular,
pyiqa can install pandas transitively even though this project's data handling
does not import pandas. NVIDIA drivers/CUDA components are not covered by this
project's AGPL; applicable NVIDIA terms still apply.

## Model inventory and caveats

| Model / family | Use and licensing action |
|---|---|
| [SigLIP so400m](https://huggingface.co/google/siglip-so400m-patch14-384), optional [base fallback](https://huggingface.co/google/siglip-base-patch16-384) | Embeddings; inspect the model card and license at the recorded revision (cards advertise Apache-2.0) |
| Aesthetic predictor v2.5 head | Quality; follow the predictor's AGPL terms and inspect weight provenance separately |
| TOPIQ-IAA / TOPIQ-NR | Quality via pyiqa; check the checkpoint's terms and upstream notices, not only the Python package metadata |
| [Q-ReAlign-Mini-0.8B](https://huggingface.co/q-future/Q-ReAlign-Mini-0.8B) | Quality; inspect its pinned revision and base-model terms before use or redistribution |
| [Falconsai NSFW image detection](https://huggingface.co/Falconsai/nsfw_image_detection) | Current safety signal; inspect the selected card/license (advertises Apache-2.0). Output is not a safety certificate |
| [WD EVA02 large tagger v3](https://huggingface.co/SmilingWolf/wd-eva02-large-tagger-v3) | Local identity candidates and attributes; revision `b25b82a03f7282e41aa2f257a52c7583b710bd1c`, **Apache-2.0**. Weights are not vendored. This does not license source images or all other WD models. Execution and limitations: [WD memory](docs/pipeline/wd-memory.md) |
| [Anime face detection](https://huggingface.co/deepghs/anime_face_detection) | Identity crop detector, v1.4 n/s at `784dc4c0bb692351ddcdbe6131a050b17d3025d5`; upstream advertises MIT; digests and scope in [identity v2](docs/pipeline/identity-v2.md) |
| [CCIP ONNX](https://huggingface.co/deepghs/ccip_onnx) | Optional, not the default: the pinned card advertises **OpenRAIL**. Exact upstream use restrictions must be assessed and accepted explicitly. Loader/project MIT or AGPL licenses do not remove weight restrictions. Redistribution and intended use need separate review; the card alone does not clear a distribution channel |

No rights to a private corpus or third-party art are granted. Synthetic CSV data
and placeholder-only demo screenshots contain no real corpus imagery. Model bias,
false negatives and false positives remain regardless of licensing status.
