import importlib.util

import pytest

from artcurator.album_map_protocol import Artifact, Root
from artcurator.identity_schema import Provenance


def test_registry_v2_retains_bytes_when_legacy_imported() -> None:
    # Given byte-sensitive v1 registry data and its original provenance.
    assert importlib.util.find_spec("artcurator.album_registry"), "registry adapter missing"
    from artcurator.album_registry import RegistryV2
    payload = ('{ "version":1, "corpus_fingerprint":"' + "a" * 64 +
               '", "events":[], "references":{}, "excluded":[] }').encode()
    provenance = Provenance(corpus_fingerprint="a" * 64, semantic_profile="b" * 64, contents={}, crops={})
    # When parsing the additive projection, then original bytes remain exact.
    registry = RegistryV2(root=Root(library_id="library", revision=0, root_digest="c" * 64),
        original=Artifact.capture(payload, "registry-v1"), provenance=provenance)
    assert bytes.fromhex(registry.original.payload_hex) == payload
    assert registry.legacy().events == []


def test_registry_v2_refuses_materialized_reference_without_event() -> None:
    # Given a v1 projection that disagrees with its empty event chain.
    assert importlib.util.find_spec("artcurator.album_registry"), "registry adapter missing"
    from artcurator.album_registry import RegistryV2
    payload = ('{"version":1,"corpus_fingerprint":"' + "a" * 64 +
        '","events":[],"references":{"f_00000001":"name"},"excluded":[]}').encode()
    # When wrapped as v2, then the original v1 validator still rejects it.
    with pytest.raises(ValueError, match="replay"):
        RegistryV2(root=Root(library_id="library", revision=0, root_digest="c" * 64),
            original=Artifact.capture(payload), provenance=Provenance(corpus_fingerprint="a" * 64,
                semantic_profile="b" * 64, contents={}, crops={}))
