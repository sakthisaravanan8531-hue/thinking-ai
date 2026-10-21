import importlib.util
import json
import os
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

# Unit tests run without AWS credentials, SDK installation or network calls.
class FakeClientError(Exception):
    def __init__(self, code):
        self.response = {'Error': {'Code': code}}
class FakeCoreError(Exception):
    pass
sys.modules.setdefault('boto3', types.SimpleNamespace(client=lambda *a, **k: None))
sys.modules.setdefault('botocore', types.ModuleType('botocore'))
sys.modules.setdefault('botocore.config', types.SimpleNamespace(Config=lambda **k: k))
sys.modules.setdefault('botocore.exceptions', types.SimpleNamespace(BotoCoreError=FakeCoreError, ClientError=FakeClientError))
spec = importlib.util.spec_from_file_location('app', Path(__file__).parents[1] / 'src/app.py')
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)

def event(**data):
    return {'body': json.dumps(data), 'requestContext': {'authorizer': {'jwt': {'claims': {'sub': 'test-user'}}}}}

class BackendTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'APP_ENABLED': 'true', 'PRIMARY_PROVIDER': 'bedrock', 'USAGE_TABLE': 'test', 'GLOBAL_DAILY_LIMIT': '50', 'USER_DAILY_LIMIT': '20', 'FREE_NETWORK_DAILY_LIMIT': '10', 'FREE_SHARED_DAILY_LIMIT': '20'})
        self.env.start()
        app._circuit_until = 0
    def tearDown(self):
        self.env.stop()
    def test_requires_authenticated_user(self):
        with patch.object(app, 'reserve') as call:
            self.assertEqual(app.handler({'body': '{}'}, None)['statusCode'], 401)
            call.assert_not_called()
    def test_oversize_document_does_not_spend(self):
        with patch.object(app, 'reserve') as call:
            r = app.handler(event(question='Summarize', document='x' * 200001), None)
            self.assertEqual(r['statusCode'], 413); call.assert_not_called()
    def test_validation_rejects_non_object(self):
        e = event(); e['body'] = '[]'
        self.assertEqual(app.handler(e, None)['statusCode'], 400)
    def test_global_limit_prevents_provider_call(self):
        with patch.object(app, 'reserve', side_effect=app.RequestError(429, 'Limit')), patch.object(app, 'bedrock') as b:
            self.assertEqual(app.handler(event(question='Hi'), None)['statusCode'], 429)
            b.assert_not_called()
    def test_bedrock_success_does_not_call_gemini(self):
        with patch.object(app, 'reserve'), patch.object(app, 'bedrock', return_value='Hello'), patch.object(app, 'gemini') as g:
            result = app.handler(event(question='Hi'), None)
            self.assertEqual(json.loads(result['body'])['provider'], 'bedrock'); g.assert_not_called()
    def test_fallback_exactly_once(self):
        with patch.object(app, 'reserve'), patch.object(app, 'bedrock', side_effect=app.ProviderUnavailable()) as b, patch.object(app, 'gemini', return_value='Hello') as g:
            result = app.handler(event(question='Hi'), None)
            self.assertEqual(json.loads(result['body'])['provider'], 'gemini')
            self.assertEqual(b.call_count, 1); self.assertEqual(g.call_count, 1)
    def test_gemini_primary_skips_bedrock(self):
        with patch.dict(os.environ, {'PRIMARY_PROVIDER': 'gemini'}), patch.object(app, 'reserve'), patch.object(app, 'bedrock') as b, patch.object(app, 'gemini', return_value='Hello') as g:
            result = app.handler(event(question='Hi'), None)
            self.assertEqual(json.loads(result['body'])['provider'], 'gemini')
            b.assert_not_called(); self.assertEqual(g.call_count, 1)
    def test_gemini_primary_failure_does_not_call_bedrock(self):
        with patch.dict(os.environ, {'PRIMARY_PROVIDER': 'gemini'}), patch.object(app, 'reserve'), patch.object(app, 'bedrock') as b, patch.object(app, 'gemini', side_effect=app.ProviderUnavailable()):
            result = app.handler(event(question='Hi'), None)
            self.assertEqual(result['statusCode'], 503)
            self.assertIn('Gemini is unavailable', result['body']); b.assert_not_called()
    def test_both_providers_down(self):
        with patch.object(app, 'reserve'), patch.object(app, 'bedrock', side_effect=app.ProviderUnavailable()), patch.object(app, 'gemini', side_effect=app.ProviderUnavailable()):
            self.assertEqual(app.handler(event(question='Hi'), None)['statusCode'], 503)
    def test_safety_refusal_does_not_fallback(self):
        with patch.object(app, 'reserve'), patch.object(app, 'bedrock', side_effect=app.SafetyBlocked()), patch.object(app, 'gemini') as g:
            self.assertEqual(app.handler(event(question='Hi'), None)['statusCode'], 422); g.assert_not_called()
    def test_retrieval_relevant_and_bounded(self):
        text = ('Gardening requires water. ' * 100) + '\n\n' + 'Lambda is the compute service used here.'
        result = app.passages(text, 'chat', 'What compute service is used?')
        self.assertTrue(any('Lambda' in x['text'] for x in result))
        self.assertLessEqual(sum(len(x['text']) for x in result), app.MAX_CONTEXT)
    def test_summary_covers_end_of_document(self):
        text = '\n\n'.join(f'Section {i}. ' + 'Facts. ' * 200 for i in range(30)) + ' END_OF_DOCUMENT'
        result = app.passages(text, 'summary', '')
        self.assertIn('END_OF_DOCUMENT', result[-1]['text'])
    def test_usage_transaction_has_both_limits(self):
        from unittest.mock import Mock
        ddb = Mock()
        with patch.object(app, 'client', return_value=ddb):
            app.reserve('person')
        tx = ddb.transact_write_items.call_args.kwargs['TransactItems']
        self.assertEqual(len(tx), 2)
        self.assertEqual(tx[0]['Update']['ExpressionAttributeValues'][':limit']['N'], '50')
    def test_usage_failure_closed(self):
        from unittest.mock import Mock
        ddb = Mock(); ddb.transact_write_items.side_effect = FakeCoreError()
        with patch.object(app, 'client', return_value=ddb):
            with self.assertRaises(app.RequestError) as exc:
                app.reserve('person')
            self.assertEqual(exc.exception.status, 503)
    def test_free_route_needs_no_login(self):
        e = {'routeKey': 'POST /free', 'body': json.dumps({'question': 'Hi'}), 'requestContext': {'http': {'sourceIp': '192.0.2.1'}}}
        with patch.object(app, 'reserve') as r, patch.object(app, 'bedrock', return_value='Hello'):
            self.assertEqual(app.handler(e, None)['statusCode'], 200)
            self.assertTrue(r.call_args.kwargs['anonymous'])
            self.assertNotIn('192.0.2.1', r.call_args.args[0])
    def test_free_route_requires_gateway_ip(self):
        e = {'routeKey': 'POST /free', 'body': json.dumps({'question': 'Hi', 'ip': '192.0.2.1'})}
        with patch.object(app, 'reserve') as r:
            self.assertEqual(app.handler(e, None)['statusCode'], 400); r.assert_not_called()
    def test_free_quota_has_global_tier_and_network_limits(self):
        from unittest.mock import Mock
        ddb=Mock()
        with patch.object(app, 'client', return_value=ddb): app.reserve('anon#test', anonymous=True)
        tx=ddb.transact_write_items.call_args.kwargs['TransactItems']
        limits=[x['Update']['ExpressionAttributeValues'][':limit']['N'] for x in tx]
        self.assertEqual(limits,['50','10','20'])
    def test_free_limits_are_configurable(self):
        from unittest.mock import Mock
        ddb=Mock()
        with patch.dict(os.environ, {'FREE_NETWORK_DAILY_LIMIT':'7','FREE_SHARED_DAILY_LIMIT':'15'}), patch.object(app,'client',return_value=ddb):
            app.reserve('anon#test',anonymous=True)
        tx=ddb.transact_write_items.call_args.kwargs['TransactItems']
        self.assertEqual([x['Update']['ExpressionAttributeValues'][':limit']['N'] for x in tx], ['50','7','15'])
    def test_quota_error_uses_configured_limits(self):
        from unittest.mock import Mock
        ddb=Mock(); ddb.transact_write_items.side_effect=FakeClientError('TransactionCanceledException')
        with patch.object(app,'client',return_value=ddb):
            with self.assertRaises(app.RequestError) as exc:app.reserve('anon#test',anonymous=True)
        self.assertIn('10 requests per network',exc.exception.message)
        self.assertIn('50-request',exc.exception.message)
    def test_general_chat_has_dedicated_gemini_instructions(self):
        with patch.dict(os.environ, {'PRIMARY_PROVIDER':'gemini'}), patch.object(app,'reserve'), patch.object(app,'gemini',return_value='AWS is a cloud platform.') as g:
            self.assertEqual(app.handler(event(question='What is AWS?'),None)['statusCode'],200)
        self.assertEqual(g.call_args.kwargs['system'],app.GENERAL_SYSTEM)
        self.assertNotIn('UNTRUSTED DOCUMENT EXCERPTS',g.call_args.args[0])
    def test_document_summary_keeps_grounding_instructions(self):
        with patch.object(app,'reserve'), patch.object(app,'bedrock',return_value='1. A [P1]') as b:
            self.assertEqual(app.handler(event(mode='summary',document='Lambda processes events and DynamoDB stores records.'),None)['statusCode'],200)
        self.assertEqual(b.call_args.kwargs['system'],app.DOCUMENT_SYSTEM)
        self.assertIn('UNTRUSTED DOCUMENT EXCERPTS',b.call_args.args[0])
    def test_blank_document_uses_general_instructions(self):
        with patch.object(app,'reserve'), patch.object(app,'bedrock',return_value='Hello') as b:
            app.handler(event(question='Hello',document='   '),None)
        self.assertEqual(b.call_args.kwargs['system'],app.GENERAL_SYSTEM)
    def test_document_entities_are_decoded_before_retrieval(self):
        with patch.object(app,'reserve'), patch.object(app,'bedrock',return_value='An event service [P1]') as b:
            result=app.handler(event(question='What is Lambda?',document='Lambda&#x20;processes events.'),None)
        self.assertNotIn('&#x20;',b.call_args.args[0])
        self.assertIn('Lambda processes events.',json.loads(result['body'])['citations'][0]['text'])
    def test_owner_kill_switch(self):
        with patch.dict(os.environ, {'APP_ENABLED': 'false'}), patch.object(app, 'bedrock') as b:
            self.assertEqual(app.handler(event(question='Hi'), None)['statusCode'], 503); b.assert_not_called()
    def test_gemini_disabled_never_fetches_key(self):
        with patch.dict(os.environ, {'GEMINI_FALLBACK_ENABLED': 'false'}), patch.object(app, 'client') as c:
            with self.assertRaises(app.ProviderUnavailable): app.gemini('Hi')
            c.assert_not_called()

