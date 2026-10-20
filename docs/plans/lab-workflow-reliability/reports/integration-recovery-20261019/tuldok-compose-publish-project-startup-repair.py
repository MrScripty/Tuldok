from pathlib import Path
import subprocess,json,datetime,hashlib
wt111=Path('/workspace/Tuldok-retained-analysis-integration-20261020');wt112=Path('/workspace/Tuldok-captions-dialog-ci-repair-20261020');old111='0ba4db01f04a77c262eb4b397f88849e9688b5ab';new111='29011daea37f101ee30be9bc10aab702a16c830a';old112='abbae728434fa0670478e12216a1d94603a97daf';main='c1fc60dbf2d96d3cb0ac0739a6822c6b3301f0ad';out=Path('/tmp/tuldok-pr111-112-project-startup-publication.json');assert not out.exists()
r={'state':'local_composition_intent','observed_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'old111':old111,'new111':new111,'old112':old112,'main':main,'independent_review_sha256':hashlib.sha256(Path('/tmp/tuldok-project-startup-ci-independent-review.json').read_bytes()).hexdigest(),'root_actual_review_sha256':hashlib.sha256(Path('/tmp/tuldok-project-startup-root-actual-receipt-review.json').read_bytes()).hexdigest()}
def save():out.write_text(json.dumps(r,indent=2)+'\n')
def git(wt,*a):return subprocess.check_output(['git',*a],cwd=wt,text=True).strip()
def api(p):return json.loads(subprocess.check_output(['gh','api','repos/MrScripty/Tuldok/'+p]))
save()
for wt,sha in ((wt111,old111),(wt112,old112)):
 assert git(wt,'rev-parse','HEAD')==sha and not git(wt,'status','--porcelain','--untracked-files=all')
for n,sha in ((111,old111),(112,old112)):
 p=api(f'pulls/{n}');assert p['state']=='open'and p['draft']and p['head']['sha']==sha
assert api('git/ref/heads/main')['object']['sha']==main
assert git(wt111,'merge-tree','--write-tree',main,new111)==git(wt111,'rev-parse',new111+'^{tree}')
r['prospective112_tree']=git(wt112,'merge-tree','--write-tree',old112,new111);save()
subprocess.run(['git','merge','--ff-only',new111],cwd=wt111,check=True,stdout=subprocess.DEVNULL);r['state']='111_local_fastforward_verified';assert git(wt111,'rev-parse','HEAD')==new111;save()
subprocess.run(['git','merge','--no-ff','-m','Merge reviewed project startup readiness repair',new111],cwd=wt112,check=True,stdout=subprocess.DEVNULL);new112=git(wt112,'rev-parse','HEAD');r.update(new112=new112,state='112_local_whole_merge_verified');assert git(wt112,'rev-parse','HEAD^{tree}')==r['prospective112_tree'];assert git(wt112,'show','-s','--format=%P','HEAD').split()==[old112,new111];save()
for folder,qual,key in (('docs/plans/retained-analysis/reports/project-startup-ci-20261020','qualification.json','source_sha256'),('docs/plans/lab-workflow-reliability/reports/caption-dialog-ci-20261020','qualification.json','tested_before_commit_with_exact_file_hashes')):
 q=json.loads((wt112/folder/qual).read_text())
 for p,h in q[key].items():assert hashlib.sha256((wt112/p).read_bytes()).hexdigest()==h,p
assert all(p.startswith(('tests/','docs/'))for p in git(wt112,'diff','--name-only',new111,new112).splitlines())
log=Path('/tmp/tuldok-pr111-112-startup-composed-local-checks.log')
with log.open('w')as stream:
 for cmd in (['node','--check','tests/browser_scientific_fields.cjs'],['node','--check','tests/browser_captions.cjs'],['node','tests/test_workspace_project_startup.cjs'],['node','tests/test_browser_cdp_session.cjs']):
  stream.write('COMMAND '+json.dumps(cmd)+'\n');stream.flush();subprocess.run(cmd,cwd=wt112,stdout=stream,stderr=subprocess.STDOUT,check=True)
r.update(state='composition_source_hashes_and_focused_checks_passed',composition_log=str(log),composition_log_sha256=hashlib.sha256(log.read_bytes()).hexdigest());save()
for wt in(wt111,wt112):assert not git(wt,'status','--porcelain','--untracked-files=all')
assert api('git/ref/heads/feature/retained-analysis-query-20261019')['object']['sha']==old111
assert api('git/ref/heads/fix/captions-dialog-ci-qualification-20261020')['object']['sha']==old112
r['state']='atomic_publication_intent';save()
a=subprocess.run(['git','-c','credential.helper=!gh auth git-credential','push','--atomic','origin',new111+':refs/heads/feature/retained-analysis-query-20261019',new112+':refs/heads/fix/captions-dialog-ci-qualification-20261020'],cwd=wt111,capture_output=True,text=True);r.update(push_exit=a.returncode,push_stdout=a.stdout,push_stderr=a.stderr);save()
r['remote111']=api('git/ref/heads/feature/retained-analysis-query-20261019')['object']['sha'];r['remote112']=api('git/ref/heads/fix/captions-dialog-ci-qualification-20261020')['object']['sha'];save();assert a.returncode==0 and r['remote111']==new111 and r['remote112']==new112
for n,sha in((111,new111),(112,new112)):
 p=api(f'pulls/{n}');assert p['head']['sha']==sha and p['draft'];r[f'pr{n}_head_verified']=sha
r['state']='atomic_publication_and_PR_heads_verified';save();print(json.dumps({'state':r['state'],'head111':new111,'head112':new112,'product_source_identical_to_reviewed111':True,'both_prior_qualifications_source_hashes_match':True}))
