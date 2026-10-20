import collections, hashlib, json, math, pathlib, statistics, sys
source=pathlib.Path(sys.argv[1]) if len(sys.argv)>1 else pathlib.Path(__file__).resolve().parent
summary=json.loads((source/'summary.json').read_bytes())

def stats(values):
    values=sorted(values)
    return {'n':len(values),'min':values[0],'median':statistics.median(values),'p90_nearest_rank':values[math.ceil(.9*len(values))-1],'max':values[-1]}

workers=[]; groups=collections.defaultdict(list); arms=collections.defaultdict(list); unavailable=[]
for path in sorted((source/'raw').glob('*-process-*.json')):
    raw=json.loads(path.read_bytes())
    if raw['availability']!='eligible_exact_inventory':
        assert raw['availability']=='no_eligible_target_in_empty_history'
        assert raw['state_before']==raw['state_after']
        assert raw['state_before']['workspace_runs']==0 and raw['pairs']==[]
        unavailable.append(path.name);continue
    assert raw['state_before']==raw['state_after']
    assert raw['whole_artifacts_equal'] and raw['events_unchanged'] and raw['no_replay']
    kind=raw['source']['kind'];number=len(raw['expected_artifacts']);history=raw['state_before']['workspace_runs']
    assert sum(x['bytes'] for x in raw['expected_artifacts'])==327680
    for pair in raw['pairs']:
        assert pair['whole_artifacts_equal']
        assert set(pair['order'])=={'individual','batch'}
        assert pair['batch_over_individual']==pair['batch_wall_ns']/pair['individual_wall_ns']
        condition='first_pair_fresh_process' if pair['cycle']==0 else 'warm_pair_same_process'
        row=dict(pair,raw_file=path.name)
        groups[kind,number,history,condition].append(row)
        groups[kind,number,history,'all_pairs'].append(row)
    for row in raw['rows']:
        if not row['operation'].startswith('collection.'):continue
        assert row['outcome']=='ok'
        arm=row['operation'].rsplit('.',1)[1]
        assert len(row['http'])==(number if arm=='individual' else 1)
        assert all(x['status']==200 for x in row['http'])
        expected=sorted(raw['expected_artifacts'],key=lambda x:x['name'])
        assert sorted(row['detail']['whole_sha256_receipts'],key=lambda x:x['name'])==expected
        arms[kind,number,history,row['condition'],arm].append(row)
        arms[kind,number,history,'all_pairs',arm].append(row)
    workers.append(path.name)
assert len(workers)==18 and len(unavailable)==6
assert len(summary['pairs'])==54 and len(summary['cleanup'])==2
assert all(x['dropped'] and x['owned_temporary_directory_removed'] for x in summary['cleanup'])
paired=[]
for (kind,number,history,condition), rows in sorted(groups.items()):
    assert len(rows)=={'first_pair_fresh_process':3,'warm_pair_same_process':6,'all_pairs':9}[condition]
    paired.append({'source_kind':kind,'artifacts':number,'total_terminal_history':history,'condition':condition,
        'wall_ratio_batch_over_individual':stats([x['batch_over_individual'] for x in rows]),
        'paired_wall_delta_ms_batch_minus_individual':stats([(x['batch_wall_ns']-x['individual_wall_ns'])/1e6 for x in rows]),
        'batch_faster_pairs':sum(x['batch_wall_ns']<x['individual_wall_ns'] for x in rows),
        'batch_equal_pairs':sum(x['batch_wall_ns']==x['individual_wall_ns'] for x in rows),
        'arm_orders':dict(collections.Counter('/'.join(x['order']) for x in rows)),
        'order_strata':{order:{'wall_ratio_batch_over_individual':stats([x['batch_over_individual'] for x in rows if '/'.join(x['order'])==order]),
            'paired_wall_delta_ms':stats([(x['batch_wall_ns']-x['individual_wall_ns'])/1e6 for x in rows if '/'.join(x['order'])==order])}
            for order in sorted(set('/'.join(x['order']) for x in rows))},
        'raw_files':sorted(set(x['raw_file'] for x in rows))})
