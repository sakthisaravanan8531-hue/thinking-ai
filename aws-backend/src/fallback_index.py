"""Bounded text indexing and keyword retrieval. No embeddings or model calls."""
import io,json,os,re,time,uuid,zipfile,math,difflib
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from botocore.exceptions import ClientError,BotoCoreError
MAX_BYTES=50*1024*1024
MAX_TEXT=250_000
MAX_PAGES=250
STOP=set('a an the and or to of for in on at is are was were be what which how why please explain tell me about this that it do does document documents previous questions current question'.split())

def enabled():return os.environ.get('DOCUMENT_FALLBACK_ENABLED')=='true'
def index_key(ident):return 'text-index/'+ident+'.json'
def active_documents(dept=None):
    import app
    args={'FilterExpression':'begins_with(pk, :prefix) AND #s = :active',
          'ExpressionAttributeNames':{'#s':'status'},'ExpressionAttributeValues':{':prefix':'DOC#',':active':'ACTIVE'},'ConsistentRead':True}
    if dept:
        args['FilterExpression']+=' AND department = :department';args['ExpressionAttributeValues'][':department']=dept
    result=[];scanned=0
    while True:
        page=app.table().scan(**args);result.extend(page.get('Items',[]));scanned+=page.get('ScannedCount',0)
        if len(result)>50 or scanned>5000:raise app.RequestError(503,'Fallback search supports up to 50 active documents in this scope. Narrow the document set or use Bedrock.')
        if not page.get('LastEvaluatedKey'):return result
        args['ExclusiveStartKey']=page['LastEvaluatedKey']

