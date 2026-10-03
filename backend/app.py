import asyncio
import hashlib
import logging
import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated
from fastapi import FastAPI, Depends, Header, HTTPException, UploadFile, File, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import insert, select
from modules.curriculum import CurriculumRepository
from .config import Settings
from .store import Store, uid, Missing, Conflict
from .contracts import LearnerProfile, LearnerInput, SourceCatalog, TargetDefinition, CONTRACTS
from .curriculum import CurriculumService
from .planning import Planner, STAGES
from .providers import FixtureProvider, ProviderFailure, ReviewRequired
from .byte_speech import DeepSeekByteProvider, wav_info
from .generation import Generator
from .assessment import Assessor
from .sessions import Sessions

class InputModel(BaseModel):model_config=ConfigDict(extra='forbid')
class Preferences(InputModel):
    context: str = Field(default='校园与日常生活',max_length=200)
    interests: list[str] = Field(default_factory=list,max_length=10)
    reference_stage: str = 'A2'
class GenerationRequest(InputModel):
    target_id: str | None = None
    profile_version: int | None = Field(default=None,ge=0)
    context: str | None = Field(default=None,max_length=200)
    minutes: int = Field(default=10,ge=3,le=30)
class SessionRequest(InputModel):lesson_id: str
class NextRequest(InputModel):expected_session_version: int
class LearnRequest(InputModel):
    material_index: int = Field(ge=0)
    personal_text: str = Field(min_length=1,max_length=1000)
class ReviewRequest(InputModel):
    catalog_id: str
    targets: list[TargetDefinition]
    reviewer: str = Field(min_length=1,max_length=200)
class PublishRequest(InputModel):review_id: str

class Services:
    def __init__(self,settings,provider=None):
        settings.validate();self.settings=settings;self.store=Store(settings.database_url)
        self.curriculum=CurriculumService(CurriculumRepository(settings.workspace),self.store)
        self.curriculum.bootstrap()
        self.provider=provider or (FixtureProvider(settings.workspace) if settings.mode=='fixture' else DeepSeekByteProvider(settings))
        self.planner=Planner(self.curriculum,self.store)
        self.generator=Generator(self.store,self.planner,self.curriculum,self.provider,settings)
        self.assessor=Assessor(self.store,self.curriculum,self.provider,settings)
        self.sessions=Sessions(self.store,self.curriculum,self.provider,self.generator,self.assessor,settings)

def job_view(row):
    p=row['payload']
    return {'schema_version':'1.0','job_id':row['id'],'state':row['state'],'row_version':row['version'],
        'error':p.get('error'),'result_lesson_id':p.get('lesson',{}).get('lesson_id') if row['state'] in ('approved','preview_ready') else None,
        'reason':p.get('assignment',{}).get('reason'),'attempts':row['attempts']}

