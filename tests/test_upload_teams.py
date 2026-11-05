import json,unittest
from unittest.mock import MagicMock,patch
from test_security import app
class TeamUploads(unittest.TestCase):
 def prepare(self,size,departments):
  service=MagicMock();service.generate_presigned_post.return_value={'url':'https://s3','fields':{}}
  with patch.object(app,'client',return_value=service),patch.object(app,'put_doc') as put:
   result=app.admin_action('prepare',{'name':'policy.pdf','size':size,'departments':departments})
  return result,service,put
 def test_accepts_exact_50_mib_and_signs_exact_limit(self):
  result,service,put=self.prepare(50*1024*1024,['hr','cloud'])
  self.assertIn(['content-length-range',1,50*1024*1024],service.generate_presigned_post.call_args.kwargs['Conditions'])
  self.assertEqual(put.call_args.args[0]['targetDepartments'],['hr','cloud'])
 def test_rejects_above_50_mib(self):
  with self.assertRaises(app.RequestError) as e:self.prepare(50*1024*1024+1,['hr'])
  self.assertEqual(e.exception.status,413)
 def test_rejects_no_teams(self):
  with self.assertRaises(app.RequestError):self.prepare(100,[])
 def test_rejects_admin_as_upload_team(self):
  with self.assertRaises(app.RequestError):self.prepare(100,['hr','admin'])
 def test_deduplicates_teams(self):
  _,_,put=self.prepare(100,['hr','hr']);self.assertEqual(put.call_args.args[0]['targetDepartments'],['hr'])
 def complete(self,targets,deleted_sibling=False):
  original={'pk':'DOC#main','id':'main','name':'policy.pdf','key':'hr/main/policy.pdf','department':'hr','targetDepartments':targets,'size':100,'status':'PENDING'}
  records={'main':original};service=MagicMock();service.head_object.return_value={'ContentLength':100}
  if deleted_sibling:
   ident=app.uuid.uuid5(app.uuid.NAMESPACE_URL,'main:cloud').hex;records[ident]={'id':ident,'status':'DELETED'}
  writes=[]
  def save(d,**kwargs):records[d['id']]=dict(d);writes.append(dict(d))
  with patch.object(app,'client',return_value=service),patch.object(app,'doc_get',side_effect=lambda i:records.get(i)),patch.object(app,'put_doc',side_effect=save),patch.object(app,'sync_kb',return_value={'status':'PENDING'}):
   result=app.admin_action('complete',{'id':'main'})
   # Retrying must not duplicate a completed team's source copy.
   count=service.copy_object.call_count;app.admin_action('complete',{'id':'main'});self.assertEqual(service.copy_object.call_count,count)
  return result,service,writes
 def test_two_teams_get_separate_metadata(self):
  _,service,writes=self.complete(['hr','cloud']);self.assertEqual(service.copy_object.call_count,1)
  metadata=[json.loads(c.kwargs['Body'])['metadataAttributes'] for c in service.put_object.call_args_list]
  self.assertEqual({x['department'] for x in metadata},{'hr','cloud'})
  self.assertEqual({x['department'] for x in writes if x['status']=='ACTIVE'},{'hr','cloud'})
 def test_three_teams_only_two_server_copies(self):
  _,service,_=self.complete(['hr','cloud','genai']);self.assertEqual(service.copy_object.call_count,2)
 def test_deleted_copy_never_recreated(self):
  _,service,_=self.complete(['hr','cloud'],True);service.copy_object.assert_not_called()
 def test_conditional_writes_protect_tombstones(self):
  catalog=MagicMock()
  with patch.object(app,'table',return_value=catalog):app.put_doc({'pk':'DOC#x','status':'ACTIVE'},protect_deleted=True)
  self.assertIn('ConditionExpression',catalog.put_item.call_args.kwargs)
