"""Author-owned D2 writer for the captured scalar example; stdlib only."""
import hashlib
import json
from pathlib import Path


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()


def digest(value):return hashlib.sha256(canonical(value)).hexdigest()


class Evidence:
    def __init__(self,output,context_raw):
        self.output=Path(output);self.context=json.loads(context_raw)
        if self.context['format']!='extension_evidence_context_v1' or canonical(self.context)!=context_raw:
            raise ValueError('Exact canonical host context is required')
        self.static=self.context['static'];self.policy=self.static['policy']
        self.entries=[];self.observations=[];self.field_groups=[]
        self.write_raw('execution-context.json',context_raw)
        self.write('model-definition.json',self.policy['model_specification'])
        self.write('profile.json',self.static['profile'])
        self.write('output-policy.json',self.policy['output_policy'])
        self.write('probe.json',self.static['probe'])
        self.write('metric-definitions.json',self.policy['metric_definitions'])

    def write_raw(self,name,raw):
        if '/' in name or '\\' in name or name in ('.','..'):raise ValueError('Flat output name required')
        with (self.output/name).open('xb') as handle:handle.write(raw)

    def write(self,name,value):self.write_raw(name,canonical(value)+b'\n')

    def blob(self,name):
        raw=(self.output/name).read_bytes()
        return {'name':name,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),
                'media_type':'application/json' if name.endswith('.json') else 'application/octet-stream'}

    def transform(self,state_name):
        self.write('fitted-transform.json',{'format':'fitted_transform_v1','fit_scope':'train',
            'fit_members':self.policy['fit_members'],'state':self.blob(state_name)})

    def checkpoint(self,point,clocks,weights_name,metrics):
        run_id=self.context['run_id'];transform=self.blob('fitted-transform.json')
        descriptor={'format':'checkpoint_state_v1','run_id':run_id,'model_sha256':self.static['model']['sha256'],
            'weights':self.blob(weights_name),'fitted_transform_sha256':transform['sha256'],'clocks':clocks}
        filename=f'checkpoint-{point}.json';self.write(filename,descriptor);ref=self.blob(filename)
        self.entries.append({'checkpoint':ref,'model_sha256':descriptor['model_sha256'],
            'fitted_transform_sha256':transform['sha256'],'clocks':clocks,'selected':False,'state':'retained'})
        probe=self.blob('probe.json')
        for metric in self.policy['metric_definitions']:
            self.observations.append({'run_id':run_id,'checkpoint_sha256':ref['sha256'],'probe_sha256':probe['sha256'],
                'metric_id':metric['id'],'split':'validation','clocks':clocks,'state':'observed',
                'value':metrics[metric['id']],'sample_count':len(self.static['probe']['members'])})
        bindings={(item['field_id'],item['member_id']):item for item in self.policy['field_outputs'] if item['clock']==point}
        for field in self.policy['fields']:
            cases=[]
            for member in self.static['probe']['members']:
                binding=bindings[field['id'],member['frozen_reference']['member_id']]
                cases.append({'member_ordinal':member['ordinal'],'predicted':self.blob(binding['prediction']),
                    'reference':self.blob(binding['reference']),'mask':None,'geometry_sha256':digest(field['geometry']),
                    'time_units':'not_applicable','gauge_policy_sha256':field['contract']['output']['gauge_policy_sha256']})
            self.field_groups.append({'run_id':run_id,'checkpoint_sha256':ref['sha256'],'probe_sha256':probe['sha256'],'cases':cases})

    def finish(self):
        # Explicit last-checkpoint author policy, no best-quality assertion.
        self.entries[-1]['selected']=True
        self.write('checkpoints.json',{'format':'checkpoint_index_v1','run_id':self.context['run_id'],'entries':self.entries})
        self.write('observations.json',self.observations)
        self.write('field-index.json',self.field_groups)
        self.write('model-evidence.json',{'format':'model_evidence_v1','schema_version':1,
            'producer':{'catalog_id':self.static['catalog_id'],'run_id':self.context['run_id'],
                'material_sha256':self.context['composition']['sha256'],'adapter_sha256':self.policy['adapter_sha256']},
            'task':self.static['task'],'model_sha256':self.static['model']['sha256'],
            'data_sha256':self.static['probe']['data_sha256'],'profile_sha256':digest(self.static['profile']),
            'probe':self.blob('probe.json'),'metric_definitions':self.blob('metric-definitions.json'),
            'checkpoints':self.blob('checkpoints.json'),'observations':[self.blob('observations.json')],
            'field_index':self.blob('field-index.json'),
            'coverage':{'required':self.static['profile']['required_capabilities'],'optional':[],'omitted':[]},
            'inference':{'mode':'eval_no_grad','fitted_transforms':[self.blob('fitted-transform.json')],
                'output_policy_sha256':digest(self.policy['output_policy'])}})