def create_app(settings=None,provider=None):
    settings=settings or Settings()
    @asynccontextmanager
    async def lifespan(app):
        yield
        if hasattr(app.state.services.provider,'close'):await app.state.services.provider.close()
    app=FastAPI(title='SayWith V3',version='0.1.0',lifespan=lifespan)
    svc=Services(settings,provider);app.state.services=svc

    @app.exception_handler(Missing)
    async def missing(req,e):return JSONResponse(status_code=404,content={'detail':'资源不存在'})
    @app.exception_handler(Conflict)
    async def conflict(req,e):return JSONResponse(status_code=409,content={'detail':str(e)})
    @app.exception_handler(ReviewRequired)
    async def review(req,e):return JSONResponse(status_code=422,content={'detail':str(e)})
    @app.exception_handler(ProviderFailure)
    async def failure(req,e):return JSONResponse(status_code=503,content={'detail':'模型或语音服务暂时不可用，请重试'})
    @app.exception_handler(ValueError)
    async def invalid(req,e):return JSONResponse(status_code=422,content={'detail':str(e)[:800]})

    async def owner(authorization: Annotated[str|None,Header()]=None):
        if not authorization or not authorization.startswith('Bearer '):raise HTTPException(401,'请登录')
        token=authorization[7:];hash=hashlib.sha256(token.encode()).hexdigest()
        with svc.store.engine.connect() as c:
            row=c.execute(select(svc.store.users).where(svc.store.users.c.token_hash==hash)).mappings().first()
        if not row:raise HTTPException(401,'登录凭据失效')
        return row['id']

    async def admin(x_admin_token: Annotated[str|None,Header()]=None):
        if not settings.admin_token or not x_admin_token or not secrets.compare_digest(x_admin_token,settings.admin_token):
            raise HTTPException(403,'需要管理员权限')

    @app.get('/health')
    def health():
        with svc.store.engine.connect() as c:c.execute(select(svc.store.users.c.id).limit(1))
        return {'status':'ok','mode':settings.mode,'map_version':svc.curriculum.active_version}

    @app.post('/v1/users',status_code=201)
    def register(preferences:Preferences):
        if preferences.reference_stage not in STAGES:raise ValueError('Invalid reference stage')
        id=uid();token=secrets.token_urlsafe(32)
        with svc.store.transaction() as c:
            c.execute(insert(svc.store.users).values(id=id,token_hash=hashlib.sha256(token.encode()).hexdigest(),created_at=time.time()))
            profile=LearnerProfile(user_id=id,preferences=preferences.model_dump()).model_dump()
            svc.store.put('LearnerProfile',id,id,profile,conn=c)
        return {'user_id':id,'access_token':token,'profile':profile}

    @app.get('/v1/profile')
    def profile(user=Depends(owner)):return svc.store.get('LearnerProfile',user,user)['payload']

    @app.patch('/v1/profile/preferences')
    def preferences(data:Preferences,user=Depends(owner)):
        if data.reference_stage not in STAGES:raise ValueError('Invalid reference stage')
        row=svc.store.get('LearnerProfile',user,user);p=row['payload'];p['preferences']=data.model_dump();p['profile_version']+=1
        svc.store.put('LearnerProfile',user,user,p,expected=row['version']);return p

    @app.get('/v1/curriculum/targets')
    def targets(stage:str|None=None,family:str|None=None,user=Depends(owner)):
        version=svc.curriculum.active_version
        return {'map_version':version,'targets':[{'target_id':t['target_id'],'outcome':t['outcome'],
            'reference_stage':t['reference_stage']} for t in svc.curriculum.list_targets(stage=stage,family=family,map_version=version)]}

    @app.get('/v1/curriculum/targets/{id}')
    def target(id:str,user=Depends(owner)):
        try:return svc.curriculum.target(id)
        except KeyError:raise Missing('target')

    @app.get('/v1/contracts')
    def contracts():return {name:c.model_json_schema() for name,c in CONTRACTS.items()}

    @app.post('/v1/course-generation-jobs',status_code=202)
    def generate(data:GenerationRequest,idempotency_key:Annotated[str,Header(min_length=1,max_length=200)],user=Depends(owner)):
        if data.target_id:
            try:svc.curriculum.target(data.target_id)
            except KeyError:raise ValueError('未知学习目标')
        return job_view(svc.store.create_job(user,idempotency_key,data.model_dump()))

    @app.get('/v1/resources')
    def resources(query:str,limit:int=20,user=Depends(owner)):
        if len(query)>100:raise ValueError('Query too long')
        profile=svc.store.get('LearnerProfile',user,user)['payload']
        known=tuple(x['resource_id'] for x in profile['resource_states'] if x.get('understanding')=='demonstrated')
        return {'candidate_only':True,'senses':svc.curriculum.repository.query_senses(query=query,limit=limit,excluded_ids=known)}

    @app.get('/internal/v1/metrics',dependencies=[Depends(admin)])
    def metrics():
        from collections import Counter
        with svc.store.engine.connect() as c:
            rows=c.execute(select(svc.store.jobs.c.state,svc.store.jobs.c.attempts)).all()
        return {'jobs_by_state':dict(Counter(r.state for r in rows)),'attempts':sum(r.attempts for r in rows),
                'audio_assets':len(svc.store.list('AudioAsset')),'assessment_count':len(svc.store.list('AssessmentResult')),
                'evidence_count':len(svc.store.list('Evidence')),'mode':settings.mode}

    @app.get('/v1/course-generation-jobs/{id}')
    def job(id:str,user=Depends(owner)):return job_view(svc.store.job(id,user))
    @app.post('/v1/course-generation-jobs/{id}/cancel')
    def cancel(id:str,user=Depends(owner)):return job_view(svc.store.cancel(id,user))

    @app.get('/v1/lessons')
    def lessons(user=Depends(owner)):
        return [{'lesson_id':r['id'],'lesson_version':r['payload']['lesson_version'],'target_ids':r['payload']['target_ids'],
            'outcome':svc.curriculum.target(r['payload']['target_ids'][0],r['payload']['map_version'])['outcome'],
            'learner_ready':r['payload']['learner_ready'],'fixture':r['payload']['provenance']['fixture']} for r in svc.store.list('LessonPackage',user)]

    @app.post('/v1/sessions',status_code=201)
    def session(data:SessionRequest,user=Depends(owner)):return svc.sessions.create(user,data.lesson_id)
    @app.get('/v1/sessions/{id}')
    def view(id:str,user=Depends(owner)):return svc.sessions.view(id,user)
    @app.post('/v1/sessions/{id}/learn')
    def learn(id:str,data:LearnRequest,user=Depends(owner)):return svc.sessions.learned(id,user,data.material_index,data.personal_text)
    @app.post('/v1/sessions/{id}/next')
    async def next_phase(id:str,data:NextRequest,user=Depends(owner)):return await svc.sessions.next(id,user,data.expected_session_version)
    @app.post('/v1/sessions/{id}/inputs')
    async def input(id:str,data:LearnerInput,user=Depends(owner)):return await svc.sessions.input(id,user,data.model_dump())
    @app.post('/v1/sessions/{id}/finish')
    async def finish(id:str,user=Depends(owner)):return await svc.sessions.finish(id,user)

    @app.post('/v1/media',status_code=201)
    async def upload(audio:UploadFile=File(),user=Depends(owner)):
        data=await audio.read(settings.max_audio_bytes+1)
        if len(data)>settings.max_audio_bytes:raise HTTPException(413,'录音过大')
        info,_=wav_info(data)
        if info['channels']!=1 or info['width']!=2 or info['rate']!=16000:raise ValueError('请上传16kHz单声道PCM16 WAV')
        id=uid();filename=id+'.wav';(settings.media_dir/filename).write_bytes(data)
        asset={'asset_id':id,'filename':filename,'audio_ref':'/v1/media/'+id,'purpose':'learner_recording','info':info,'fixture':False,
               'sha256':hashlib.sha256(data).hexdigest()}
        svc.store.put('AudioAsset',id,user,asset)
        return {'audio_ref':asset['audio_ref']}

    @app.get('/v1/media/{id}')
    def media(id:str,user=Depends(owner)):
        asset=svc.store.get('AudioAsset',id,user)['payload']
        return FileResponse(settings.media_dir/asset['filename'],media_type='audio/wav')

    @app.get('/v1/assessments')
    def assessments(user=Depends(owner)):
        return [r['payload'] for r in svc.store.list('AssessmentResult',user)]

    @app.post('/internal/v1/sources/normalize',dependencies=[Depends(admin)])
    def normalize(data:SourceCatalog):return svc.curriculum.normalize(data.model_dump())
    @app.post('/internal/v1/curriculum/reviews',dependencies=[Depends(admin)])
    def map_review(data:ReviewRequest):return svc.curriculum.review(data.catalog_id,[t.model_dump() for t in data.targets],data.reviewer)
    @app.post('/internal/v1/curriculum/releases',dependencies=[Depends(admin)])
    def map_publish(data:PublishRequest):return svc.curriculum.publish(data.review_id)
    @app.get('/internal/v1/lessons/{id}',dependencies=[Depends(admin)])
    def internal_lesson(id:str):return svc.store.get('LessonPackage',id)['payload']
    return app
