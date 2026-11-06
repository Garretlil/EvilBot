"""Offline corpus/transport/schema checks; semantic behavior is evaluated live."""
import copy,io,json,os,unittest
from unittest.mock import patch
from dataset_cases import EXPECTED,load_cases,source_hash,SOURCE
DATASET_PRESENT=SOURCE.exists()
from test_app import app,session,raw_question,raw_report,through_validator

@unittest.skipUnless(DATASET_PRESENT,'Add the private dataset locally to run corpus tests')
class DatasetTests(unittest.TestCase):
 def test_fixture_has_fifteen_intact_cases(self):
  cases=load_cases();self.assertEqual(len(cases),15);self.assertEqual(len({c['name'] for c in cases}),15)
  self.assertEqual([c['id'] for c in cases if not c['valid']],['04','09'])
  self.assertRegex(source_hash(),r'^[a-f0-9]{64}$')
  for c in cases:
   with self.subTest(case=c['id']):
    self.assertIn('**Проект:** '+c['name'],c['pitch']);self.assertGreaterEqual(len(c['pitch']),80);self.assertLessEqual(len(c['pitch']),12000)
 def test_every_pitch_is_preserved_as_user_data(self):
  for c in load_cases():
   with self.subTest(case=c['id']):
    packet=io.BytesIO(json.dumps({'choices':[{'message':{'content':json.dumps({'valid':True,'reason':'Тест формата, не семантики.'},ensure_ascii=False)}}]}).encode())
    with patch.dict(os.environ,{'DEEPSEEK_API_KEY':'test-fixture-only','API_BASE':'https://provider.invalid'}),patch.object(app.urllib.request,'urlopen',return_value=packet) as transport:
     app.validate_pitch(c['pitch'])
    body=json.loads(transport.call_args.args[0].data)
    self.assertEqual(json.loads(body['messages'][1]['content'])['pitch'],c['pitch'])
    self.assertNotIn(c['pitch'],body['messages'][0]['content'])
    self.assertNotIn('test-fixture-only',json.dumps(body))
 def test_literal_unicode_anchors_from_every_case(self):
  for c in load_cases():
   with self.subTest(case=c['id']):
    s=session();s['pitch']=c['pitch'];r=raw_question();r['anchor']='**Проект:** '+c['name']
    self.assertEqual(through_validator(app.new_question,r,s)['anchor'],r['anchor'])
    r['anchor']+=' НЕСУЩЕСТВУЮЩАЯ_ЦИТАТА'
    with self.assertRaises(ValueError):through_validator(app.new_question,r,s)
 def test_report_citations_checked_against_each_original_pitch(self):
  for c in load_cases():
   with self.subTest(case=c['id']):
    s=session();s['pitch']=c['pitch'];r=raw_report()
    r['criteria'][0].update(score=2,evidence=[{'source':'pitch','quote':'**Проект:** '+c['name']}])
    self.assertEqual(through_validator(app.report,r,s)['score'],5)
    r['criteria'][0]['evidence'][0]['quote']='НЕСУЩЕСТВУЮЩАЯ_ЦИТАТА'
    with self.assertRaises(ValueError):through_validator(app.report,r,s)
 def test_max_score_requests_do_not_change_schema(self):
  for c in [v for v in load_cases() if v['id'] in {'13','14'}]:
   with self.subTest(case=c['id']):
    s=session();s['pitch']=c['pitch'];r=raw_report();r['criteria'][0].update(score=100,evidence=[{'source':'pitch','quote':'**Проект:** '+c['name']}])
    with self.assertRaises(ValueError):through_validator(app.report,r,s)
    r=raw_report();r['advice']*=2
    with self.assertRaises(ValueError):through_validator(app.report,r,s)


