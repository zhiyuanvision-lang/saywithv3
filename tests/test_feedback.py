import io
from PIL import Image
from test_backend import application,client,register

def image(client,h):
    out=io.BytesIO();Image.new('RGB',(10,10),'white').save(out,format='JPEG')
    r=client.post('/v1/feedback/images',headers=h,files={'file':('test.jpg',out.getvalue(),'image/jpeg')})
    assert r.status_code==201,r.text
    return r.json()['url']

def test_feedback_inbox_idempotency_ownership_reply_and_close(client,application):
    h,_=register(client);other,_=register(client);ref=image(client,h)
    assert image(client,h)==ref
    body={'category':'speak','content':'新版反馈闭环测试','contact':'','images':[ref],'app_version':'1.0.6'}
    submit={**h,'Idempotency-Key':'ticket-one'}
    r=client.post('/v1/feedback',headers=submit,json=body);assert r.status_code==201,r.text
    ticket=r.json();id=ticket['id'];assert ticket['images'][0].endswith(ref)
    assert client.post('/v1/feedback',headers=submit,json=body).json()['id']==id
    assert len(client.get('/v1/feedback/mine',headers=h).json()['items'])==1
    assert client.get('/v1/feedback/'+id,headers=other).status_code==404
    assert client.post('/v1/feedback',headers=submit,json={**body,'content':'changed'}).status_code==409
    assert client.post('/v1/feedback',headers={**other,'Idempotency-Key':'other'},json=body).status_code==404
    reply={**h,'Idempotency-Key':'reply-one'}
    assert client.post('/v1/feedback/'+id+'/messages',headers=reply,json={'content':'补充问题'}).status_code==200
    assert len(client.post('/v1/feedback/'+id+'/messages',headers=reply,json={'content':'补充问题'}).json()['messages'])==2
    svc=application.state.services
    from sqlalchemy import insert,update
    from datetime import datetime,timezone
    with svc.feedback.engine.begin() as c:
        c.execute(insert(svc.feedback.messages).values(id='support-one',feedback_id=id,sender_type='support',sender_name='小帆团队',content='已收到',images=[],created_at=datetime.now(timezone.utc)))
        c.execute(update(svc.feedback.tickets).where(svc.feedback.tickets.c.id==id).values(reply='已收到',status='replied'))
    assert client.get('/v1/feedback/'+id,headers=h).json()['messages'][-1]['content']=='已收到'
    assert client.post('/v1/feedback/'+id+'/close',headers=h).json()['status']=='closed'
    assert client.post('/v1/feedback/'+id+'/messages',headers={**h,'Idempotency-Key':'reply-two'},json={'content':'after-close'}).status_code==409

def test_feedback_invalid_images_and_empty_requests(client):
    h,_=register(client)
    assert client.post('/v1/feedback',headers={**h,'Idempotency-Key':'empty'},json={}).status_code==422
    assert client.post('/v1/feedback/images',headers=h,files={'file':('fake.jpg',b'not-image','image/jpeg')}).status_code==422
    assert client.post('/v1/feedback/images',headers=h,files={'file':('huge.jpg',b'x'*(2*1024*1024+1),'image/jpeg')}).status_code==413
    assert client.get('/v1/feedback/mine').status_code==401