arm_groups=[]
for (kind,number,history,condition,arm), rows in sorted(arms.items()):
    counts=sorted(set().union(*(x['counts'] for x in rows)))
    io=sorted(set().union(*(x['proc_io_delta'] for x in rows)))
    resource_io=sorted(set().union(*(x['resource_io_blocks_delta'] for x in rows)))
    owners=sorted(set(x['owner'] for r in rows for x in r['owner_stages']))
    arm_groups.append({'source_kind':kind,'artifacts':number,'total_terminal_history':history,'condition':condition,'arm':arm,
        'wall_ms':stats([x['wall_ns']/1e6 for x in rows]),
        'process_and_waited_children_cpu_ms':stats([sum(x['cpu'].values())*1000 for x in rows]),
        'http_requests':stats([len(x['http']) for x in rows]),
        'http_request_body_bytes':stats([sum(a['request_body_bytes'] for a in x['http']) for x in rows]),
        'http_response_body_bytes':stats([sum(a['response_body_bytes'] for a in x['http']) for x in rows]),
        'rss_after_kib':stats([x['rss']['after_kib'] for x in rows]),
        'lifetime_hwm_after_kib':stats([x['rss']['lifetime_hwm_after_kib'] for x in rows]),
        'proc_io_delta':{key:stats([x['proc_io_delta'].get(key,0) for x in rows]) for key in io},
        'resource_io_blocks_delta':{key:stats([x['resource_io_blocks_delta'].get(key,0) for x in rows]) for key in resource_io},
        'owner_call_counts':{key:stats([x['counts'].get(key,0) for x in rows]) for key in counts},
        'inclusive_owner_wall_ms':{key:stats([sum(a['inclusive_wall_ns'] for a in x['owner_stages'] if a['owner']==key)/1e6 for x in rows]) for key in owners}})
result={'kind':'full_predeclared_matrix_no_filtered_pairs','measured_head':summary['source']['head'],
    'availability':{'eligible_workers':len(workers),'empty_history_unavailable_workers':len(unavailable),'unavailable_files':unavailable},
    'counts':{'eligible_cells':6,'first_pairs':18,'warm_pairs':36,'pairs':54,'collection_arms':108,'artifacts_per_arm':[1,20],'aggregate_raw_bytes_per_arm':327680},
    'invariants':{'whole_hash_and_inventory_equality_all_arms':True,'original_events_and_run_grant_consumption_reservation_counts_unchanged':True,
        'no_child_compute_during_collection':True,'exact_recorded_owned_cleanup_checks':summary['cleanup'],
        'source_and_harness_stable':all(summary['source'][k]==summary['environment_finish'][k] for k in ('head','source_sha256','harness_sha256','paired_harness_sha256'))},
    'paired_distributions':paired,'arm_resource_distributions':arm_groups,
    'limits':summary['limits']+['Original production_base field records branch admission ancestry2d8b7d7; actual measured source is composed9838022 with exact source_sha256.',
        'All known heavy gates reported complete before this coordinated window; small pure checks were permitted and no exclusive-host claim is made. Per-arm UTC starts were not recorded.',
        'No confidence interval or latency-budget acceptance; n3 first / n6 warm are descriptive.','Do not sum inclusive owner spans. All outliers retained.']}
out=source/'qualified-pairs.json';out.write_text(json.dumps(result,sort_keys=True,indent=2)+'\n')
for row in paired:
    if row['condition']=='all_pairs':
        print(row['source_kind'],row['artifacts'],row['total_terminal_history'],row['wall_ratio_batch_over_individual']['median'],row['paired_wall_delta_ms_batch_minus_individual']['median'])
print('CLEANUP',summary['cleanup'])
