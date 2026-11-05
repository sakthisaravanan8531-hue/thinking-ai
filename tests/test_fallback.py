import io,json,os,sys,unittest,zipfile
from pathlib import Path
from unittest.mock import MagicMock,patch
from botocore.exceptions import ClientError
from test_security import app,event
sys.modules['app']=app
sys.path.insert(0,str(Path(__file__).parents[1]/'aws-backend/src'))
import fallback_index as index
PASSAGE={'id':'D1','documentId':'1','name':'policy.txt','text':'Employees are entitled to twenty days of annual leave.'}
class HybridAnswers(unittest.TestCase):
 def setUp(self):
  self.env=patch.dict(os.environ,{'DOCUMENT_FALLBACK_ENABLED':'true','USAGE_TABLE':'usage','FALLBACK_INDEX_BUCKET':'cache'});self.env.start();self.addCleanup(self.env.stop)
  self.user={'id':'u','department':'hr'}
 def test_bedrock_primary_success_never_uses_fallback(self):
  with patch.object(app,'reserve'),patch.object(app,'bedrock_available',return_value=True),patch.object(app,'retrieve',return_value=[PASSAGE]),patch.object(app,'grounded_response',return_value={'answer':'Primary'}),patch.object(index,'search') as local,patch.object(app,'gemini') as gemini:
   result=app.answer('leave',self.user,[])
  self.assertEqual(result['retrieval'],'bedrock');local.assert_not_called();gemini.assert_not_called()
 def test_bedrock_safety_refusal_never_falls_back(self):
  with patch.object(app,'reserve'),patch.object(app,'bedrock_available',return_value=True),patch.object(app,'retrieve',return_value=[PASSAGE]),patch.object(app,'grounded_response',side_effect=app.SafetyBlocked()),patch.object(index,'search') as local:
   with self.assertRaises(app.SafetyBlocked):app.answer('leave',self.user,[])
  local.assert_not_called()
 def test_bedrock_throttle_uses_local_search_and_gemini(self):
  error=ClientError({'Error':{'Code':'ThrottlingException'}},'Retrieve')
  with patch.object(app,'reserve'),patch.object(app,'bedrock_available',return_value=True),patch.object(app,'retrieve',side_effect=error),patch.object(app,'pause_bedrock') as pause,patch.object(index,'search',return_value=([PASSAGE],False)),patch.object(app,'extractive_response',return_value={'answer':'Verified','retrieval':'text-search'}) as generate:
   result=app.answer('leave',self.user,[])
  self.assertEqual(result['retrieval'],'text-search');pause.assert_called_once();generate.assert_called_once()
 def test_shared_cooldown_skips_bedrock(self):
  with patch.object(app,'reserve'),patch.object(app,'bedrock_available',return_value=False),patch.object(app,'retrieve') as retrieve,patch.object(index,'search',return_value=([],False)),patch.object(app,'gemini') as gemini:
   result=app.answer('What is AWS?',self.user,[])
  retrieve.assert_not_called();gemini.assert_not_called();self.assertEqual(result['answer'],app.ABSTAIN)
 def test_generation_outage_reuses_authorized_bedrock_evidence(self):
  with patch.object(app,'reserve'),patch.object(app,'bedrock_available',return_value=True),patch.object(app,'retrieve',return_value=[PASSAGE]),patch.object(app,'grounded_response',side_effect=app.ProviderUnavailable()),patch.object(app,'pause_bedrock'),patch.object(index,'search') as local,patch.object(app,'extractive_response',return_value={}) as generate:app.answer('leave',self.user,[])
  local.assert_not_called();self.assertEqual(generate.call_args.args[3],[PASSAGE])
 def extract(self,result,active=True):
  with patch.object(app,'gemini',return_value=json.dumps(result)),patch.object(app,'checked_evidence',return_value=active),patch.object(app,'client') as clients:
   answer=app.extractive_response('leave',self.user,[],[PASSAGE],False,'text-search')
  clients.assert_not_called() # No Bedrock guardrail dependency in extractive fallback.
  return answer
 def test_topic_explanation_with_source_anchor(self):
  payload={'supported':True,'answer':'Background explanation: PostgreSQL is a relational database. [D1]','excerpts':[{'id':'D1','quote':PASSAGE['text']}]}
  with patch.object(app,'gemini',return_value=json.dumps(payload)),patch.object(app,'checked_evidence',return_value=True):
   result=app.extractive_response('Explain the topic',self.user,[],[PASSAGE],False,'text-search',topic=True)
  self.assertEqual(result['answer'],payload['answer']);self.assertEqual(result['answerMode'],'document-topic-explanation')
 def test_pdf_spacing_and_standalone_topic(self):
  passage={**PASSAGE,'text':'Deploy  an AWS RDS\n PostgreSQL instance in the private subnet group.'}
  payload={'supported':True,'answer':'PostgreSQL is used for the private database. [D1]','excerpts':[{'id':'D1','quote':'Deploy an AWS RDS PostgreSQL instance in the private subnet group.'}]}
  with patch.object(app,'gemini',return_value=json.dumps(payload)) as generate,patch.object(app,'checked_evidence',return_value=True):
   result=app.extractive_response('What is PostgreSQL?',self.user,[{'role':'user','text':'explain exercise 4'}],[passage],False,'text-search',topic=True)
  sent=json.loads(generate.call_args.args[0])
  self.assertEqual(sent['conversation'],[]);self.assertEqual(sent['topicMatches'],['D1'])
  self.assertEqual(result['answer'],payload['answer'])
 def test_missing_inline_citation_is_added_from_verified_anchor(self):
  payload={'supported':True,'answer':'Background explanation: Leave is time away from work.','excerpts':[{'id':'D1','quote':PASSAGE['text']}]}
  with patch.object(app,'gemini',return_value=json.dumps(payload)),patch.object(app,'checked_evidence',return_value=True):
   result=app.extractive_response('What is leave?',self.user,[],[PASSAGE],False,'text-search',topic=True)
  self.assertTrue(result['answer'].endswith('[D1]'));self.assertEqual(result['citations'],[{'id':'D1','name':PASSAGE['name']}])
 def test_unknown_explanation_citation_remains_blocked(self):
  payload={'supported':True,'answer':'An explanation [D99]','excerpts':[{'id':'D1','quote':PASSAGE['text']}]}
  with patch.object(app,'gemini',return_value=json.dumps(payload)),patch.object(app,'checked_evidence',return_value=True):
   result=app.extractive_response('leave',self.user,[],[PASSAGE],False,'text-search',topic=True)
  self.assertEqual(result['answer'],app.ABSTAIN)
 def test_additional_retrieved_citation_is_rechecked(self):
  other={**PASSAGE,'id':'D2','documentId':'2'}
  payload={'supported':True,'answer':'An explanation [D2]','excerpts':[{'id':'D1','quote':PASSAGE['text']}]}
  with patch.object(app,'gemini',return_value=json.dumps(payload)),patch.object(app,'checked_evidence',side_effect=[True,False]):
   result=app.extractive_response('leave',self.user,[],[PASSAGE,other],False,'text-search',topic=True)
  self.assertEqual(result['answer'],app.ABSTAIN)
 def test_topic_refusal(self):
  with patch.object(app,'gemini',return_value='{"supported":false}'):
   result=app.extractive_response('Travel directions',self.user,[],[PASSAGE],False,'text-search',topic=True)
  self.assertEqual(result['answer'],app.ABSTAIN)
 def test_current_question_search_does_not_inherit_unrelated_history(self):
  with patch.object(app,'reserve'),patch.object(app,'bedrock_available',return_value=False),patch.object(index,'search',return_value=([],False)) as search:
   app.answer('Travel directions',self.user,[{'role':'user','text':'explain exercise 1'}])
  search.assert_called_once_with('Travel directions','hr')
 def test_postgresql_spelling(self):
  self.assertEqual(index.words('what is postgeSQL'),['postgresql'])
  self.assertEqual(index.words('postgrSQL postgSQL'),['postgresql','postgresql'])
 def test_only_exact_source_quotes_returned(self):
  result=self.extract({'supported':True,'excerpts':[{'id':'D1','quote':PASSAGE['text']}],'answer':'INVENTED CLAIM'})
  self.assertNotIn('INVENTED',result['answer']);self.assertIn(PASSAGE['text'],result['answer']);self.assertEqual(result['answerMode'],'verified-excerpts')
 def test_fabricated_quote_rejected(self):self.assertEqual(self.extract({'supported':True,'excerpts':[{'id':'D1','quote':'Employees get three hundred days of leave.'}]})['answer'],app.ABSTAIN)
 def test_invalid_citation_rejected(self):self.assertEqual(self.extract({'supported':True,'excerpts':[{'id':'D9','quote':PASSAGE['text']}]})['answer'],app.ABSTAIN)
 def test_deleted_during_generation_is_rejected(self):self.assertEqual(self.extract({'supported':True,'excerpts':[{'id':'D1','quote':PASSAGE['text']}]},False)['answer'],app.ABSTAIN)
 def test_staff_cannot_build_indexes(self):self.assertEqual(app.handler(event(['hr'],path='/admin/fallback-index'),None)['statusCode'],401)