class ModelIdentityTests(unittest.TestCase):
    def test_identity_uses_configured_gemini_after_success(self):
        with patch.dict(os.environ, {'PRIMARY_PROVIDER':'gemini','GEMINI_MODEL_ID':'gemini-test-model','APP_ENABLED':'true'}), patch.object(app,'reserve'), patch.object(app,'gemini',return_value='I am made by Google') as g:
            result=json.loads(app.handler(event(question='Which AI model is being used here?',document='Untrusted document'),None)['body'])
        self.assertEqual(result['modelId'],'gemini-test-model')
        self.assertIn('gemini-test-model',result['answer'])
        self.assertNotIn('made by Google',result['answer'])
        self.assertEqual(result['citations'],[])
        g.assert_called_once()
    def test_identity_follows_actual_fallback_provider(self):
        with patch.dict(os.environ, {'PRIMARY_PROVIDER':'bedrock','GEMINI_MODEL_ID':'gemini-fallback','APP_ENABLED':'true'}), patch.object(app,'reserve'), patch.object(app,'bedrock',side_effect=app.ProviderUnavailable), patch.object(app,'gemini',return_value='Hello'):
            result=json.loads(app.handler(event(question='What model are you using?'),None)['body'])
        self.assertEqual(result['provider'],'gemini')
        self.assertEqual(result['modelId'],'gemini-fallback')
        self.assertIn('gemini-fallback',result['answer'])
    def test_regular_document_questions_are_not_intercepted(self):
        for question in ['Which AI model is described in the document?', 'Explain model deployment', 'What is AWS?']:
            self.assertFalse(app.asks_model_identity(question))
    def test_runtime_provider_instructions(self):
        with patch.dict(os.environ, {'GEMINI_MODEL_ID':'gemini-example'}):
            self.assertIn('gemini-example',app.provider_system(app.DOCUMENT_SYSTEM,'gemini'))
            self.assertIn('independent application',app.provider_system(app.GENERAL_SYSTEM,'gemini'))

