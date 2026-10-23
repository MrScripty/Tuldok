"""Rheon whole-sequence facade over shared immutable asset publication."""
from access import authorized
from immutable_assets import ImmutableAssets, MAX_SELECTED_ASSET_BYTES, migrate_records

MAX_SELECTED_SEQUENCE_BYTES = MAX_SELECTED_ASSET_BYTES
MAX_BUNDLE_BYTES = 65536 + 2097152 + 1024


class SequenceAssets(ImmutableAssets):
    @staticmethod
    def validate_project_acquisition(value, metadata):
        from sequence_batch_import import FORMAT, MAX_ITEMS, marker, label
        from workbench import WorkbenchError
        fields={'format','request_id','batch_name','item_name','item_index','run_sha256','frames_sha256'}
        if type(value) is not dict or set(value)!=fields or value['format']!=FORMAT:
            raise WorkbenchError('Unsupported retained sequence acquisition fields.','unsupported',409)
        marker(value['request_id']);label(value['batch_name'],'Batch label');label(value['item_name'],'Trajectory label')
        if type(value['item_index']) is not int or not 1<=value['item_index']<=MAX_ITEMS or value['run_sha256']!=metadata['run_sha256'] or value['frames_sha256']!=metadata['manifest']['frames_sha256']:
            raise WorkbenchError('Retained sequence acquisition differs from its source.')

    @staticmethod
    def prepare_project_files(files):
        """Prepare bounded source files behind the sequence owner's facade."""
        from workbench import WorkbenchError
        import rheon_sequences as source
        if type(files) is not dict or set(files) != {'run.json', 'frames.jsonl'}:
            raise WorkbenchError('Supply exactly run.json and frames.jsonl sequence files.')
        return source.prepare(
            source.decode_file(files['run.json'], source.contract.MANIFEST_LIMIT, 'run.json'),
            source.decode_file(files['frames.jsonl'], source.contract.FRAMES_LIMIT, 'frames.jsonl'))

    def __init__(self, workbench):
        super().__init__(workbench, kind='sequence', task='sequence_transport',
                         maximum=MAX_BUNDLE_BYTES, default_name='Rheon transport sequence')

    @authorized('edit', 'sequence_assets.admit')
    def admit(self, prepared, body, *, acquisition=None):
        metadata = prepared['metadata']
        origin = {'method': 'simulation_import', 'adapter': metadata['adapter'],
            'run_sha256': metadata['run_sha256'], 'frames_sha256': metadata['manifest']['frames_sha256']}
        if acquisition is not None:
            origin['sequence_acquisition'] = acquisition
        return super().admit(prepared, body, origin)

    def validate_project_source(self, bundle, metadata):
        """Retained sequence decoding stays behind this existing owner."""
        import io
        import zipfile
        from workbench import WorkbenchError
        import rheon_sequences
        try:
            with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
                if archive.namelist() != ['run.json', 'frames.jsonl'] or sum(i.file_size for i in archive.infolist()) > MAX_BUNDLE_BYTES:
                    raise ValueError()
                prepared = rheon_sequences.prepare(archive.read('run.json'), archive.read('frames.jsonl'))
            expected = dict(metadata); expected.pop('bundle_bytes', None)
            if prepared['metadata'] != expected:
                raise ValueError()
        except (ValueError, KeyError, zipfile.BadZipFile):
            raise WorkbenchError('Retained sequence metadata differs from its original bundle.') from None

    @staticmethod
    def validate_project_metadata(value):
        import math
        import re
        from immutable_assets import validate_project_metadata_fields
        from workbench import WorkbenchError
        import rheon_sequence_contract as contract
        validate_project_metadata_fields(value,{'adapter','manifest','run_sha256','frame_index','technical_validation','protected_groups','scope'},MAX_BUNDLE_BYTES)
        contract.validate_manifest(value['manifest'])
        if type(value['adapter']) is not dict or type(value['run_sha256']) is not str or not re.fullmatch('[a-f0-9]{64}',value['run_sha256']):raise WorkbenchError('Invalid retained sequence identity.')
        frames=value['frame_index']
        if type(frames) is not list or len(frames)!=9:raise WorkbenchError('Invalid retained sequence frame index.')
        offset=0
        for index,frame in enumerate(frames):
            if type(frame) is not dict or set(frame)!={'frame','time_s','dt_s','carrier_stamp','liquid_stamp','diagnostics','byte_offset','byte_length','sha256'}:raise WorkbenchError('Invalid retained sequence index fields.')
            contract.integer(frame['frame'],index,index,'frame');contract.number(frame['time_s'],'time');contract.number(frame['dt_s'],'interval')
            if type(frame['byte_offset']) is not int or frame['byte_offset']!=offset or type(frame['byte_length']) is not int or not 1<=frame['byte_length']<=contract.LINE_LIMIT or type(frame['sha256']) is not str or not contract.HEX256.fullmatch(frame['sha256']):raise WorkbenchError('Invalid retained sequence byte index.')
            offset+=frame['byte_length']
            for stamp in (frame['carrier_stamp'],frame['liquid_stamp']):
                if type(stamp) is not dict or set(stamp)!={'id','version'} or any(type(n) is not str or not contract.U64.fullmatch(n) or int(n)>=1<<64 for n in stamp.values()):raise WorkbenchError('Invalid retained sequence stage stamp.')
            diagnostics=frame['diagnostics']
            if index==0:
                if diagnostics is not None:raise WorkbenchError('Initial sequence frame cannot have interval diagnostics.')
            else:
                if type(diagnostics) is not dict or set(diagnostics)!=contract.DIAGNOSTICS:raise WorkbenchError('Invalid retained sequence diagnostics.')
                contract.integer(diagnostics['pressure_iterations'],0,10000,'Pressure iterations')
                for name in contract.DIAGNOSTICS-{'pressure_iterations'}:contract.number(diagnostics[name],name)
        if offset!=value['manifest']['frames_bytes']:raise WorkbenchError('Sequence index byte total differs.')
        technical=value['technical_validation']
        if type(technical) is not dict or set(technical)!={'schema','version','frames','accepted_steps','time_s','volume_m3','mass_kg','centroid_x_m','all_frame_volumes_m3','maxima','limitations'}:raise WorkbenchError('Invalid retained sequence validation summary.')
        if technical['schema']!=contract.SCHEMA or type(technical['version']) is not int or technical['version']!=1 or type(technical['frames']) is not int or technical['frames']!=9 or type(technical['accepted_steps']) is not int or technical['accepted_steps']!=8:raise WorkbenchError('Retained sequence summary profile differs.')
        for key in ('time_s','volume_m3','mass_kg','centroid_x_m'):contract.number(technical[key],key)
        if type(technical['all_frame_volumes_m3']) is not list or len(technical['all_frame_volumes_m3'])!=9 or any(type(n) not in (int,float) or not math.isfinite(n) for n in technical['all_frame_volumes_m3']):raise WorkbenchError('Invalid retained sequence volume observations.')
        if type(technical['maxima']) is not dict or set(technical['maxima'])!={'divergence_s_inv','binomial_fraction_error','velocity_error_m_s','first_pressure_error_pa'}:raise WorkbenchError('Invalid retained sequence diagnostics.')
        for number in technical['maxima'].values():contract.number(number,'diagnostic')
