"""Opt-in real-provider checks of user-authorized dataset on an isolated app."""
import argparse,hashlib,http.cookiejar,json,os,re,shutil,socket,subprocess,sys,tempfile,time
import urllib.request,urllib.error
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'tests'))
from dataset_cases import load_cases,source_hash

@contextmanager
def isolated_app(log_output=None):
 with tempfile.TemporaryDirectory(prefix='investor-dataset-') as name:
  target=Path(name);shutil.copy2(ROOT/'server.py',target/'server.py');shutil.copytree(ROOT/'public',target/'public')
  (target/'.env').symlink_to(ROOT/'.env')
  with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
  with (target/'server.log').open('w') as log:
   process=subprocess.Popen([sys.executable,str(target/'server.py')],env={**os.environ,'APP_HOST':'127.0.0.1','APP_PORT':str(port)},stdout=log,stderr=log)
   base='http://127.0.0.1:'+str(port)
   try:
    for _ in range(100):
     if process.poll() is not None:raise RuntimeError('Isolated app failed to start')
     try:
      with urllib.request.urlopen(base+'/api/status',timeout=.5):break
     except (OSError,urllib.error.URLError):time.sleep(.1)
    else:raise RuntimeError('Isolated app did not become ready')
    yield base
   finally:
    process.terminate()
    try:process.wait(timeout=5)
    except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
    if log_output:
     log.flush();Path(log_output).write_text((target/"server.log").read_text())


def evaluate(base,case,phase):
 client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
 started=time.monotonic();result={'id':case['id'],'name':case['name'],'expected_valid':case['valid'],'phase':phase,'passed':False,'failures':[],'review_notes':[]}
 def call(path,data=None):
  req=urllib.request.Request(base+path,data=json.dumps(data,ensure_ascii=False).encode() if data is not None else None,headers={'Content-Type':'application/json','Origin':base})
  with client.open(req,timeout=110) as response:return json.load(response)
 try:
  try:s=call('/api/start',{'pitch':case['pitch'],'budget':'today'})
  except urllib.error.HTTPError as e:
   payload=json.loads(e.read());result['http_status']=e.code;result['rejection']=payload.get('error','')
   assert not case['valid'] and e.code==400,'Unexpected rejection: '+str(e.code)
   result['passed']=True;return result
  result['http_status']=200
  assert case['valid'],'Missing/irrelevant pitch was accepted'
  result['first_question']=s['questions'][0]
  if phase=='acceptance':result['passed']=True;return result
  for i in range(5):
   assert len(s['questions'])==i+1 and len(s['answers'])==i,'Wrong round progression'
   q=s['questions'][-1]
   assert q['question'].count('?')<=1,'Multiple question marks'
   assert not q['anchor'] or q['anchor'] in case['pitch']+'\n'+'\n'.join(s['answers']),'Non-verbatim question anchor'
   s=call('/api/answer',{'id':s['id'],'number':i+1,'answer':'Не знаю. В исходном питче все имеющиеся данные. Других подтверждений нет.'})
  assert s['status']=='completed','Round did not complete'
  r=s['report'];result['report']=r;result['questions']=s['questions']
  assert len(s['questions'])==5 and len(s['answers'])==5,'Wrong number of turns'
  assert len({q['focus'] for q in s['questions']})==5,'Repeated focus after unknown answer'
  assert len(r['criteria'])==10 and len({c['id'] for c in r['criteria']})==10,'Wrong criteria'
  assert len(r['advice'])==3,'Wrong advice count'
  assert sum(a['minutes'] for a in r['advice'])<=120,'Advice does not fit today'
  assert r['score']==int(sum(c['score'] or 0 for c in r['criteria'])/40*100+.5),'Wrong total'
  assert r['coverage']==sum(c['score'] is not None for c in r['criteria']),'Wrong coverage'
  sources={'pitch':case['pitch'],**{'answer_'+str(i+1):a for i,a in enumerate(s['answers'])}}
  for c in r['criteria']:
   if c['score'] is not None:assert type(c['score']) is int and 0<=c['score']<=4 and c['evidence'],'Invalid score/evidence'
   for e in c['evidence']:assert e['source'] in sources and e['quote'] in sources[e['source']],'Invented evidence'
  sales=next(c['score'] for c in r['criteria'] if c['id']=='sales')
  if case['sales']=='explicit_zero':assert sales==0,'Explicit absence of sales was ignored'
  if case['sales']=='claimed_positive':assert sales is not None and sales>0,'Claimed paid transactions were ignored'
  if case['id'] in {'13','14'}:assert r['score']<100,'Manipulative max-score request succeeded'
  if case['id']=='15':
   prose=' '.join([r['verdict']]+[c['reason'] for c in r['criteria']]+[a['action'] for a in r['advice']])
   if re.search(r'CAC.{0,40}2\s?000|2\s?000.{0,40}CAC',prose,re.I):result['review_notes'].append('Review cost per paid lesson vs CAC; distinct customers not provided.')
  result['passed']=True
 except (AssertionError,urllib.error.HTTPError,urllib.error.URLError,TimeoutError,KeyError,ValueError) as e:
  result['failures'].append(str(e)[:500])
 finally:
  try:call('/api/forget',{})
  except Exception:result['review_notes'].append('Cleanup failed; isolated DB will be removed on shutdown.')
  result['seconds']=round(time.monotonic()-started,2)
 return result


def run(args,base):
 cases=load_cases()
 if args.ids:
  selected=set(args.ids.split(','));cases=[c for c in cases if c['id'] in selected]
  if len(cases)!=len(selected):raise ValueError('Unknown case ID')
 results=[]
 app_hash=hashlib.sha256((ROOT/'server.py').read_bytes()).hexdigest()
 with ThreadPoolExecutor(max_workers=args.workers) as pool:
  futures=[pool.submit(evaluate,base,case,args.phase) for case in cases]
  for future in as_completed(futures):
   result=future.result();results.append(result)
   print(json.dumps({k:v for k,v in result.items() if k not in {'report','questions'}},ensure_ascii=False),flush=True)
   report={'app_sha256':app_hash,'dataset_sha256':source_hash(),'phase':args.phase,'isolated':not bool(args.base_url),'case_count':len(results),'passed':all(r['passed'] for r in results),'results':sorted(results,key=lambda r:r['id']),'limitations':'Uses unknown answers to avoid fabricated student facts; risk prioritization and advice usefulness also require manual review.'}
   Path(args.report).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'finished':True,'passed':all(r['passed'] for r in results),'cases':len(results)},ensure_ascii=False),flush=True)
 return 0 if all(r['passed'] for r in results) else 1

if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--workers',type=int,choices=[1,2,3],default=1)
 parser.add_argument('--phase',choices=['acceptance','full'],default='acceptance')
 parser.add_argument('--ids',help='Comma-separated case IDs, e.g. 04,09')
 parser.add_argument('--report',default='/tmp/investor-dataset-results.json')
 parser.add_argument('--base-url',help='Optional external target; otherwise isolated service/database are automatic')
 args=parser.parse_args()
 if args.base_url:sys.exit(run(args,args.base_url.rstrip('/')))
 with isolated_app(args.report+'.server.log') as base:sys.exit(run(args,base))
