"""Actual published Kenoma neutral packet and explicitly authored legacy control."""
import functools
import gzip
import hashlib
import io
import json
from pathlib import Path
import zipfile

from mesh_binary_packet import kenoma_packet, legacy_packet

ROOT=Path(__file__).parent
ARTIFACT_COMMIT='7eec7ef00c005ac3168e51cb93cb4b212fe31e36'
SOURCE_COMMIT='136f4947c7ef9bd2d4fe5cff09086489b0cb501d'


def producer_files():
    root=ROOT/'kenoma_rig_bind_v1';manifest_raw=(root/'manifest.json').read_bytes();manifest=json.loads(manifest_raw)
    request=(root/'request.json').read_bytes();compressed=(root/'response.json.gz').read_bytes()
    assert len(compressed)==1508798==manifest['response']['compressed_bytes']
    assert hashlib.sha256(compressed).hexdigest()=='66fdbca45c1a70a2589ccc5af137af76c2c46443595d1fbe8ba7300a87bb599b'
    with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as stream:
        response=stream.read(8*1024*1024+1);assert len(response)<=8*1024*1024 and stream.read(1)==b''
    assert len(response)==5257666==manifest['response']['bytes']
    assert hashlib.sha256(response).hexdigest()=='034f9f4a27339488e8cea40d00a508f4d02fbfeb5b4a8f5bf59a95c9c6d6a7a0'
    assert len(request)==62 and hashlib.sha256(request).hexdigest()=='25ef5907280cdc35774634a5f62370e091404cbcce503442ab6a2c188e841d91'
    return request,response,manifest_raw


@functools.lru_cache(maxsize=1)
def packets():
    # Authored mixed-type, halfway-neighbor analytic triangle; not producer data.
    from tests.fixtures.native_mesh_fixture import pair
    ply,sidecar=pair();stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w',zipfile.ZIP_STORED) as archive:
        archive.writestr(zipfile.ZipInfo('mesh.ply'),ply);archive.writestr(zipfile.ZipInfo('mesh.json'),sidecar)
    return [('Authored source-bound midpoint mesh',legacy_packet(stream.getvalue())),
        ('Kenoma default neutral bind',kenoma_packet(*producer_files()))]
