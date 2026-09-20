"""Pinned pixel-only CPU detector adapters; no silent provider/model substitution."""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final, assert_never

import numpy as np
from PIL import Image

from .identity_schema import BBox, DetectorInfo, IdentityOptions
from .identity_store import file_digest

ANIME_REVISION: Final = "784dc4c0bb692351ddcdbe6131a050b17d3025d5"
ANIME_HASHES: Final = {
    "n": "fd860b650a4377046842c3cd80d01b0b408bdfbdb4acee5759630f82c6ef04a9",
    "s": "403b5bc93b6ff789b7d183418df4a1364049bac00c24acd927604a7ff6891483",
}


@dataclass(frozen=True, slots=True)
class Detection:
    bbox: BBox
    score: float


@dataclass(frozen=True, slots=True)
class Detector:
    info: DetectorInfo
    artifact_sha256: str
    predict: Callable[[Image.Image], list[Detection]]


def _boxes(raw: np.ndarray, image: Image.Image, options: IdentityOptions) -> list[Detection]:
    """Class-agnostic NMS on original-image xyxy boxes and scores."""
    order = np.argsort(-raw[:, 4], kind="stable")
    selected: list[Detection] = []
    seen: set[BBox] = set()
    while len(order):
        index, rest = order[0], order[1:]
        x1, y1, x2, y2, score = raw[index]
        x1, y1 = max(0, int(np.floor(x1))), max(0, int(np.floor(y1)))
        x2, y2 = min(image.width, int(np.ceil(x2))), min(image.height, int(np.ceil(y2)))
        box = (x1, y1, x2 - x1, y2 - y1)
        if min(box[2:]) >= options.min_face_px and box not in seen:
            selected.append(Detection(box, float(score)))
            seen.add(box)
        a = raw[index, :4]
        b = raw[rest, :4]
        intersection = np.maximum(0, np.minimum(a[2:], b[:, 2:]) - np.maximum(a[:2], b[:, :2]))
        overlap = intersection[:, 0] * intersection[:, 1]
        area_a = np.prod(np.maximum(0, a[2:] - a[:2]))
        area_b = np.prod(np.maximum(0, b[:, 2:] - b[:, :2]), axis=1)
        iou = overlap / np.maximum(area_a + area_b - overlap, 1e-12)
        order = rest[iou <= options.nms_threshold]
    return sorted(selected, key=lambda d: d.bbox)


def load_detector(options: IdentityOptions) -> Detector:
    from huggingface_hub import HfApi, hf_hub_download
    from pathlib import Path
    match options.detector:
        case "anime_face_detection":
            import onnxruntime as ort
            model = f"face_detect_v1.4_{options.variant}/model.onnx"
            path = Path(hf_hub_download("deepghs/anime_face_detection", model, revision=ANIME_REVISION))
            artifact = file_digest(path)
            if artifact != ANIME_HASHES[options.variant]:
                raise ValueError("anime detector artifact digest mismatch")
            session_options = ort.SessionOptions()
            session_options.intra_op_num_threads = options.threads
            session_options.inter_op_num_threads = 1
            session = ort.InferenceSession(str(path), sess_options=session_options,
                                           providers=["CPUExecutionProvider"])
            if session.get_providers() != ["CPUExecutionProvider"]:
                raise ValueError("unexpected detector execution provider")

            def predict(image: Image.Image) -> list[Detection]:
                with image.resize((640, 640), Image.Resampling.BILINEAR) as resized:
                    tensor = np.asarray(resized, dtype=np.float32).transpose(2, 0, 1)[None] / 255
                output = np.asarray(session.run(["output0"], {"images": tensor})[0])[0].T
                if output.ndim != 2 or output.shape[1] != 5 or not np.isfinite(output).all():
                    raise ValueError("unexpected anime detector output")
                output = output[output[:, 4] >= options.det_threshold].copy()
                centers, sizes = output[:, :2].copy(), output[:, 2:4].copy()
                output[:, :2] = centers - sizes / 2
                output[:, 2:4] = centers + sizes / 2
                output[:, [0, 2]] *= image.width / 640
                output[:, [1, 3]] *= image.height / 640
                return _boxes(output, image, options)

            return Detector(DetectorInfo(name=options.detector, model=model, revision=ANIME_REVISION,
                                         min_face_px=options.min_face_px), artifact, predict)
        case "yunet":
            import cv2
            repo = "opencv/face_detection_yunet"
            revision = HfApi().model_info(repo).sha
            if revision is None:
                raise ValueError("YuNet immutable revision unavailable")
            path = Path(hf_hub_download(repo, "face_detection_yunet_2023mar.onnx", revision=revision))
            detector = cv2.FaceDetectorYN.create(str(path), "", (320, 320), options.det_threshold,
                                                 options.nms_threshold, 5000,
                                                 cv2.dnn.DNN_BACKEND_OPENCV, cv2.dnn.DNN_TARGET_CPU)

            def predict_yunet(image: Image.Image) -> list[Detection]:
                detector.setInputSize(image.size)
                _, found = detector.detect(np.asarray(image)[:, :, ::-1].copy())
                if found is None:
                    return []
                raw = np.column_stack((found[:, :2], found[:, :2] + found[:, 2:4], found[:, -1]))
                return _boxes(raw, image, options)

            return Detector(DetectorInfo(name="yunet", model=repo, revision=revision,
                                         min_face_px=options.min_face_px), file_digest(path), predict_yunet)
        case unreachable:
            assert_never(unreachable)
