"""Shared dictionary, account-owned notebook and weak lexical practice signals."""
import copy
import hashlib
import json
import re
import time
from pathlib import Path
import httpx
from sqlalchemy import update
from .store import Missing, Conflict

WORD = re.compile(r"^[A-Za-z]+(?:['’-][A-Za-z]+)*$")

def normalize(raw):
    word=raw.strip().replace('’',"'").lower()
    if not WORD.fullmatch(word) or len(word)>80:raise ValueError('请选择一个英文单词')
    return word

class Vocabulary:
    def __init__(self,settings,store):
        self.settings=settings;self.store=store;self.words={};self.forms={}
        path=settings.workspace/'data/dictionary_core_with_scenarios.jsonl'
        if path.exists():
            for line in path.read_text().splitlines():
                row=json.loads(line);head=row['word'].lower();self.words[head]=row
                for f in row.get('word_forms',[]):
                    for form in re.split(r'[,;/\s]+',f.get('text','')):
                        if form:self.forms.setdefault(form.lower(),head)
        # Function forms omitted from some dictionary rows.
        self.forms.update({'am':'be','are':'be','were':'be',"i'm":'be',"isn't":'be',"can't":'can',"cannot":'can',"don't":'do'})

    async def lookup(self,raw,detail=False):
        token=normalize(raw);head=token if token in self.words else self.forms.get(token,token)
        key=hashlib.sha256((head+':'+str(detail)).encode()).hexdigest()
        try:
            cached=self.store.get('DictionaryCache',key,'dictionary')['payload']
            if cached['expires_at']>time.time():return copy.deepcopy(cached['card'])
        except Missing:pass
        # Reuse the legacy dictionary resolver and full knowledge cards; no learner credentials cross services.
        card=None
        if self.settings.mode!='fixture':
            try:
                async with httpx.AsyncClient(timeout=12,follow_redirects=False) as client:
                    r=await client.get(self.settings.dictionary_api_base+'/v1/vocab/'+('knowledge' if detail else 'lookup'),params={'word':token,'wordbook_id':'cet4'})
                    if r.status_code==200 and isinstance(r.json(),dict) and r.json().get('word'):card=r.json()
            except (httpx.HTTPError,ValueError):pass
        if card is None:
            row=self.words.get(head)
            if row is None:raise Missing('Dictionary')
            card=copy.deepcopy(row)
        card['word']=normalize(card['word']);card['tapped_word']=token
        card.setdefault('meaning','；'.join(s.get('meaning_cn','') for s in card.get('senses',[])[:2]))
        card.setdefault('phonetic_uk','');card.setdefault('phonetic_us','')
        card.setdefault('audio_uk','');card.setdefault('audio_us','');card.setdefault('senses',[])
        card['dictionary_source']='dictionary_core_with_scenarios / shared SayWith resolver'
        # Cache is immutable per fetch; concurrent requests can use either equivalent result.
        try:
            old=self.store.get('DictionaryCache',key,'dictionary')
            self.store.put('DictionaryCache',key,'dictionary',{'card':card,'expires_at':time.time()+86400},expected=old['version'])
        except Missing:
            try:self.store.put('DictionaryCache',key,'dictionary',{'card':card,'expires_at':time.time()+86400})
            except Exception as e:
                from sqlalchemy.exc import IntegrityError
                if not isinstance(e,IntegrityError):raise
        except Conflict:pass
        return card

    def entry_id(self,user,word):return hashlib.sha256((user+':'+word).encode()).hexdigest()
    def mine(self,user):
        return {'items':sorted((r['payload'] for r in self.store.list('NotebookEntry',user)),key=lambda x:x['created_at'],reverse=True)}

    def signal(self,user,card,kind,context='',session_id=None,save=False):
        head=card['word'];id=self.entry_id(user,head);now=time.time()
        with self.store.transaction() as c:
            # Serialise user mutations against each other in PostgreSQL and SQLite.
            c.execute(update(self.store.users).where(self.store.users.c.id==user).values(created_at=self.store.users.c.created_at))
            session_row=None;target_ids=[]
            if session_id:
                session_row=self.store.get('Session',session_id,user,c)
                session=session_row['payload']
                lesson=self.store.get('LessonPackage',session['lesson_id'],user,c)['payload'];target_ids=lesson['target_ids']
            row=self.store.get('LearnerProfile',user,user,c);profile=copy.deepcopy(row['payload'])
            states=profile['resource_states'];resource_id='lexeme:'+head
            state=next((x for x in states if x['resource_id']==resource_id),None)
            if state is None:
                state={'resource_id':resource_id,'resource_type':'word','word':head,'understanding':'not_checked','retrieval':'not_checked','practice_signal':'lookup_only','lookup_count':0,'evidence_strength':'weak','observations':[]};states.append(state)
            if kind=='looked_up':state['lookup_count']=state.get('lookup_count',0)+1
            if save:state['practice_signal']='self_selected';state['notebook_active']=True
            state['updated_at']=now
            state['observations']=(state.get('observations',[])+[{'kind':kind,'time':now,'context_sentence':context[:1200],'session_id':session_id,'target_ids':target_ids,'tapped_word':card.get('tapped_word',head),'evidence_strength':'weak'}])[-30:]
            profile['profile_version']+=1
            self.store.put('LearnerProfile',user,user,profile,expected=row['version'],conn=c)
            if session_row and kind=='looked_up':
                s=copy.deepcopy(session_row['payload'])
                if s['phase'] in ('supported_practice','independent_application'):
                    s['support_used']=sorted(set(s['support_used']+['查词释义']))
                    s['dictionary_lookups']=(s.get('dictionary_lookups',[])+[{'word':head,'time':now}])[-50:]
                    self.store.put('Session',session_id,user,s,expected=session_row['version'],conn=c)
            if save:
                try:
                    existing=self.store.get('NotebookEntry',id,user,c)
                    entry=copy.deepcopy(existing['payload']);entry['card']=card
                    entry['contexts']=(entry.get('contexts',[])+([context[:1200]] if context and context not in entry.get('contexts',[]) else []))[-10:]
                    self.store.put('NotebookEntry',id,user,entry,expected=existing['version'],conn=c)
                except Missing:
                    entry={'id':id,'word':head,'created_at':now,'card':card,'contexts':[context[:1200]] if context else []}
                    self.store.put('NotebookEntry',id,user,entry,conn=c)
                return entry
        return state

    def remove(self,user,id):
        with self.store.transaction() as c:
            c.execute(update(self.store.users).where(self.store.users.c.id==user).values(created_at=self.store.users.c.created_at))
            entry=self.store.get('NotebookEntry',id,user,c)['payload']
            row=self.store.get('LearnerProfile',user,user,c);p=copy.deepcopy(row['payload'])
            for state in p['resource_states']:
                if state['resource_id']=='lexeme:'+entry['word']:state['notebook_active']=False
            p['profile_version']+=1;self.store.put('LearnerProfile',user,user,p,expected=row['version'],conn=c)
            c.execute(self.store.docs.delete().where(self.store.docs.c.kind=='NotebookEntry',self.store.docs.c.id==id,self.store.docs.c.owner==user))
        return {'removed':True}
