"""Rheon whole-sequence facade over shared immutable asset publication."""
from immutable_assets import ImmutableAssets, MAX_SELECTED_ASSET_BYTES, migrate_records

MAX_SELECTED_SEQUENCE_BYTES = MAX_SELECTED_ASSET_BYTES
MAX_BUNDLE_BYTES = 65536 + 2097152 + 1024


class SequenceAssets(ImmutableAssets):
    def __init__(self, workbench):
        super().__init__(workbench, kind='sequence', task='sequence_transport',
                         maximum=MAX_BUNDLE_BYTES, default_name='Rheon transport sequence')

    def admit(self, prepared, body):
        metadata = prepared['metadata']
        return super().admit(prepared, body, {'method': 'simulation_import', 'adapter': metadata['adapter'],
            'run_sha256': metadata['run_sha256'], 'frames_sha256': metadata['manifest']['frames_sha256']})
