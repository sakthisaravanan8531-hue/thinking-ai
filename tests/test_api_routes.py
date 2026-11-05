import unittest
from pathlib import Path
import yaml
class ApiRoutes(unittest.TestCase):
 def test_staff_and_admin_routes_are_distinct_and_authenticated(self):
  template=yaml.safe_load((Path(__file__).parents[1]/'aws-backend/template.yaml').read_text())
  events=template['Resources']['ChatFunction']['Properties']['Events']
  paths=[event['Properties']['Path'] for event in events.values()]
  expected={'/chat','/me','/admin/me','/admin/list','/admin/prepare','/admin/complete','/admin/delete','/admin/sync','/admin/job','/admin/users','/admin/departments','/admin/fallback-index'}
  self.assertEqual(set(paths),expected)
  self.assertEqual(len(paths),len(expected))
  for event in events.values():
   self.assertEqual(event['Properties']['Method'],'POST')
   self.assertNotEqual(event['Properties'].get('Auth',{}).get('Authorizer'),'NONE')
  api=template['Resources']['Api']['Properties']
  self.assertEqual(api['Auth']['DefaultAuthorizer'],'CognitoJwt')
  self.assertIn({'Ref':'CloudFrontOrigin'},api['CorsConfiguration']['AllowOrigins'])
