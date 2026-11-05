import importlib.util, json, os, unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
os.environ.update(STAFF_CLIENT_ID='staff',ADMIN_CLIENT_ID='admin-client',DOCUMENT_BUCKET='docs',KNOWLEDGE_BASE_ID='kb',GUARDRAIL_ID='guard',GUARDRAIL_VERSION='1',PRIMARY_PROVIDER='gemini')
spec=importlib.util.spec_from_file_location('app',Path(__file__).parents[1]/'aws-backend/src/app.py');app=importlib.util.module_from_spec(spec);spec.loader.exec_module(app)
def event(groups=None,aud='staff',path='/chat',body=None):
 c={'sub':'user-1','token_use':'id','aud':aud,'name':'A User'}
 if groups is not None:c['cognito:groups']=groups
 return {'rawPath':path,'requestContext':{'authorizer':{'jwt':{'claims':c}}},'body':json.dumps(body or {'question':'Explain the policy'})}
def doc(status='ACTIVE',dept='hr'):return {'id':'1','department':dept,'status':status,'key':'hr/1/policy.pdf','name':'policy.pdf'}
def result(dept='hr',uri='s3://docs/hr/1/policy.pdf'):return {'retrievalResults':[{'metadata':{'department':dept,'documentId':'1'},'location':{'s3Location':{'uri':uri}},'content':{'text':'Employees have 20 days leave.'}}]}
class Security(unittest.TestCase):
 def test_missing_login(self):
  self.assertEqual(app.handler({'rawPath':'/chat'},None)['statusCode'],401)
 def test_removed_free_endpoint(self):
  self.assertEqual(app.handler(event(path='/free'),None)['statusCode'],404)
 def test_no_group_denied(self):
  self.assertEqual(app.handler(event(),None)['statusCode'],403)
 def test_multiple_departments_denied(self):
  self.assertEqual(app.handler(event(['hr','cloud']),None)['statusCode'],403)
 def test_staff_cannot_manage_documents(self):
  self.assertEqual(app.handler(event(['hr'],path='/admin/delete'),None)['statusCode'],401)
 def test_admin_group_required(self):
  self.assertEqual(app.handler(event(['hr'],aud='admin-client',path='/admin/list'),None)['statusCode'],403)
 def test_admin_cannot_use_staff_portal(self):
  self.assertEqual(app.handler(event(['admin','hr']),None)['statusCode'],403)
 def test_groups_string(self):
  self.assertEqual(app.principal(event('[hr]'))['department'],'hr')
 def test_access_token_rejected(self):
  e=event(['hr']);e['requestContext']['authorizer']['jwt']['claims']['token_use']='access'
  self.assertEqual(app.handler(e,None)['statusCode'],401)
 def test_user_document_injection_rejected(self):
  e=event(['hr'],body={'question':'x','document':'secret','department':'cloud'})
  self.assertEqual(app.handler(e,None)['statusCode'],400)
 def test_retrieval_filter_and_catalog(self):
  service=MagicMock();service.retrieve.return_value=result()
  with patch.object(app,'client',return_value=service),patch.object(app,'doc_get',return_value=doc()):
   self.assertEqual(len(app.retrieve('leave','hr')),1)
   self.assertEqual(service.retrieve.call_args.kwargs['retrievalConfiguration']['vectorSearchConfiguration']['filter'],{'equals':{'key':'department','value':'hr'}})
 def test_cross_department_vector_discarded(self):
  service=MagicMock();service.retrieve.return_value=result('cloud')
  with patch.object(app,'client',return_value=service),patch.object(app,'doc_get',return_value=doc(dept='cloud')):
   self.assertEqual(app.retrieve('anything','hr'),[])
 def test_deleted_vector_discarded(self):
  service=MagicMock();service.retrieve.return_value=result()
  with patch.object(app,'client',return_value=service),patch.object(app,'doc_get',return_value=doc('DELETED')):
   self.assertEqual(app.retrieve('anything','hr'),[])
 def test_forged_location_discarded(self):
  service=MagicMock();service.retrieve.return_value=result(uri='s3://other/secret')
  with patch.object(app,'client',return_value=service),patch.object(app,'doc_get',return_value=doc()):
   self.assertEqual(app.retrieve('anything','hr'),[])
 def test_no_evidence_never_calls_model(self):
  with patch.object(app,'reserve'),patch.object(app,'retrieve',return_value=[]),patch.object(app,'gemini') as model:
   self.assertEqual(app.answer('What is AWS?',{'id':'u','department':'hr'},[])['answer'],app.ABSTAIN);model.assert_not_called()
 def run_answer(self,raw,action='NONE',deleted=False):
  service=MagicMock();service.apply_guardrail.return_value={'action':action}
  evidence=[{'id':'D1','documentId':'1','name':'policy.pdf','text':'Employees have 20 days leave.'}]
  with patch.object(app,'reserve'),patch.object(app,'retrieve',return_value=evidence),patch.object(app,'gemini',return_value=raw),patch.object(app,'client',return_value=service),patch.object(app,'doc_get',return_value=doc('DELETED' if deleted else 'ACTIVE')):
   return app.answer('How much leave?',{'id':'u','department':'hr'},[])
 def test_unsupported_answer_abstains(self):
  self.assertEqual(self.run_answer('{"supported":false}')['answer'],app.ABSTAIN)
 def test_invalid_citation_abstains(self):
  self.assertEqual(self.run_answer(json.dumps({'supported':True,'answer':'100 days [D9]','citations':['D9']}))['answer'],app.ABSTAIN)
 def test_guardrail_block_abstains(self):
  self.assertEqual(self.run_answer(json.dumps({'supported':True,'answer':'20 days [D1]','citations':['D1']}),'GUARDRAIL_INTERVENED')['answer'],app.ABSTAIN)
 def test_deletion_during_generation_abstains(self):
  self.assertEqual(self.run_answer(json.dumps({'supported':True,'answer':'20 days [D1]','citations':['D1']}),deleted=True)['answer'],app.ABSTAIN)
 def test_grounded_response_has_filename(self):
  answer=self.run_answer(json.dumps({'supported':True,'answer':'20 days [D1]','citations':['D1']}))
  self.assertEqual(answer['citations'],[{'id':'D1','name':'policy.pdf'}])
 def test_delete_tombstone_precedes_s3(self):
  calls=[];service=MagicMock();service.delete_objects.side_effect=lambda **k:(calls.append('s3') or {})
  with patch.object(app,'doc_get',return_value=doc()),patch.object(app,'put_doc',side_effect=lambda d:calls.append(d['status'])),patch.object(app,'client',return_value=service),patch.object(app,'sync_kb',return_value={}):
   app.admin_action('delete',{'id':'1'})
  self.assertEqual(calls,['DELETED','s3','DELETED'])
if __name__=='__main__':unittest.main()
