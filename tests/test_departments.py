import copy,os,unittest
from unittest.mock import MagicMock,patch
from botocore.exceptions import ClientError
from test_security import app,event
class Departments(unittest.TestCase):
 def setUp(self):
  self.rows=copy.deepcopy(app.DEFAULT_DEPARTMENTS);self.version=0;self.service=MagicMock();self.service.list_users_in_group.return_value={'Users':[]}
  self.catalog=MagicMock();self.catalog.scan.return_value={'Items':[]}
  self.patches=[patch.dict(os.environ,{'USER_POOL_ID':'pool'}),patch.object(app,'client',return_value=self.service),patch.object(app,'table',return_value=self.catalog),patch.object(app,'department_config',side_effect=lambda:(copy.deepcopy(self.rows),self.version)),patch.object(app,'save_departments',side_effect=self.save)]
  for p in self.patches:p.start();self.addCleanup(p.stop)
 def save(self,rows,revision):self.rows=copy.deepcopy(rows);self.version=revision+1
 def run_action(self,action,ident='finance',**extra):return app.manage_departments({'action':action,'id':ident,**extra},{'id':'admin'})
 def add(self):self.rows['finance']={'id':'finance','name':'Finance','status':'ACTIVE'}
 def test_create_department_and_cognito_group(self):
  self.run_action('create',name='Finance');self.assertEqual(self.rows['finance']['status'],'ACTIVE')
  self.service.create_group.assert_called_once_with(UserPoolId='pool',GroupName='finance',Description='Thinking AI managed department finance')
 def test_reserved_admin_id_rejected(self):
  with self.assertRaises(app.RequestError):self.run_action('create','admin',name='Admin')
  self.service.create_group.assert_not_called()
 def test_duplicate_id_is_rejected(self):
  with self.assertRaises(app.RequestError):self.run_action('create','hr',name='Other HR')
 def test_custom_department_can_upload(self):
  self.add();self.service.generate_presigned_post.return_value={}
  with patch.object(app,'put_doc') as put:app.admin_action('prepare',{'departments':['finance'],'name':'policy.pdf','size':100})
  self.assertEqual(put.call_args.args[0]['department'],'finance')
 def test_custom_department_account_role_allowed(self):
  self.add();self.service.admin_create_user.return_value={'User':{'Username':'new'}}
  app.manage_accounts({'action':'create','email':'a@example.com','name':'A','role':'finance'},{'id':'admin'})
  self.service.admin_add_user_to_group.assert_called_once_with(UserPoolId='pool',Username='new',GroupName='finance')
 def test_custom_department_staff_allowed(self):
  self.add();principal=app.principal(event(['finance']));self.assertEqual(principal['departmentName'],'Finance')
 def test_disabled_department_blocks_staff_and_uploads(self):
  self.add();self.run_action('disable')
  with self.assertRaises(app.RequestError):app.principal(event(['finance']))
  with self.assertRaises(app.RequestError):app.admin_action('prepare',{'departments':['finance'],'name':'policy.pdf','size':100})
 def test_enable_restores_active_department(self):
  self.add();self.run_action('disable');self.run_action('enable');self.assertIn('finance',app.department_ids())
 def test_rename_preserves_identifier(self):
  self.add();self.run_action('rename',name='Finance & Accounts');self.assertEqual(self.rows['finance']['name'],'Finance & Accounts');self.service.delete_group.assert_not_called()
 def test_builtin_cannot_be_deleted(self):
  with self.assertRaises(app.RequestError):self.run_action('delete','hr',confirm='hr')
  self.service.delete_group.assert_not_called()
 def test_department_with_members_cannot_be_deleted(self):
  self.add();self.service.list_users_in_group.return_value={'Users':[{'Username':'member'}]}
  with self.assertRaises(app.RequestError):self.run_action('delete',confirm='finance')
  self.service.delete_group.assert_not_called()
 def test_department_with_documents_cannot_be_deleted(self):
  self.add();self.catalog.scan.return_value={'Items':[{'pk':'DOC#1'}]}
  with self.assertRaises(app.RequestError):self.run_action('delete',confirm='finance')
  self.service.delete_group.assert_not_called()
 def test_empty_department_deleted_and_id_retired(self):
  self.add();self.run_action('delete',confirm='finance');self.assertEqual(self.rows['finance']['status'],'DELETED');self.service.delete_group.assert_called_once()
  with self.assertRaises(app.RequestError):self.run_action('create',name='Finance')
 def test_only_managed_group_may_be_recovered_after_conflict(self):
  self.service.create_group.side_effect=ClientError({'Error':{'Code':'GroupExistsException'}},'CreateGroup');self.service.get_group.return_value={'Group':{'Description':'External group'}}
  with self.assertRaises(app.RequestError):self.run_action('create',name='Finance')
  self.assertNotIn('finance',self.rows)
 def test_staff_cannot_manage_departments(self):self.assertEqual(app.handler(event(['cloud'],path='/admin/departments'),None)['statusCode'],401)
 def test_member_pagination_does_not_mistake_empty_page_for_empty_group(self):
  self.add();self.service.list_users_in_group.side_effect=[{'Users':[],'NextToken':'next'},{'Users':[{'Username':'member'}]}]
  with self.assertRaises(app.RequestError):self.run_action('delete',confirm='finance')
  self.service.delete_group.assert_not_called()
