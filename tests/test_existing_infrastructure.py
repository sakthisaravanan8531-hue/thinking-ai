import unittest
from pathlib import Path
import yaml
ROOT=Path(__file__).parents[1]
class ExistingInfrastructure(unittest.TestCase):
 def test_no_duplicate_bedrock_or_storage(self):
  t=yaml.safe_load((ROOT/'aws-backend/knowledge.yaml').read_text())
  self.assertEqual(set(t['Resources']),{'Catalog','Grounding','GroundingVersion'})
  self.assertEqual(t['Parameters']['KnowledgeBaseId']['Default'],'5KIGBYRICE')
  self.assertEqual(t['Parameters']['DataSourceId']['Default'],'VPS3UHQOQC')
  self.assertEqual(t['Parameters']['DocumentBucket']['Default'],'thinkingai-datasourse-bucket')
  for name in ['KnowledgeBaseId','DataSourceId','DocumentBucket']:
   self.assertEqual(t['Outputs'][name]['Value'],{'Ref':name})
 def test_bucket_configuration_is_wired_before_deploy(self):
  s=(ROOT/'scripts/deploy-backend.ps1').read_text()
  self.assertLess(s.index('configure-document-bucket.ps1'),s.index('sam deploy'))
 def test_no_generation_api_for_migration(self):
  s=(ROOT/'scripts/register-existing-document.py').read_text()
  self.assertNotIn('invoke_model',s)
  self.assertIn('start_ingestion_job',s)