def schedule(ids,force=False):
    import app
    if not enabled():return {'queued':0,'message':'Document fallback is not enabled.'}
    if len(ids)>50 or any(not isinstance(ident,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}',ident) for ident in ids):raise app.RequestError(400,'Index up to 50 valid document IDs at a time.')
    docs=[];now=int(time.time())
    for ident in dict.fromkeys(ids):
        doc=app.doc_get(ident)
        if not doc or doc.get('status')!='ACTIVE':continue
        if doc.get('fallbackStatus') in ('QUEUED','INDEXING') and int(doc.get('fallbackUpdated',0))>now-300:continue
        if doc.get('fallbackStatus') in ('READY','PARTIAL') and not force:continue
        docs.append(doc)
    queued=0
    for start in range(0,len(docs),10):
        batch=docs[start:start+10];day=time.strftime('%Y-%m-%d',time.gmtime());job=uuid.uuid4().hex
        try:
            app.client('dynamodb').update_item(TableName=os.environ['USAGE_TABLE'],Key={'pk':{'S':day+'#fallback-index-jobs'}},
             UpdateExpression='SET expires_at = :ttl ADD used :one',ConditionExpression='attribute_not_exists(used) OR used < :limit',
             ExpressionAttributeValues={':ttl':{'N':str(now+259200)},':one':{'N':'1'},':limit':{'N':os.environ.get('INDEX_DAILY_LIMIT','20')}})
        except (ClientError,BotoCoreError):
            return {'queued':queued,'message':'Daily indexing allowance reached or usage control unavailable. No more jobs were queued.'}
        accepted=[]
        for doc in batch:
            try:
                app.table().update_item(Key={'pk':'DOC#'+doc['id']},UpdateExpression='SET fallbackStatus = :queued, fallbackJob = :job, fallbackUpdated = :now',
                 ConditionExpression='#s = :active AND (attribute_not_exists(fallbackUpdated) OR fallbackUpdated < :stale OR (fallbackStatus <> :queued AND fallbackStatus <> :indexing))',
                 ExpressionAttributeNames={'#s':'status'},ExpressionAttributeValues={':queued':'QUEUED',':indexing':'INDEXING',':active':'ACTIVE',':job':job,':now':now,':stale':now-300})
                accepted.append(doc['id'])
            except ClientError as exc:
                if exc.response['Error']['Code']!='ConditionalCheckFailedException':raise
        if not accepted:continue
        try:
            result=app.client('lambda').invoke(FunctionName=os.environ['FALLBACK_INDEX_FUNCTION'],InvocationType='Event',Payload=json.dumps({'jobId':job,'documentIds':accepted}).encode())
            if result.get('StatusCode')!=202:raise RuntimeError('Index worker not accepted')
            queued+=len(accepted)
        except Exception:
            for ident in accepted:
                _set_state(ident,job,'FAILED','QUEUE_FAILED')
            return {'queued':queued,'message':'Some indexing jobs could not be queued. Retry after checking the worker.'}
    return {'queued':queued,'message':str(queued)+' document copies queued for fallback text indexing. Refresh documents to check progress.'}

def _set_state(ident,job,state,error='',extra=None):
    import app
    values={':state':state,':now':int(time.time()),':error':error,':job':job,':active':'ACTIVE'}
    expression='SET fallbackStatus = :state, fallbackUpdated = :now, fallbackError = :error'
    names={'#s':'status'}
    for i,(key,value) in enumerate((extra or {}).items()):
        names['#f'+str(i)]=key;values[':v'+str(i)]=value;expression+=', #f'+str(i)+' = :v'+str(i)
    try:
        app.table().update_item(Key={'pk':'DOC#'+ident},UpdateExpression=expression,ConditionExpression='#s = :active AND fallbackJob = :job',ExpressionAttributeNames=names,ExpressionAttributeValues=values)
        return True
    except ClientError as exc:
        if exc.response['Error']['Code']!='ConditionalCheckFailedException':raise
        return False

def chunks_from_bytes(raw,name):
    suffix=name.rsplit('.',1)[-1].lower();parts=[];used=0;partial=False
    def add(text,page=None):
        nonlocal used,partial
        text=re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]',' ',text)
        remaining=MAX_TEXT-used
        if len(text)>remaining:partial=True
        text=text[:remaining];used+=len(text)
        for start in range(0,len(text),1100):
            chunk=text[start:start+1200].strip()
            if chunk:parts.append({'text':chunk,**({'page':page} if page else {})})
    if suffix in ('txt','md'):
        add(raw.decode('utf-8-sig'))
    elif suffix=='pdf':
        from pypdf import PdfReader
        pdf=PdfReader(io.BytesIO(raw),strict=False)
        if pdf.is_encrypted:raise ValueError('ENCRYPTED_PDF')
        partial=len(pdf.pages)>MAX_PAGES
        for i,page in enumerate(pdf.pages):
            if i>=MAX_PAGES or used>=MAX_TEXT:partial=True;break
            # Avoid a pathological single decompressed PDF content stream.
            contents=page.get_contents()
            if contents and len(contents.get_data())>20*1024*1024:raise ValueError('PDF_PAGE_TOO_COMPLEX')
            add(page.extract_text() or '',i+1)
    elif suffix=='docx':
        from defusedxml import ElementTree
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            info=archive.getinfo('word/document.xml')
            if info.file_size>20*1024*1024:raise ValueError('DOCX_XML_TOO_LARGE')
            root=ElementTree.fromstring(archive.read(info))
            namespace={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
            paragraphs=[]
            for paragraph in root.findall('.//w:p',namespace):
                paragraphs.append(''.join(n.text or '' for n in paragraph.findall('.//w:t',namespace)))
            add('\n'.join(paragraphs))
    else:raise ValueError('UNSUPPORTED_FORMAT')
    if not parts:raise ValueError('NO_READABLE_TEXT_OCR_MAY_BE_REQUIRED')
    return parts,partial

def handler(event,context):
    import app
    ids=event.get('documentIds',[]);job=event.get('jobId','')
    if not isinstance(ids,list) or not 1<=len(ids)<=10 or not re.fullmatch(r'[a-f0-9]{32}',job):return {'error':'INVALID_JOB'}
    s3=app.client('s3');cache={};completed=0
    for ident in ids:
        if not isinstance(ident,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}',ident):continue
        if context and context.get_remaining_time_in_millis()<12000:
            _set_state(ident,job,'FAILED','WORKER_TIME_BUDGET');continue
        doc=app.doc_get(ident)
        if not doc or doc.get('status')!='ACTIVE' or doc.get('fallbackJob')!=job:continue
        try:
            app.table().update_item(Key={'pk':'DOC#'+ident},UpdateExpression='SET fallbackStatus = :running',
              ConditionExpression='#s = :active AND fallbackJob = :job AND fallbackStatus = :queued',ExpressionAttributeNames={'#s':'status'},
              ExpressionAttributeValues={':active':'ACTIVE',':job':job,':queued':'QUEUED',':running':'INDEXING'})
        except ClientError as exc:
            if exc.response['Error']['Code']=='ConditionalCheckFailedException':continue
            raise
        try:
            head=s3.head_object(Bucket=os.environ['DOCUMENT_BUCKET'],Key=doc['key']);etag=head['ETag']
            if not 1<=head['ContentLength']<=MAX_BYTES:raise ValueError('INVALID_SOURCE_SIZE')
            cache_id=(etag,doc['name'].rsplit('.',1)[-1].lower())
            if cache_id not in cache:
                source=s3.get_object(Bucket=os.environ['DOCUMENT_BUCKET'],Key=doc['key'])
                if source['ETag']!=etag:raise ValueError('SOURCE_CHANGED')
                try:raw=source['Body'].read(MAX_BYTES+1)
                finally:source['Body'].close()
                if len(raw)>MAX_BYTES:raise ValueError('SOURCE_TOO_LARGE')
                cache.clear()  # Keep only one extracted file in worker memory.
                cache[cache_id]=chunks_from_bytes(raw,doc['name'])
                del raw
            chunks,partial=cache[cache_id]
            if s3.head_object(Bucket=os.environ['DOCUMENT_BUCKET'],Key=doc['key'])['ETag']!=etag:raise ValueError('SOURCE_CHANGED')
            index={'version':1,'documentId':ident,'department':doc['department'],'sourceKey':doc['key'],'sourceETag':etag,'chunks':chunks,'partial':partial}
            s3.put_object(Bucket=os.environ['FALLBACK_INDEX_BUCKET'],Key=index_key(ident),Body=json.dumps(index).encode(),ContentType='application/json')
            committed=_set_state(ident,job,'PARTIAL' if partial else 'READY',extra={'fallbackETag':etag})
            if committed is False:
                current=app.doc_get(ident)
                if not current or current.get('status')=='DELETED':s3.delete_object(Bucket=os.environ['FALLBACK_INDEX_BUCKET'],Key=index_key(ident))
                continue
            completed+=1
        except Exception as exc:
            # Error type/code only, never extracted text or provider error bodies.
            allowed_errors={'ENCRYPTED_PDF','PDF_PAGE_TOO_COMPLEX','DOCX_XML_TOO_LARGE','UNSUPPORTED_FORMAT','NO_READABLE_TEXT_OCR_MAY_BE_REQUIRED','SOURCE_CHANGED','SOURCE_TOO_LARGE','INVALID_SOURCE_SIZE'}
            code=str(exc) if isinstance(exc,ValueError) and str(exc) in allowed_errors else type(exc).__name__
            _set_state(ident,job,'FAILED',code)
            print(json.dumps({'error':'fallback_index_failed','documentId':ident,'errorCode':code}))
    return {'completed':completed}

def words(text):
    text=re.sub(r'\biaac\b','iac',text,flags=re.I)
    text=re.sub(r'\b(?:postgre\s*sql|postgesql|postgrsql|postgsql|postgres|postgre)\b','postgresql',text.lower())
    text=re.sub(r'\bex(?:ercise)?\s*[-:]?\s*(\d+)\b',r'exercise\1',text.lower())
    return [w for w in re.findall(r'[a-z0-9]+',text) if len(w)>1 and w not in STOP]

def matching_term(word, vocabulary):
    if word in vocabulary:return word
    # Short identifiers (S3, IAM, etc.) must match exactly. Longer typos
    # require one clear, highly similar word from the authorized source.
    if len(word)<5:return None
    choices=difflib.get_close_matches(word,vocabulary,n=2,cutoff=.84)
    if not choices:return None
    first=difflib.SequenceMatcher(None,word,choices[0]).ratio()
    if len(choices)>1 and first-difflib.SequenceMatcher(None,word,choices[1]).ratio()<.05:return None
    return choices[0]

def search(question,department):
    import app
    docs=active_documents(department)
    if not docs:return [],False
    s3=app.client('s3');query=Counter(words(question));unavailable=0
    def read(doc):
        if doc.get('fallbackStatus') not in ('READY','PARTIAL'):return [],True,False
        try:
            head=s3.head_object(Bucket=os.environ['DOCUMENT_BUCKET'],Key=doc['key'])
            response=s3.get_object(Bucket=os.environ['FALLBACK_INDEX_BUCKET'],Key=index_key(doc['id']))
            try:index=json.loads(response['Body'].read(2_000_000))
            finally:response['Body'].close()
            if not isinstance(index,dict) or index.get('version')!=1 or not isinstance(index.get('chunks'),list) or index.get('documentId')!=doc['id'] or index.get('department')!=department or index.get('sourceKey')!=doc['key'] or index.get('sourceETag')!=head['ETag']:return [],True,False
            ranked=[]
            name_tokens=set(words(doc['name']))
            for chunk in index.get('chunks',[]):
                if not isinstance(chunk,dict):continue
                text=chunk.get('text','')
                if not isinstance(text,str) or len(text)>1400:continue
                terms=Counter(words(text));score=0
                for word in query:
                    matched=matching_term(word,terms)
                    if matched:score+=(1+math.log(terms[matched]))*(1 if matched==word else .8)
                    elif word in name_tokens:score+=.25
                if score>0:ranked.append((score,{'text':text,'name':doc['name'],'documentId':doc['id'],**({'page':chunk['page']} if chunk.get('page') else {})}))
            return sorted(ranked,key=lambda x:-x[0])[:6],False,bool(index.get('partial'))
        except (ClientError,BotoCoreError,ValueError,KeyError,TypeError):return [],True,False
    ranked=[];partial=False
    with ThreadPoolExecutor(max_workers=6) as executor:
        for found,missing,truncated in executor.map(read,docs):ranked.extend(found);unavailable+=int(missing);partial=partial or truncated
    if unavailable==len(docs):raise app.RequestError(409,'Fallback text indexing is pending or unavailable. Ask your administrator to build or refresh the fallback index.')
    out=[];used=0
    for _,passage in sorted(ranked,key=lambda x:-x[0])[:6]:
        passage={**passage,'id':'D'+str(len(out)+1)};used+=len(passage['text'])
        if used>12000:break
        out.append(passage)
    return out,partial or unavailable>0
