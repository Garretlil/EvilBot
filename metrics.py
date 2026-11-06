"""Aggregate prototype metrics; no pitch text or identifiers printed."""
import json,sqlite3,time
from pathlib import Path
from collections import defaultdict
c=sqlite3.connect(Path(__file__).parent/'data/sessions.sqlite')
rows=c.execute('SELECT owner, project, created, version, scores FROM events WHERE created>? ORDER BY created',(time.time()-30*86400,)).fetchall()
users=defaultdict(list)
for owner,project,created,version,scores in rows:
 users[owner].append({'project':project,'created':created,'version':version,'scores':json.loads(scores)})
eligible=returned=improved=comparable=incomparable=0
for rounds in users.values():
 first=rounds[0]
 if first['created']<=time.time()-7*86400:
  eligible+=1
  returned+=any(r['project']==first['project'] and r['created']<=first['created']+7*86400 for r in rounds[1:])
 previous={}
 for r in rounds:
  p=previous.get(r['project']);previous[r['project']]=r
  if not p:continue
  common=[k for k,v in r['scores'].items() if v is not None and p['scores'].get(k) is not None]
  if p['version']!=r['version'] or len(common)<5:incomparable+=1;continue
  comparable+=1
  improved+=sum(r['scores'][k]-p['scores'][k] for k in common)>=2
print(json.dumps({'window_days':30,'completed_rounds':len(rows),'users':len(users),'return_7d':{'eligible':eligible,'returned':returned,'rate':returned/eligible if eligible else None},'improvement':{'comparable_pairs':comparable,'improved_pairs':improved,'incomparable_pairs':incomparable,'rate':improved/comparable if comparable else None},'limits':'Within one browser. Measures presented answers, not independently verified business progress.'},ensure_ascii=False,indent=2))
