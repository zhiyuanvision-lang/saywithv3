"""Adapter to the existing SayWith feedback inbox; no access to account tables.
Production uses a dedicated database role. Fixture tests use separate local tables.
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import create_engine, MetaData, Table, Column, String, DateTime, JSON, select, insert, update
from sqlalchemy.dialects.postgresql import ARRAY
from .store import Missing, Conflict

class Feedback:
    def __init__(self, settings, store):
        self.store=store; self.settings=settings
        if settings.feedback_database_url:
            self.engine=create_engine(settings.feedback_database_url,pool_pre_ping=True)
            meta=MetaData()
            self.tickets=Table('feedbacks',meta,autoload_with=self.engine)
            self.messages=Table('feedback_messages',meta,autoload_with=self.engine)
        elif settings.mode=='fixture':
            self.engine=store.engine; meta=MetaData()
            self.tickets=Table('feedbacks',meta,*[Column(k,String,primary_key=k=='id') for k in
                ('id','user_id','reporter_name','contact','source','category','content','app_version','status','reply')],
                Column('created_at',DateTime(timezone=True)),Column('replied_at',DateTime(timezone=True)))
            self.messages=Table('feedback_messages',meta,*[Column(k,String,primary_key=k=='id') for k in
                ('id','feedback_id','sender_type','sender_name','content')],Column('images',JSON().with_variant(ARRAY(String),'postgresql')),Column('created_at',DateTime(timezone=True)))
            meta.create_all(self.engine)
        else:
            self.engine=None

    def ready(self):
        if self.engine is None: raise ValueError('意见反馈服务尚未配置')

    def get(self,owner,id,conn=None):
        self.ready()
        if conn is None:
            with self.engine.connect() as c:return self.get(owner,id,c)
        row=conn.execute(select(self.tickets).where(self.tickets.c.id==id,self.tickets.c.user_id=='learning:'+owner)).mappings().first()
        if not row:raise Missing('feedback')
        result=dict(row)
        result['messages']=[dict(m) for m in conn.execute(select(self.messages).where(self.messages.c.feedback_id==id).order_by(self.messages.c.created_at)).mappings()]
        result['images']=result['messages'][0]['images'] if result['messages'] else []
        return result

    def mine(self,owner):
        self.ready()
        with self.engine.connect() as c:
            ids=c.execute(select(self.tickets.c.id).where(self.tickets.c.user_id=='learning:'+owner).order_by(self.tickets.c.created_at.desc()).limit(100)).scalars().all()
            return {'items':[self.get(owner,id,c) for id in ids]}

    def images(self,owner,images):
        refs=[]
        for ref in images:
            id=ref.removeprefix('/v1/feedback/images/')
            if ref!='/v1/feedback/images/'+id or len(id)!=32:raise ValueError('无效的反馈图片')
            self.store.get('FeedbackImage',id,owner)
            refs.append(self.settings.feedback_public_base.rstrip('/')+ref)
        return refs

    def create(self,owner,key,data):
        self.ready();images=self.images(owner,data['images']);content=data['content'].strip()
        if not content and not images:raise ValueError('请填写反馈内容或添加图片')
        id=uuid.uuid5(uuid.NAMESPACE_URL,'saywith-feedback:'+owner+':'+key).hex
        expected={'content':content or '（图片反馈）','contact':data['contact'].strip(),'category':data['category'],
                  'app_version':data['app_version'],'images':images}
        with self.engine.begin() as c:
            if self.engine.dialect.name=='postgresql':
                from sqlalchemy import text
                c.execute(text('SELECT pg_advisory_xact_lock(:key)'),{'key':int(id[:15],16)})
            existing=c.execute(select(self.tickets.c.id).where(self.tickets.c.id==id)).first()
            if existing:
                ticket=self.get(owner,id,c)
                if any(ticket[k]!=v for k,v in expected.items()):raise Conflict('提交标识已用于另一条反馈')
                return ticket
            now=datetime.now(timezone.utc)
            c.execute(insert(self.tickets).values(id=id,user_id='learning:'+owner,reporter_name='新版学习者',source='ios',
                content=expected['content'],contact=expected['contact'],category=expected['category'],app_version=expected['app_version'],
                status='open',reply='',created_at=now))
            c.execute(insert(self.messages).values(id=id,feedback_id=id,sender_type='user',sender_name='我',content=expected['content'],images=images,created_at=now))
            return self.get(owner,id,c)

    def reply(self,owner,id,key,data):
        self.ready();images=self.images(owner,data['images']);content=data['content'].strip()
        if not content and not images:raise ValueError('请填写回复或添加图片')
        mid=uuid.uuid5(uuid.NAMESPACE_URL,'saywith-reply:'+owner+':'+id+':'+key).hex
        with self.engine.begin() as c:
            if self.engine.dialect.name=='postgresql':
                c.execute(select(self.tickets.c.id).where(self.tickets.c.id==id,self.tickets.c.user_id=='learning:'+owner).with_for_update()).first()
            ticket=self.get(owner,id,c)
            old=c.execute(select(self.messages).where(self.messages.c.id==mid)).mappings().first()
            if old:
                if old['content']!=content or old['images']!=images:raise Conflict('回复标识已被使用')
                return ticket
            if ticket['status']=='closed':raise Conflict('这条反馈已结束')
            c.execute(insert(self.messages).values(id=mid,feedback_id=id,sender_type='user',sender_name='我',content=content,images=images,created_at=datetime.now(timezone.utc)))
            c.execute(update(self.tickets).where(self.tickets.c.id==id).values(status='open'))
            return self.get(owner,id,c)

    def close(self,owner,id):
        self.ready()
        with self.engine.begin() as c:
            if self.engine.dialect.name=='postgresql':
                c.execute(select(self.tickets.c.id).where(self.tickets.c.id==id,self.tickets.c.user_id=='learning:'+owner).with_for_update()).first()
            self.get(owner,id,c)
            c.execute(update(self.tickets).where(self.tickets.c.id==id).values(status='closed'))
            return self.get(owner,id,c)