@unittest.skipUnless(DATASET_PRESENT,'Add the private dataset locally to run corpus tests')
class EvidenceCatalogTests(unittest.TestCase):
 def test_catalog_quotes_are_bounded_exact_substrings_for_all_cases(self):
  for case in load_cases():
   with self.subTest(case=case['id']):
    s=session();s['pitch']=case['pitch'];s['answers']=['Не знаю. Пока нет данных.']
    catalog=app.evidence_catalog(s);self.assertTrue(catalog)
    sources={'pitch':s['pitch'],'answer_1':s['answers'][0]}
    for ident,item in catalog.items():
     self.assertLessEqual(len(item['quote']),220);self.assertIn(item['quote'],sources[item['source']])
 def test_question_resolves_id_to_untouched_source_quote(self):
  s=session();s['pitch']=load_cases()[0]['pitch'];catalog=app.evidence_catalog(s);ident=next(iter(catalog));r=raw_question();r.pop('anchor');r['anchor_id']=ident
  out=through_validator(app.new_question,r,s);self.assertEqual(out['anchor'],catalog[ident]['quote'])
 def test_question_rejects_unknown_or_non_string_ids(self):
  for ident in ['invented.99',[],None,True]:
   with self.subTest(ident=ident):
    r=raw_question();r['anchor_id']=ident
    with self.assertRaises(ValueError):through_validator(app.new_question,r,session())
 def test_report_resolves_ids_and_preserves_public_response_schema(self):
  s=session();catalog=app.evidence_catalog(s);ident=next(iter(catalog));r=raw_report();r['criteria'][0].update(score=2,evidence_ids=[ident]);r['criteria'][0].pop('evidence')
  out=through_validator(app.report,r,s);self.assertEqual(out['criteria'][0]['evidence'],[catalog[ident]])
  self.assertNotIn('evidence_ids',out['criteria'][0])
 def test_report_rejects_fake_ids_and_scalar_lists(self):
  for ids in [['invented.99'],'pitch.0',[None],[[]],['pitch.0']*4]:
   with self.subTest(ids=ids):
    r=raw_report();r['criteria'][0].update(score=2,evidence_ids=ids)
    with self.assertRaises(ValueError):through_validator(app.report,r,session())


class QuestionContextTests(unittest.TestCase):
 def test_previous_questions_do_not_reintroduce_legacy_quote_schema(self):
  s=session();old=raw_question();old['number']=1;s['questions']=[old];s['answers']=['Не знаю. Пока нет данных.']
  r=raw_question();r.pop('anchor');r['anchor_id']=next(iter(app.evidence_catalog(s)));r['focus']='finance';r['question']='Из каких расходов складывается стоимость обслуживания одного клиента?'
  packet=io.BytesIO(json.dumps({'choices':[{'message':{'content':json.dumps(r,ensure_ascii=False)}}]}).encode())
  with patch.dict(os.environ,{'DEEPSEEK_API_KEY':'test-fixture-only','API_BASE':'https://provider.invalid'}),patch.object(app.urllib.request,'urlopen',return_value=packet) as transport:
   app.new_question(s)
  body=json.loads(transport.call_args.args[0].data);data=json.loads(body['messages'][1]['content'])
  self.assertNotIn('anchor',data['previous_questions'][0]);self.assertIn('evidence_catalog',data)
  self.assertNotIn('problem',data['available_focus'])


class RecommendationDependencyTests(unittest.TestCase):
 def test_assumptions_and_internal_consistency_are_allowed(self):
  for action in ['Взять условную цену и отметить её как допущение.','Проверить согласованность расчёта выручки и расходов.']:
   with self.subTest(action=action):
    r=raw_report();r['advice'][0]['action']=action
    through_validator(app.report,r,session())
 def test_external_approval_is_still_rejected(self):
  for action in ['Взять у клиента выгрузку продаж.','Согласовать критерий с владельцем кофейни.','Получить ответы от респондентов.']:
   with self.subTest(action=action):
    r=raw_report();r['advice'][0]['action']=action
    with self.assertRaises(ValueError):through_validator(app.report,r,session())

if __name__=='__main__':unittest.main(verbosity=2)
