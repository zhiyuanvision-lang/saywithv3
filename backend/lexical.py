"""Bounded notebook scheduling and conservative, evidence-based lexical updates."""
import copy
import hashlib
import json
import re
import time
from .contracts import LexicalSelection, LexicalCandidate

POLICY_VERSION = 'lexical-v1'
STOP = set('the a an and or to of for is are be can do make with what where using simple reference talk people see used obtained'.split())

def tokens(text):
    return set(re.findall(r'[a-z]{3,}',text.lower()))-STOP

def sense_id(word,sense):
    return 'sense:'+hashlib.sha256((word+':'+sense.get('meaning_cn','')).encode()).hexdigest()[:20]

def select_words(profile,target,entries,context='',limit=2,now=None):
    """Source target links dominate; textual matches are candidates, confirmed by course QA."""
    now=time.time() if now is None else now
    states={s['resource_id']:s for s in profile['resource_states']}
    target_text=target['outcome']+' '+context+' '+ ' '.join(r.get('outcome_en','') for r in target['reviewed_standard_references'])
    anchors=tokens(target_text)
    if target['target_id'].startswith('ARRANGE.'):
        anchors.update('available free time tomorrow today schedule diary meeting meet appointment friday monday afternoon morning'.split())
    ranked=[]
    for entry in entries:
        word=entry['word'];state=states.get('lexeme:'+word,{})
        if not state.get('notebook_active'):continue
        sources=entry.get('sources',[])
        targets=list(dict.fromkeys(t for src in sources for t in src.get('target_ids',[])))
        targets=list(dict.fromkeys(targets+[t for o in state.get('observations',[]) for t in o.get('target_ids',[])]))
        linked=target['target_id'] in targets
        family=any(t.split('.')[0]==target['target_id'].split('.')[0] for t in targets)
        contexts=entry.get('contexts',[])[-2:]
        scored=[]
        for sense in entry['card'].get('senses',[]):
            text=' '.join([sense.get('meaning_en',''),sense.get('meaning_cn',''),sense.get('pattern',''),sense.get('collocation',''),*[e.get('text','') for e in sense.get('examples',[])]])
            overlap=len(tokens(text)&anchors)
            scored.append((overlap,sense))
        sense=max(scored,key=lambda x:x[0])[1] if scored else {'meaning_cn':entry['card'].get('meaning','')}
        overlap=(max((x[0] for x in scored),default=0)+len(tokens(' '.join(contexts))&anchors))
        if not linked and not family and overlap<2:continue
        sid=sense_id(word,sense);specific=state.get('senses',{}).get(sid,{})
        due=specific.get('due_at',state.get('due_at'));needed=specific.get('retrieval',state.get('retrieval')) in ('needs_practice','supported') or specific.get('understanding',state.get('understanding'))=='needs_practice'
        reason='到期复习' if due is not None and due<=now else '需要加强' if needed else '先检查收藏词的起点'
        # Not-yet-due mastered words do not occupy the practice budget.
        if due is not None and due>now and specific.get('retrieval') in ('provisional','demonstrated') and not needed:continue
        forms=[word]
        for f in entry['card'].get('word_forms',[]):forms.extend(re.split(r'[,;/\s]+',f.get('text','')))
        selection=LexicalSelection(resource_id='lexeme:'+word,notebook_entry_id=entry['id'],word=word,sense_id=sid,
            meaning_zh=sense.get('meaning_cn',''),forms=list(dict.fromkeys(f.lower() for f in forms if re.fullmatch(r"[a-zA-Z]+(?:['’-][a-zA-Z]+)*",f))),
            recent_contexts=contexts,target_ids=list(dict.fromkeys(targets+[target['target_id']])),reason=reason,relevance='同目标来源' if linked else '同类沟通来源' if family else '任务文本与词义语境匹配，须通过课程质检',
            understanding=specific.get('understanding',state.get('understanding','not_checked')),retrieval=specific.get('retrieval',state.get('retrieval','not_checked')),due_at=due).model_dump()
        ranked.append(((0 if linked else 1 if family else 2,0 if due is not None and due<=now else 1 if needed else 2,due or now,word),selection))
    return [x[1] for x in sorted(ranked,key=lambda x:x[0])[:limit]]