class OutputBudgetTests(unittest.TestCase):
    def test_both_providers_send_new_output_budget(self):
        from unittest.mock import Mock
        provider = Mock()
        provider.converse.return_value = {'output': {'message': {'content': [{'text': 'Hello'}]}}}
        with patch.object(app, '_circuit_until', 0), patch.object(app, 'client', return_value=provider), patch.object(app, 'MAX_OUTPUT', 1024):
            app.bedrock('Hi')
            self.assertEqual(provider.converse.call_args.kwargs['inferenceConfig']['maxTokens'], 1024)
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = json.dumps({'candidates': [{'content': {'parts': [{'text': 'Hello'}]}}]}).encode()
        with patch.dict(os.environ, {'PRIMARY_PROVIDER': 'gemini'}), patch.object(app, '_key', 'fake-key'), patch.object(app, 'MAX_OUTPUT', 1024), patch.object(app.urllib.request, 'urlopen', return_value=response) as request:
            self.assertEqual(app.gemini('Hi'), 'Hello')
            payload = json.loads(request.call_args.args[0].data)
            self.assertEqual(payload['generationConfig']['maxOutputTokens'], 1024)
    def test_higher_free_limits_keep_all_atomic_counters(self):
        from unittest.mock import Mock
        ddb=Mock()
        with patch.dict(os.environ, {'USAGE_TABLE':'test', 'GLOBAL_DAILY_LIMIT':'100','FREE_NETWORK_DAILY_LIMIT':'50','FREE_SHARED_DAILY_LIMIT':'100'}), patch.object(app,'client',return_value=ddb):
            app.reserve('test-network', anonymous=True)
        tx=ddb.transact_write_items.call_args.kwargs['TransactItems']
        self.assertEqual([x['Update']['ExpressionAttributeValues'][':limit']['N'] for x in tx],['100','50','100'])

if __name__ == '__main__':
    unittest.main()
