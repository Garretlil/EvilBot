"""Optional local dataset adapter. Source applications are not publicly distributed."""
import hashlib,re
from pathlib import Path
SOURCE=Path(__file__).parent/'fixtures/pitch-dataset.md'
EXPECTED={}
def source_hash():return hashlib.sha256(SOURCE.read_bytes()).hexdigest()
def load_cases():
 chunks=re.split(r'(?=^## Заявка \d{2}\s)',SOURCE.read_text(),flags=re.M)[1:]
 cases=[]
 for chunk in chunks:
  ident=re.search(r'^## Заявка (\d{2})',chunk).group(1)
  name=re.search(r'^\*\*Проект:\*\*\s*(.+)',chunk,re.M).group(1).strip()
  cases.append({'id':ident,'name':name,'pitch':chunk.strip(),'valid':ident not in {'04','09'},'sales':'explicit_zero' if ident=='08' else 'claimed_positive' if ident in {'06','07','15'} else 'unknown','risk':'Review the original pitch; no per-project runtime rules.'})
 if [c['id'] for c in cases]!=[f'{i:02}' for i in range(1,16)]:raise ValueError('Expected 15 cases')
 return cases