def validate_checks(raw,resources,turns):
    """Model claims need a quoted learner turn containing this lexeme or its stored forms."""
    candidate=LexicalCandidate.model_validate(raw)
    allowed={r['resource_id']:r for r in resources};learner={t['turn_id']:t for t in turns if t['speaker']=='learner'}
    result=[];seen=set()
    for parsed in candidate.checks:
        check=parsed.model_dump();r=allowed.get(check['resource_id'])
        valid=bool(r and check['sense_id']==r['sense_id'] and check['resource_id'] not in seen)
        seen.add(check['resource_id'])
        if check['result'] in ('correct_usage','meaning_mismatch'):
            quoted=check['quote'].strip()
            refs=check['evidence_refs'];forms=set(r.get('forms',[r['word']])) if r else set()
            valid=valid and check['confidence']=='high' and bool(quoted) and bool(refs) and set(refs)<=learner.keys()
            valid=valid and any(quoted.lower() in learner[i].get('transcript',learner[i].get('text','')).lower() for i in refs if i in learner)
            valid=valid and bool(set(re.findall(r"[a-z]+(?:['’-][a-z]+)*",quoted.lower()))&forms)
        # A paraphrase or omission is never evidence of word failure.
        check['validation']='accepted' if valid else 'rejected'
        result.append(check)
    return result

def apply_checks(profile,checks,resources,attempt_id,session_id,independent,supports,scene,evidence_ref,now=None,retention_days=7):
    now=time.time() if now is None else now
    by_id={r['resource_id']:r for r in resources}
    for check in checks:
        if check['validation']!='accepted' or check['result'] not in ('correct_usage','meaning_mismatch'):continue
        resource=by_id[check['resource_id']]
        state=next((s for s in profile['resource_states'] if s['resource_id']==resource['resource_id']),None)
        if state is None:continue
        sid=check['sense_id'];specific=state.setdefault('senses',{}).setdefault(sid,{'sense_id':sid,'meaning_zh':resource['meaning_zh'],'understanding':'not_checked','retrieval':'not_checked','retention':'not_checked','observations':[]})
        if any(o['attempt_id']==attempt_id for o in specific['observations']):continue
        correct=check['result']=='correct_usage'
        obs={'attempt_id':attempt_id,'session_id':session_id,'time':now,'correct':correct,'independent':independent,'support_used':supports,'scenario_signature':scene,'evidence_ref':evidence_ref,'evidence_refs':check['evidence_refs'],'quote':check['quote'],'target_ids':resource.get('target_ids',[])}
        specific['observations']=(specific['observations']+[obs])[-100:]
        successes=[o for o in specific['observations'] if o['correct'] and o['independent']]
        if correct:
            specific['understanding']='demonstrated' if len({o['session_id'] for o in successes})>=2 else 'provisional'
            if independent:specific['retrieval']='demonstrated' if len({o['session_id'] for o in successes})>=2 else 'provisional'
            elif specific['retrieval'] not in ('provisional','demonstrated'):specific['retrieval']='supported'
            prior=[o for o in successes if o['attempt_id']!=attempt_id and o['session_id']!=session_id]
            if independent and prior and now-min(o['time'] for o in prior)>=retention_days*86400:specific['retention']='demonstrated'
            step=min(4,len({o['session_id'] for o in successes}));days=[1,3,7,14,30][step] if independent else 1
        else:
            specific['understanding']='needs_practice';specific['retrieval']='needs_recheck';specific['retention']='needs_recheck';days=1
        specific.update(due_at=now+days*86400,updated_at=now,policy_version=POLICY_VERSION,confidence='provisional_rule_requires_pilot')
        # Summary is explicitly the last assessed sense, not all senses of this word.
        state.update(understanding=specific['understanding'],retrieval=specific['retrieval'],due_at=specific['due_at'],last_assessed_sense=sid,updated_at=now,evidence_strength='validated_usage')
