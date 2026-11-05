"""Owner-only migration: assign one existing S3 document to a department, then sync."""
import argparse, json, uuid
import boto3
from botocore.exceptions import ClientError
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--key',required=True,help='Exact S3 object key, not an s3:// URL')
p.add_argument('--department',required=True,choices=['hr','cloud','genai'])
p.add_argument('--region',default='us-east-1')
a=p.parse_args()
session=boto3.Session(region_name=a.region)
if session.client('sts').get_caller_identity()['Account']!='912010732788':raise SystemExit('Wrong AWS account.')
if a.key.endswith('/') or a.key.endswith('.metadata.json'):raise SystemExit('Select a document, not a folder or metadata sidecar.')
bucket='thinkingai-datasourse-bucket';s3=session.client('s3')
head=s3.head_object(Bucket=bucket,Key=a.key)
outputs=session.client('cloudformation').describe_stacks(StackName='thinking-ai-knowledge')['Stacks'][0]['Outputs']
table_name=next(x['OutputValue'] for x in outputs if x['OutputKey']=='DocumentTable')
table=session.resource('dynamodb').Table(table_name)
try:metadata=json.loads(s3.get_object(Bucket=bucket,Key=a.key+'.metadata.json')['Body'].read())
except ClientError as e:
 if e.response['Error']['Code'] not in ('NoSuchKey','404'):raise
 metadata={'metadataAttributes':{}}
attrs=metadata.setdefault('metadataAttributes',{})
ident=attrs.get('documentId') or uuid.uuid4().hex
if not isinstance(ident,str) or not ident:raise SystemExit('Existing documentId is invalid; review the sidecar first.')
existing=table.get_item(Key={'pk':'DOC#'+ident},ConsistentRead=True).get('Item')
if existing and (existing.get('department')!=a.department or existing.get('key')!=a.key or existing.get('status')!='ACTIVE'):
 raise SystemExit('Existing catalog assignment conflicts or was deleted. No changes made; use a new approved upload instead.')
attrs.update(department=a.department,documentId=ident)
body=json.dumps(metadata).encode()
if len(body)>1024:raise SystemExit('Metadata exceeds the conservative 1 KB S3 Vectors metadata budget; review its existing fields.')
s3.put_object(Bucket=bucket,Key=a.key+'.metadata.json',Body=body,ContentType='application/json')
table.put_item(Item={'pk':'DOC#'+ident,'id':ident,'name':a.key.rsplit('/',1)[-1],'department':a.department,'key':a.key,'size':head['ContentLength'],'status':'ACTIVE'},ConditionExpression='attribute_not_exists(pk) OR (#s = :active AND department = :dept AND #k = :key)',ExpressionAttributeNames={'#s':'status','#k':'key'},ExpressionAttributeValues={':active':'ACTIVE',':dept':a.department,':key':a.key})
try:
 job=session.client('bedrock-agent').start_ingestion_job(knowledgeBaseId='5KIGBYRICE',dataSourceId='VPS3UHQOQC')['ingestionJob']
 print('Assigned document to',a.department,'— sync:',job['ingestionJobId'],job['status'])
except ClientError as e:
 if e.response['Error']['Code']!='ConflictException':raise
 print('Assignment saved. An indexing job is running; click Sync knowledge base in the admin portal after it finishes.')
