"""SQLAlchemy persistence; CAS versions support SQLite locally and PostgreSQL workers."""
import hashlib
import json
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from sqlalchemy import (create_engine, MetaData, Table, Column, String, Integer, Float,
                        JSON, UniqueConstraint, select, update, insert, text)
from sqlalchemy.exc import IntegrityError

def uid(): return str(uuid.uuid4())
def digest(value): return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

class Conflict(Exception): pass
class Missing(Exception): pass

class Store:
    def __init__(self, url):
        if url.startswith('sqlite:///') and ':memory:' not in url:
            Path(url.removeprefix('sqlite:///')).parent.mkdir(parents=True,exist_ok=True)
        options={'connect_args':{'check_same_thread':False,'timeout':30}} if url.startswith('sqlite') else {}
        self.engine=create_engine(url,**options)
        self.meta=MetaData()
        self.docs=Table('documents',self.meta,
            Column('kind',String,primary_key=True),Column('id',String,primary_key=True),
            Column('owner',String,nullable=False),Column('version',Integer,nullable=False),
            Column('payload',JSON,nullable=False),Column('created_at',Float,nullable=False))
        self.users=Table('users',self.meta,Column('id',String,primary_key=True),
            Column('token_hash',String,unique=True,nullable=False),Column('created_at',Float,nullable=False))
        self.identities=Table('account_identities',self.meta,
            Column('external_id',String,primary_key=True),Column('owner',String,unique=True,nullable=False))
        self.auth_sessions=Table('account_sessions',self.meta,
            Column('access_hash',String,primary_key=True),Column('refresh_hash',String,unique=True,nullable=False),
            Column('owner',String,nullable=False),Column('expires_at',Float,nullable=False))
        self.jobs=Table('generation_jobs',self.meta,
            Column('id',String,primary_key=True),Column('owner',String,nullable=False),
            Column('key',String,nullable=False),Column('request_hash',String,nullable=False),
            Column('payload',JSON,nullable=False),Column('state',String,nullable=False),
            Column('version',Integer,nullable=False),Column('attempts',Integer,nullable=False),
            Column('lease',String),Column('lease_until',Float),Column('ready_at',Float,nullable=False),
            UniqueConstraint('owner','key'))
        self.events=Table('outbox_events',self.meta,Column('id',String,primary_key=True),
            Column('key',String,unique=True,nullable=False),Column('payload',JSON,nullable=False),
            Column('created_at',Float,nullable=False))
        with self.engine.begin() as conn:
            if self.engine.dialect.name=='postgresql':conn.execute(text('SELECT pg_advisory_xact_lock(73632103)'))
            self.meta.create_all(conn)

    @contextmanager
    def transaction(self):
        with self.engine.begin() as conn: yield conn

    def get(self,kind,id,owner=None,conn=None):
        if conn is None:
            with self.engine.connect() as c: return self.get(kind,id,owner,c)
        query=select(self.docs).where(self.docs.c.kind==kind,self.docs.c.id==id)
        if owner is not None: query=query.where(self.docs.c.owner==owner)
        row=conn.execute(query).mappings().first()
        if not row: raise Missing(kind)
        return dict(row)

    def list(self,kind,owner=None,conn=None):
        if conn is None:
            with self.engine.connect() as c:return self.list(kind,owner,c)
        q=select(self.docs).where(self.docs.c.kind==kind)
        if owner is not None:q=q.where(self.docs.c.owner==owner)
        return [dict(x) for x in conn.execute(q).mappings()]

    def put(self,kind,id,owner,payload,expected=None,conn=None):
        if conn is None:
            with self.transaction() as c:return self.put(kind,id,owner,payload,expected,c)
        if expected is None:
            conn.execute(insert(self.docs).values(kind=kind,id=id,owner=owner,version=1,payload=payload,created_at=time.time()))
            return 1
        result=conn.execute(update(self.docs).where(self.docs.c.kind==kind,self.docs.c.id==id,
            self.docs.c.owner==owner,self.docs.c.version==expected).values(payload=payload,version=expected+1))
        if result.rowcount != 1:raise Conflict('Concurrent update; reload latest version')
        return expected+1

    def create_job(self,owner,key,request):
        hash=digest(request)
        with self.transaction() as c:
            row=c.execute(select(self.jobs).where(self.jobs.c.owner==owner,self.jobs.c.key==key)).mappings().first()
            if row:
                if row['request_hash']!=hash:raise Conflict('Idempotency key used for a different request')
                return dict(row)
            # Serialize per-user admission, including concurrent requests on different keys.
            c.execute(update(self.users).where(self.users.c.id==owner).values(created_at=self.users.c.created_at))
            active=c.execute(select(self.jobs.c.id).where(self.jobs.c.owner==owner,
                ~self.jobs.c.state.in_(['approved','preview_ready','failed','cancelled','needs_review']))).all()
            if len(active)>=3:raise Conflict('已有三个生成任务，请等待或取消')
            id=uid(); payload={'request':request,'created_at':time.time()}
            try:
                # A savepoint preserves the transaction after a competing insert.
                with c.begin_nested():
                    c.execute(insert(self.jobs).values(id=id,owner=owner,key=key,request_hash=hash,payload=payload,
                        state='queued',version=1,attempts=0,ready_at=time.time()))
            except IntegrityError:
                row=c.execute(select(self.jobs).where(self.jobs.c.owner==owner,self.jobs.c.key==key)).mappings().one()
                if row['request_hash']!=hash:raise Conflict('Idempotency key conflict')
                return dict(row)
            return dict(c.execute(select(self.jobs).where(self.jobs.c.id==id)).mappings().one())

    def job(self,id,owner=None,conn=None):
        if conn is None:
            with self.engine.connect() as c:return self.job(id,owner,c)
        q=select(self.jobs).where(self.jobs.c.id==id)
        if owner is not None:q=q.where(self.jobs.c.owner==owner)
        row=conn.execute(q).mappings().first()
        if not row:raise Missing('job')
        return dict(row)

    def claim(self,worker,seconds=900):
        now=time.time()
        with self.transaction() as c:
            q=select(self.jobs).where(~self.jobs.c.state.in_(['approved','preview_ready','failed','cancelled','needs_review']),
                self.jobs.c.ready_at<=now,(self.jobs.c.lease_until.is_(None)|(self.jobs.c.lease_until<now)))
            if self.engine.dialect.name=='postgresql':q=q.with_for_update(skip_locked=True)
            for row in c.execute(q.limit(10)).mappings():
                r=c.execute(update(self.jobs).where(self.jobs.c.id==row['id'],self.jobs.c.version==row['version']).values(
                    lease=worker,lease_until=now+seconds,version=row['version']+1,attempts=row['attempts']+1))
                if r.rowcount:return self.job(row['id'],conn=c)
        return None

    def advance(self,row,state,payload,conn=None,release=False,delay=0):
        if conn is None:
            with self.transaction() as c:return self.advance(row,state,payload,c,release,delay)
        r=conn.execute(update(self.jobs).where(self.jobs.c.id==row['id'],self.jobs.c.version==row['version'],
            self.jobs.c.lease==row['lease'],self.jobs.c.lease_until>time.time()).values(
                state=state,payload=payload,version=row['version']+1,ready_at=time.time()+delay,
                lease=None if release else row['lease'],lease_until=None if release else time.time()+900))
        if r.rowcount!=1:raise Conflict('Expired lease or cancelled job')
        return self.job(row['id'],conn=conn)

    def cancel(self,id,owner):
        with self.transaction() as c:
            row=self.job(id,owner,c)
            if row['state'] in ('approved','preview_ready','failed','needs_review'):raise Conflict('Job already finished')
            if row['state']=='cancelled':return row
            r=c.execute(update(self.jobs).where(self.jobs.c.id==id,self.jobs.c.version==row['version']).values(
                state='cancelled',lease=None,lease_until=None,version=row['version']+1))
            if not r.rowcount:raise Conflict('Job changed')
            return self.job(id,owner,c)

    def emit(self,key,payload,conn):
        conn.execute(insert(self.events).values(id=uid(),key=key,payload=payload,created_at=time.time()))
