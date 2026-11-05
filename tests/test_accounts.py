import os,unittest
from unittest.mock import patch,MagicMock
from botocore.exceptions import ClientError
from test_security import app,event,doc
class Accounts(unittest.TestCase):
 def setUp(self):
  self.environment=patch.dict(os.environ,{'USER_POOL_ID':'pool'});self.environment.start();self.addCleanup(self.environment.stop)
  self.service=MagicMock();self.service.admin_get_user.return_value={'Username':'target','Enabled':True,'UserStatus':'CONFIRMED','UserAttributes':[{'Name':'sub','Value':'target-id'}]}
  self.service.admin_list_groups_for_user.return_value={'Groups':[{'GroupName':'cloud'}]}
  self.actor={'id':'admin-id'}
 def invoke(self,data):
  with patch.object(app,'client',return_value=self.service),patch.object(app,'table',return_value=MagicMock()):return app.manage_accounts(data,self.actor)
 def test_create_invite_and_role(self):
  self.service.admin_create_user.return_value={'User':{'Username':'new'}}
  self.invoke({'action':'create','name':'Alice','email':'alice@example.com','role':'hr'})
  self.assertEqual(self.service.admin_create_user.call_args.kwargs['DesiredDeliveryMediums'],['EMAIL'])
  self.assertNotIn('TemporaryPassword',self.service.admin_create_user.call_args.kwargs)
  self.service.admin_add_user_to_group.assert_called_once_with(UserPoolId='pool',Username='new',GroupName='hr')
 def test_invalid_role_never_creates_user(self):
  with self.assertRaises(app.RequestError):self.invoke({'action':'create','name':'Alice','email':'alice@example.com','role':'root'})
  self.service.admin_create_user.assert_not_called()
 def test_self_mutation_blocked(self):
  self.actor={'id':'target-id'}
  for action in ['delete','disable','role','reset','rename','enable','resend']:
   with self.subTest(action=action),self.assertRaises(app.RequestError) as error:self.invoke({'action':action,'username':'target','confirm':'target','role':'hr'})
   self.assertEqual(error.exception.status,409)
  self.service.admin_delete_user.assert_not_called()
 def test_role_removes_old_before_add(self):
  self.invoke({'action':'role','username':'target','role':'hr'})
  self.service.admin_remove_user_from_group.assert_called_once_with(UserPoolId='pool',Username='target',GroupName='cloud')
  self.service.admin_add_user_to_group.assert_called_once_with(UserPoolId='pool',Username='target',GroupName='hr')
  calls=[c[0] for c in self.service.mock_calls];self.assertLess(calls.index('admin_remove_user_from_group'),calls.index('admin_add_user_to_group'))
 def test_delete_requires_explicit_confirmation(self):
  with self.assertRaises(app.RequestError):self.invoke({'action':'delete','username':'target'})
  self.service.admin_delete_user.assert_not_called()
 def test_delete_account_does_not_delete_documents(self):
  self.invoke({'action':'delete','username':'target','confirm':'target'})
  self.service.admin_delete_user.assert_called_once_with(UserPoolId='pool',Username='target')
  self.service.delete_objects.assert_not_called()
 def test_reset_sends_code_not_password(self):
  self.invoke({'action':'reset','username':'target'})
  self.service.admin_reset_user_password.assert_called_once_with(UserPoolId='pool',Username='target')
 def test_disable_revokes_existing_sessions(self):
  catalog=MagicMock()
  with patch.object(app,'client',return_value=self.service),patch.object(app,'table',return_value=catalog):app.manage_accounts({'action':'disable','username':'target'},self.actor)
  self.assertEqual(catalog.put_item.call_args.kwargs['Item']['pk'],'ACCESS#target-id')
  self.service.admin_disable_user.assert_called_once()
 def test_staff_cannot_call_accounts_route(self):
  self.assertEqual(app.handler(event(['cloud'],path='/admin/users'),None)['statusCode'],401)
 def live(self,enabled=True,status='CONFIRMED',groups=['cloud'],revoked=None):
  self.service.admin_get_user.return_value={'Username':'user-1','Enabled':enabled,'UserStatus':status,'UserAttributes':[{'Name':'sub','Value':'user-1'}]}
  catalog=MagicMock();catalog.get_item.return_value={'Item':{'revokedBefore':revoked}} if revoked is not None else {}
  with patch.dict(os.environ,{'ENFORCE_LIVE_ROLES':'true'}),patch.object(app,'client',return_value=self.service),patch.object(app,'table',return_value=catalog),patch.object(app,'account_groups',return_value=groups):
   return app.principal(event(['cloud']))
 def test_live_disabled_account_is_denied(self):
  with self.assertRaises(app.RequestError):self.live(enabled=False)
 def test_live_role_change_rejects_old_token(self):
  with self.assertRaises(app.RequestError):self.live(groups=['hr'])
 def test_password_reset_status_denied(self):
  with self.assertRaises(app.RequestError):self.live(status='RESET_REQUIRED')
 def test_security_watermark_rejects_old_authentication(self):
  with self.assertRaises(app.RequestError):self.live(revoked=100)
 def test_unchanged_enabled_account_allowed(self):self.assertEqual(self.live()['department'],'cloud')
 def test_delete_succeeds_with_pending_bedrock(self):
  self.service.delete_objects.return_value={}
  self.service.start_ingestion_job.side_effect=ClientError({'Error':{'Code':'ValidationException','Message':'quota zero'}},'StartIngestionJob')
  with patch.object(app,'client',return_value=self.service),patch.object(app,'doc_get',return_value=doc()),patch.object(app,'put_doc') as save,patch.dict(os.environ,{'DATA_SOURCE_ID':'source'}):result=app.admin_action('delete',{'id':'1'})
  self.assertEqual(result['job']['status'],'PENDING');self.assertIn('deleted',result['message']);self.assertFalse(save.call_args.args[0]['cleanupPending'])
 def test_source_cleanup_errors_are_retryable_and_blocked(self):
  self.service.delete_objects.return_value={'Errors':[{'Code':'AccessDenied'}]}
  with patch.object(app,'client',return_value=self.service),patch.object(app,'doc_get',return_value=doc()),patch.object(app,'put_doc') as save:result=app.admin_action('delete',{'id':'1'})
  self.assertIn('cleanup is pending',result['message']);self.assertEqual(save.call_args.args[0]['status'],'DELETED');self.assertTrue(save.call_args.args[0]['cleanupPending'])