class TextIndex(unittest.TestCase):
 def test_typo_matches_document_vocabulary(self):
  self.assertEqual(index.matching_term('terrafom',{'terraform','database'}),'terraform')
  self.assertEqual(index.matching_term('postgressql',{'postgresql','subnet'}),'postgresql')
  self.assertEqual(index.words('iaac'),['iac'])
 def test_unrelated_and_short_terms_do_not_fuzzy_match(self):
  self.assertIsNone(index.matching_term('travel',{'terraform','postgresql'}))
  self.assertIsNone(index.matching_term('s4',{'s3'}))
 def test_ambiguous_typo_does_not_match(self):
  self.assertIsNone(index.matching_term('testing',{'testings','testin'}))

 def test_utf8_text_extracts(self):
  chunks,partial=index.chunks_from_bytes(b'Company policy: employees can request twenty days of annual leave.','policy.txt');self.assertFalse(partial);self.assertIn('twenty',chunks[0]['text'])
 def test_large_text_is_marked_partial(self):
  chunks,partial=index.chunks_from_bytes(b'hello world '*30000,'large.txt');self.assertTrue(partial);self.assertTrue(chunks)
 def test_docx_extracts_paragraph_text(self):
  data=io.BytesIO()
  with zipfile.ZipFile(data,'w') as z:z.writestr('word/document.xml','<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Approved finance policy.</w:t></w:r></w:p></w:body></w:document>')
  chunks,partial=index.chunks_from_bytes(data.getvalue(),'policy.docx');self.assertEqual(chunks[0]['text'],'Approved finance policy.')
 def test_docx_entity_expansion_rejected(self):
  data=io.BytesIO()
  with zipfile.ZipFile(data,'w') as z:z.writestr('word/document.xml','<!DOCTYPE test [<!ENTITY a "private">]><test>&a;</test>')
  with self.assertRaises(Exception):index.chunks_from_bytes(data.getvalue(),'policy.docx')
 def test_blank_scanned_pdf_has_no_fake_text(self):
  from pypdf import PdfWriter
  stream=io.BytesIO();pdf=PdfWriter();pdf.add_blank_page(width=100,height=100);pdf.write(stream)
  with self.assertRaisesRegex(ValueError,'NO_READABLE_TEXT'):index.chunks_from_bytes(stream.getvalue(),'scan.pdf')
 def test_keyword_normalization_ex1(self):self.assertEqual(index.words('Explain ex1'),index.words('Explain Exercise 1'))
 def search(self,department='hr',mismatch=False,missing=False,old_version=False):
  doc={'id':'1','department':'hr','status':'ACTIVE','key':'hr/1/policy.txt','name':'policy.txt','fallbackStatus':'QUEUED' if missing else 'READY'}
  data={'version':1,'documentId':'1','department':'cloud' if mismatch else 'hr','sourceKey':doc['key'],'sourceETag':'old' if old_version else 'v1','chunks':[{'text':PASSAGE['text']}],'partial':False}
  service=MagicMock();service.head_object.return_value={'ETag':'v1'};service.get_object.side_effect=lambda **kw:{'Body':io.BytesIO(json.dumps(data).encode())}
  with patch.dict(os.environ,{'DOCUMENT_BUCKET':'source','FALLBACK_INDEX_BUCKET':'cache'}),patch.object(index,'active_documents',return_value=[doc]) as list_docs,patch.object(app,'client',return_value=service):
   result=index.search('annual leave',department)
  list_docs.assert_called_once_with(department)
  return result
 def test_keyword_search_selects_actual_passage(self):self.assertEqual(self.search()[0][0]['documentId'],'1')
 def test_cache_department_mismatch_rejected(self):
  with self.assertRaises(app.RequestError):self.search(mismatch=True)
 def test_changed_source_version_is_rejected(self):
  with self.assertRaises(app.RequestError):self.search(old_version=True)
 def test_pending_indexes_do_not_call_any_model(self):
  with self.assertRaises(app.RequestError):self.search(missing=True)
 def test_worker_cannot_update_deleted_doc_to_active(self):
  table=MagicMock()
  with patch.object(app,'table',return_value=table):index._set_state('1','job','READY')
  kwargs=table.update_item.call_args.kwargs;self.assertIn('#s = :active',kwargs['ConditionExpression']);self.assertNotIn('status =',kwargs['UpdateExpression'])
 def test_worker_rejects_untrusted_job_shape(self):self.assertEqual(index.handler({'documentIds':[]},None)['error'],'INVALID_JOB')
 def test_worker_extracts_and_writes_authorized_index(self):
  job='a'*32;doc={'id':'1','department':'hr','status':'ACTIVE','fallbackJob':job,'key':'hr/1/policy.txt','name':'policy.txt'}
  service=MagicMock();raw=PASSAGE['text'].encode();service.head_object.return_value={'ETag':'v1','ContentLength':len(raw)};service.get_object.return_value={'ETag':'v1','Body':io.BytesIO(raw)}
  with patch.dict(os.environ,{'DOCUMENT_BUCKET':'source','FALLBACK_INDEX_BUCKET':'cache'}),patch.object(app,'client',return_value=service),patch.object(app,'table',return_value=MagicMock()),patch.object(app,'doc_get',return_value=doc),patch.object(index,'_set_state') as state:
   result=index.handler({'jobId':job,'documentIds':['1']},None)
  self.assertEqual(result['completed'],1);self.assertEqual(json.loads(service.put_object.call_args.kwargs['Body'])['department'],'hr');self.assertEqual(state.call_args.args[2],'READY')
