import json, unittest
from unittest.mock import patch
from botocore.exceptions import ClientError
from test_security import app,event
class Diagnostics(unittest.TestCase):
 def test_aws_error_logs_operation_without_provider_message(self):
  error=ClientError({'Error':{'Code':'AccessDeniedException','Message':'SECRET DOCUMENT OR CREDENTIAL'},'ResponseMetadata':{'HTTPStatusCode':403,'RequestId':'aws-id'}},'StartIngestionJob')
  with patch.object(app,'admin_action',side_effect=error),patch('builtins.print') as output:
   result=app.handler(event(['admin'],aud='admin-client',path='/admin/sync'),None)
  logged=json.loads(output.call_args.args[0])
  self.assertEqual(logged['awsOperation'],'StartIngestionJob')
  self.assertEqual(logged['awsErrorCode'],'AccessDeniedException')
  self.assertEqual(logged['route'],'/admin/sync')
  self.assertNotIn('SECRET',str(output.call_args))
  self.assertEqual(result['statusCode'],503)
 def test_python_error_does_not_log_arguments(self):
  with patch.object(app,'admin_action',side_effect=ValueError('private text')),patch('builtins.print') as output:
   app.handler(event(['admin'],aud='admin-client',path='/admin/list'),None)
  logged=json.loads(output.call_args.args[0])
  self.assertEqual(logged['exceptionType'],'ValueError')
  self.assertNotIn('private text',str(output.call_args))
