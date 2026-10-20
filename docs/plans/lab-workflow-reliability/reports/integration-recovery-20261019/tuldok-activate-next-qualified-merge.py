import subprocess,json,sys,datetime
from pathlib import Path
n=int(sys.argv[1]);assert n in (105,106,109,110)
prep=json.loads(Path('/tmp/tuldok-remaining-serial-merge-preparation.json').read_text());p=next(x for x in prep['prepared'] if x['pr']==n)
receipt=Path(f'/tmp/tuldok-pr{n}-retarget-main-receipt.json');assert not receipt.exists(),'Inspect existing receipt before retry'
def api(path):return json.loads(subprocess.check_output(['gh','api','repos/MrScripty/Tuldok/'+path]))
def git(*args):return subprocess.check_output(['git',*args],cwd=p['source_worktree'],text=True).strip()
pr=api(f'pulls/{n}');assert pr['state']=='open' and pr['head']['sha']==p['head']
main=api('git/ref/heads/main')['object']['sha'];oldbase=pr['base']['sha']
subprocess.run(['git','-c','credential.helper=!gh auth git-credential','fetch','origin','refs/heads/main'],cwd=p['source_worktree'],check=True)
assert git('rev-parse',oldbase+'^{tree}')==git('rev-parse',main+'^{tree}')
assert git('merge-tree','--write-tree',main,p['head'])==p['tree']
r={'pr':n,'head':p['head'],'main':main,'qualified_old_base':oldbase,'base_trees_equal':True,'prospective_tree':p['tree'],'observed_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'state':'retarget_intent'};receipt.write_text(json.dumps(r,indent=2)+'\n')
req=Path(f'/tmp/tuldok-pr{n}-retarget-request.json');req.write_text(json.dumps({'base':'main'}))
result=subprocess.run(['gh','api','--method','PATCH',f'repos/MrScripty/Tuldok/pulls/{n}','--input',str(req)],capture_output=True,text=True)
r.update(command_exit=result.returncode,stderr=result.stderr);receipt.write_text(json.dumps(r,indent=2)+'\n')
# Always observe a potentially uncertain write; never retry the mutation here.
observed=api(f'pulls/{n}');r.update(observed_base=observed['base']['ref'],observed_base_sha=observed['base']['sha'],observed_head=observed['head']['sha']);receipt.write_text(json.dumps(r,indent=2)+'\n')
assert result.returncode==0 and observed['base']['ref']=='main' and observed['base']['sha']==main and observed['head']['sha']==p['head']
r['state']='retarget_confirmed';receipt.write_text(json.dumps(r,indent=2)+'\n')
p['base']=main;plan=Path(f'/tmp/tuldok-pr{n}-merge-plan.json');plan.write_text(json.dumps(p,indent=2)+'\n')
subprocess.run(['python','/tmp/tuldok-merge-qualified-pr.py',str(plan)],check=True)