class QueueAndCooldown(unittest.TestCase):
 def setUp(self):
  self.env=patch.dict(os.environ,{'DOCUMENT_FALLBACK_ENABLED':'true','USAGE_TABLE':'usage','FALLBACK_INDEX_FUNCTION':'worker','INDEX_DAILY_LIMIT':'20'});self.env.start();self.addCleanup(self.env.stop)
 def test_shared_cooldown_reads_until_timestamp(self):
  service=MagicMock();service.get_item.return_value={'Item':{'until':{'N':str(int(app.time.time())+300)}}}
  with patch.object(app,'client',return_value=service):self.assertFalse(app.bedrock_available())
 def test_schedule_marks_active_docs_then_invokes_worker(self):
  service=MagicMock();service.invoke.return_value={'StatusCode':202};catalog=MagicMock();doc={'id':'1','status':'ACTIVE'}
  with patch.object(app,'client',return_value=service),patch.object(app,'table',return_value=catalog),patch.object(app,'doc_get',return_value=doc):result=index.schedule(['1'])
  self.assertEqual(result['queued'],1);self.assertEqual(service.invoke.call_args.kwargs['InvocationType'],'Event')
  self.assertEqual(json.loads(service.invoke.call_args.kwargs['Payload'])['documentIds'],['1'])
  self.assertIn('#s = :active',catalog.update_item.call_args.kwargs['ConditionExpression'])
 def test_index_daily_limit_blocks_worker_invocation(self):
  service=MagicMock();service.update_item.side_effect=ClientError({'Error':{'Code':'ConditionalCheckFailedException'}},'UpdateItem')
  with patch.object(app,'client',return_value=service),patch.object(app,'doc_get',return_value={'id':'1','status':'ACTIVE'}):result=index.schedule(['1'])
  self.assertEqual(result['queued'],0);service.invoke.assert_not_called()
 def test_deleted_source_is_never_queued(self):
  service=MagicMock()
  with patch.object(app,'client',return_value=service),patch.object(app,'doc_get',return_value={'id':'1','status':'DELETED'}):result=index.schedule(['1'])
  self.assertEqual(result['queued'],0);service.invoke.assert_not_called()
 def test_duplicate_queue_delivery_cannot_reparse_claimed_document(self):
  job='a'*32;catalog=MagicMock();catalog.update_item.side_effect=ClientError({'Error':{'Code':'ConditionalCheckFailedException'}},'UpdateItem');service=MagicMock()
  with patch.object(app,'table',return_value=catalog),patch.object(app,'client',return_value=service),patch.object(app,'doc_get',return_value={'id':'1','status':'ACTIVE','fallbackJob':job}):result=index.handler({'jobId':job,'documentIds':['1']},None)
  self.assertEqual(result['completed'],0);service.get_object.assert_not_called()
 def test_unknown_bedrock_errors_do_not_silently_fall_back(self):
  error=ClientError({'Error':{'Code':'UnknownPolicyError'}},'Retrieve')
  with patch.object(app,'reserve'),patch.object(app,'bedrock_available',return_value=True),patch.object(app,'retrieve',side_effect=error),patch.object(index,'search') as search:
   with self.assertRaises(ClientError):app.answer('leave',{'id':'u','department':'hr'},[])
  search.assert_not_called()
 def test_explicit_service_safety_error_stops_before_fallback(self):
  error=ClientError({'Error':{'Code':'GuardrailIntervenedException'}},'Converse')
  with patch.object(app,'reserve'),patch.object(app,'bedrock_available',return_value=True),patch.object(app,'retrieve',side_effect=error),patch.object(index,'search') as search:
   with self.assertRaises(app.SafetyBlocked):app.answer('leave',{'id':'u','department':'hr'},[])
  search.assert_not_called()
