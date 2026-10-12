"""Audio targets in canonical_v1 releases; original WAV + typed source-frame JSONL."""
from audio_assets import TASK, validate_annotation
from workbench import WorkbenchError

CONTRACT = 'PCM WAV originals; timed targets are zero-based channel indexes and integer source-frame [start_frame,end_frame) intervals. Seconds are display conversions only. No crop, downmix, resampling, ASR or training qualification.'


def validate_record(record):
    if record['kind'] != 'audio' or record['task'] != TASK or not record['source_available'] or record['review'] != 'human_reviewed':
        raise WorkbenchError('Audio export requires available original WAV and explicit human-reviewed timed annotations.')
    validate_annotation(record['annotation'], record)


def project(record):
    validate_record(record)
    return dict(record, audio_target_schema_version=1, audio_coordinate_contract=CONTRACT)
