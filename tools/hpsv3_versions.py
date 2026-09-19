"""Record all three isolated environments without installing or changing their pins."""
import json
import subprocess

from artcurator import db
from artcurator.config import ROOT
from artcurator.hpsv3_model import PROCESSOR_REVISION, REVISION


def main() -> None:
    versions = {}
    query = ("import importlib.metadata,json,platform; print(json.dumps({'python':platform.python_version(),"
             "'packages':{d.metadata['Name']:d.version for d in importlib.metadata.distributions()}}))")
    for name, directory in (("main", ".venv"), ("qrealign", ".venv-qrealign"), ("hpsv3", ".venv-hpsv3")):
        result = subprocess.run([str(ROOT / directory / "Scripts/python.exe"), "-c", query],
                                check=True, capture_output=True, text=True)
        versions[name] = json.loads(result.stdout)
    versions["hpsv3"].update(checkpoint_revision=REVISION, processor_revision=PROCESSOR_REVISION,
                             precision="8bit", physical_vram_fraction=0.85)
    db.write_json(ROOT / "environment-versions.json", versions)
    print("Recorded main, qrealign, hpsv3 packages and immutable model revisions")


if __name__ == "__main__":
    main()
