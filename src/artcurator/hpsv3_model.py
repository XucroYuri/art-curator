"""Pinned HPSv3 wheel architecture and checkpoint; empty image-specific prompt."""
from __future__ import annotations

from pathlib import Path
from typing import Final, Literal
import json

import numpy as np
from PIL import Image

from .models import Predictor

REVISION: Final = "4f81e3e09edd82fe3c5f636444c721b592a735ca"
PROCESSOR_REVISION: Final = "eed13092ef92e448dd6875b2a00151bd3f7db0ac"
Precision = Literal["bf16", "8bit", "4bit", "cpu"]


def sharded_checkpoint(checkpoint: str) -> str:
    """Losslessly shard the official archive to bound quantization staging memory."""
    from safetensors import safe_open
    from safetensors.torch import save_file

    directory = Path(checkpoint).parent / "artcurator-sharded"
    index = directory / "model.safetensors.index.json"
    if index.exists():
        return str(index)
    directory.mkdir(exist_ok=True)
    mapping = {}
    with safe_open(checkpoint, framework="pt", device="cpu") as weights:
        shard = {}
        size = 0
        number = 0
        for key in weights.keys():
            tensor = weights.get_tensor(key)
            shard[key] = tensor
            size += tensor.numel() * tensor.element_size()
            if size >= 256 * 1024 * 1024:
                name = f"part-{number:04d}.safetensors"
                save_file(shard, str(directory / name), metadata={"format": "pt"})
                mapping.update(dict.fromkeys(shard, name))
                shard = {}
                size = 0
                number += 1
        if shard:
            name = f"part-{number:04d}.safetensors"
            save_file(shard, str(directory / name), metadata={"format": "pt"})
            mapping.update(dict.fromkeys(shard, name))
    temporary = index.with_suffix(".tmp")
    temporary.write_text(json.dumps({"metadata": {}, "weight_map": mapping}), encoding="utf-8")
    temporary.replace(index)
    return str(index)


def load(precision: Precision) -> Predictor:
    """Load the complete reward checkpoint directly, avoiding duplicate base weights."""
    import torch
    from accelerate import init_empty_weights, load_checkpoint_and_dispatch
    from accelerate.utils import BnbQuantizationConfig
    from accelerate.utils.bnb import load_and_quantize_model
    from hpsv3 import HPSv3RewardInferencer
    from hpsv3.model.qwen2vl_trainer import Qwen2VLRewardModelBT
    from huggingface_hub import hf_hub_download
    from safetensors import safe_open
    from transformers import AutoConfig, AutoProcessor

    repo = "Qwen/Qwen2-VL-7B-Instruct"
    processor = AutoProcessor.from_pretrained(repo, revision=PROCESSOR_REVISION, padding_side="right")
    processor.tokenizer.add_special_tokens({"additional_special_tokens": ["<|Reward|>"]})
    config = AutoConfig.from_pretrained(repo, revision=PROCESSOR_REVISION)
    config.vocab_size = len(processor.tokenizer)
    config.pad_token_id = processor.tokenizer.pad_token_id
    config.use_cache = False
    config._attn_implementation = "sdpa"
    with init_empty_weights():
        model = Qwen2VLRewardModelBT(config, output_dim=2, reward_token="special",
                                   special_token_ids=processor.tokenizer.convert_tokens_to_ids(["<|Reward|>"]),
                                   rm_head_type="ranknet")
    checkpoint = hf_hub_download("MizzenAI/HPSv3", "HPSv3.safetensors", revision=REVISION)
    with safe_open(checkpoint, framework="pt") as weights:
        if set(weights.keys()) != set(model.state_dict()):
            raise RuntimeError("HPSv3 checkpoint keys do not match the official reward architecture")
    checkpoint = sharded_checkpoint(checkpoint)
    device = "cpu" if precision == "cpu" else "cuda:0"
    if device != "cpu":
        from .resources import Budgets
        free, total = torch.cuda.mem_get_info(0)
        cap = Budgets.choose(1, 1, 1, [(total, free)]).gpu_bytes[0]
        torch.cuda.set_per_process_memory_fraction(cap / total, 0)
    match precision:
        case "bf16" | "cpu":
            model = load_checkpoint_and_dispatch(model, checkpoint, device_map={"": device},
                                                 dtype=torch.bfloat16, strict=True)
        case "8bit" | "4bit":
            quantization = BnbQuantizationConfig(
                load_in_8bit=precision == "8bit", load_in_4bit=precision == "4bit",
                bnb_4bit_quant_type="nf4", bnb_4bit_compute_dtype=torch.bfloat16,
                torch_dtype=torch.bfloat16, skip_modules=["lm_head", "visual"],
                keep_in_fp32_modules=["rm_head"],
            )
            model = load_and_quantize_model(model, quantization, weights_location=checkpoint,
                                           device_map={"": device})
    model.rm_head.float()

    def head_input(module: torch.nn.Module, args: tuple[torch.Tensor, ...]) -> tuple[torch.Tensor, ...]:
        # The wheel requests unsupported CUDA float32 autocast; explicitly cast at the FP32 head boundary.
        return (args[0].float(),)

    model.rm_head.register_forward_pre_hook(head_input)
    model.eval()
    # Reuse the wheel's exact preprocessing/reward API without its unpinned base-model loader.
    inferencer = HPSv3RewardInferencer.__new__(HPSv3RewardInferencer)
    inferencer.model = model
    inferencer.processor = processor
    inferencer.device = device
    inferencer.use_special_tokens = True

    def predict(images: list[Image.Image]) -> np.ndarray:
        with torch.inference_mode():
            raw = inferencer.reward(image_paths=images, prompts=[""] * len(images)).float()
            # Upstream uncertainty loss defines sigma = exp(raw head channel 1).
            values = torch.stack((raw[:, 0], raw[:, 1].exp()), dim=1)
            return values.cpu().numpy()

    return Predictor("MizzenAI/HPSv3", REVISION + "+processor:" + PROCESSOR_REVISION,
                     f"pixels-v1-hpsv3-1.0.0-tf4.45.2-empty-prompt-official-200704-sdpa-{precision}-fp32head-exp-sigma",
                     predict)