class EmptyKnowledgeBase(unittest.TestCase):
 def test_empty_kb_does_not_disable_ready_text_fallback(self):
  with patch.dict(os.environ,{'DOCUMENT_FALLBACK_ENABLED':'true'}),patch.object(app,'reserve'),patch.object(app,'bedrock_available',return_value=True),patch.object(app,'retrieve',return_value=[]),patch.object(index,'search',return_value=([PASSAGE],False)) as search,patch.object(app,'extractive_response',return_value={'answer':'Verified'}) as generate:
   result=app.answer('leave',{'id':'u','department':'hr'},[])
  search.assert_called_once();generate.assert_called_once();self.assertEqual(result['answer'],'Verified')
class DeletedIndexCleanup(unittest.TestCase):
 def test_worker_removes_derived_text_if_deleted_during_extraction(self):
  job='a'*32;doc={'id':'1','department':'hr','status':'ACTIVE','fallbackJob':job,'key':'hr/1/policy.txt','name':'policy.txt'}
  service=MagicMock();raw=PASSAGE['text'].encode();service.head_object.return_value={'ETag':'v1','ContentLength':len(raw)};service.get_object.return_value={'ETag':'v1','Body':io.BytesIO(raw)}
  with patch.dict(os.environ,{'DOCUMENT_BUCKET':'source','FALLBACK_INDEX_BUCKET':'cache'}),patch.object(app,'client',return_value=service),patch.object(app,'table',return_value=MagicMock()),patch.object(app,'doc_get',side_effect=[doc,{'id':'1','status':'DELETED'}]),patch.object(index,'_set_state',return_value=False):
   result=index.handler({'jobId':job,'documentIds':['1']},None)
  self.assertEqual(result['completed'],0);service.delete_object.assert_called_once_with(Bucket='cache',Key='text-index/1.json')
