"""Normalize sources, retain traceability, record review, release immutable maps."""
import hashlib
import json
from pathlib import Path
from .contracts import SourceCatalog, CurriculumRelease, TargetDefinition
from .store import digest, uid, Missing, Conflict
from sqlalchemy.exc import IntegrityError

class CurriculumService:
    def __init__(self,repository,store):self.repository=repository;self.store=store

    def target(self,id,map_version=None):
        if map_version is None:
            try:map_version=self.store.get('ActiveCurriculum','current')['payload']['map_version']
            except Missing:map_version=self.repository.version
        if map_version!=self.repository.version:
            return self.store.get('TargetDefinition',map_version+'/'+id)['payload']
        t=self.repository.get_target(id)
        return TargetDefinition(map_version=t['map_version'],target_id=id,target_version=t['target_version'],
            outcome=t['outcome'],reference_stage=t['reference_stage'],contract=t['generation_contract'],
            reviewed_standard_references=t['reviewed_standard_references']).model_dump()

    def bootstrap(self):
        try:self.store.get('CurriculumRelease',self.repository.version);return
        except Missing:pass
        report=self.repository.validate()
        if report['failed']:raise ValueError('Invalid curriculum dependencies')
        sources=[]
        for name,ref in self.repository.map['standard_reference_catalogs'].items():
            file=self.repository.resolve(ref)
            sources.append({'source_id':name,'kind':'reference_catalog','document_ref':ref,
                'sha256':hashlib.sha256(file.read_bytes()).hexdigest(),'extraction_status':'existing_reviewed_import'})
        catalog=SourceCatalog(catalog_version='existing-'+self.repository.version,sources=sources,status='normalized').model_dump()
        release=CurriculumRelease(map_version=self.repository.version,map_ref='curriculum_map.json',
            dependencies=[{'kind':'lexicon','ref':self.repository.map['lexicon']['database'],'version':self.repository.version}],
            release_scope='backend_map_data',learner_content_ready=False).model_dump()
        try:
            with self.store.transaction() as c:
                self.store.put('SourceCatalog',catalog['catalog_version'],'system',catalog,conn=c)
                self.store.put('CurriculumRelease',self.repository.version,'system',release,conn=c)
                self.store.put('ReleaseAudit',self.repository.version,'system',{'map_sha256':digest(self.repository.map),
                    'validation':report,'review_origin':'existing single-model review, not independent certification'},conn=c)
        except IntegrityError:
            # Another API/worker initialized the same immutable release concurrently.
            self.store.get('CurriculumRelease',self.repository.version)

    def list_targets(self,stage=None,family=None):
        try:version=self.store.get('ActiveCurriculum','current')['payload']['map_version']
        except Missing:version=self.repository.version
        if version==self.repository.version:return [self.target(t['target_id'],version) for t in self.repository.list_targets(stage=stage,family=family)]
        return [r['payload'] for r in self.store.list('TargetDefinition') if r['payload']['map_version']==version
                and (stage is None or r['payload']['reference_stage']==stage)
                and (family is None or r['payload']['target_id'].startswith(family+'.'))]

    def normalize(self,catalog):
        catalog=SourceCatalog.model_validate(catalog).model_dump();ids=set();rows=[]
        for entry in catalog['sources']:
            if entry['source_id'] in ids:raise ValueError('Duplicate source ID')
            ids.add(entry['source_id'])
            file=(self.repository.workspace/entry['document_ref']).resolve()
            if not file.is_relative_to(self.repository.workspace) or not file.is_file():raise ValueError('Invalid source path')
            if file.stat().st_size>100_000_000:raise ValueError('Source too large')
            if file.suffix=='.json':content=json.loads(file.read_text());method='json'
            elif file.suffix in ('.txt','.csv'):content=file.read_text();method='utf8'
            elif file.suffix=='.pdf':
                import fitz
                with fitz.open(file) as doc:content=[{'page':i+1,'text':p.get_text()} for i,p in enumerate(doc)]
                method='pdf_text_requires_semantic_review'
            else:raise ValueError('Only JSON, text, CSV and PDF sources supported')
            ref=uid();self.store.put('NormalizedSource',ref,'system',{'source_id':entry['source_id'],'content':content,
                'method':method,'document_ref':entry['document_ref'],'sha256':hashlib.sha256(file.read_bytes()).hexdigest()})
            rows.append({**entry,'normalized_ref':ref,'method':method})
        catalog.update(sources=rows,status='normalized_requires_review')
        self.store.put('SourceCatalog',catalog['catalog_version'],'system',catalog)
        return catalog

    def review(self,catalog_id,targets,reviewer):
        catalog=self.store.get('SourceCatalog',catalog_id)['payload']
        if not targets:raise ValueError('A reviewed release needs targets')
        definitions=[TargetDefinition.model_validate(t).model_dump() for t in targets]
        if len({t['target_id'] for t in definitions})!=len(definitions):raise ValueError('Duplicate target')
        version=definitions[0]['map_version']
        if any(t['map_version']!=version or t['target_version']!=version for t in definitions):raise ValueError('Mixed versions')
        for t in definitions:
            if not t['contract'].get('task_specific_contract'):raise ValueError('Missing task contract')
            if t['contract'].get('target_version')!=version or t['contract'].get('main_outcome')!=t['outcome']:
                raise ValueError('Target contract version/outcome mismatch')
            for ref in t['reviewed_standard_references']:
                if ref.get('official_equivalence') or ref.get('learner_score_authority'):raise ValueError('Unsupported official equivalence')
        id=uid();self.store.put('MapReview',id,'system',{'catalog_id':catalog_id,'targets':definitions,'reviewer':reviewer,
            'map_version':version,'status':'reviewed','catalog_hash':digest(catalog)})
        return {'review_id':id,'map_version':version}

    def publish(self,review_id):
        review=self.store.get('MapReview',review_id)['payload']
        version=review['map_version']
        with self.store.transaction() as c:
            try:self.store.get('CurriculumRelease',version,conn=c)
            except Missing:pass
            else:raise Conflict('Released maps are immutable')
            catalog=self.store.get('SourceCatalog',review['catalog_id'],conn=c)['payload']
            if digest(catalog)!=review['catalog_hash']:raise Conflict('Source changed after review')
            release=CurriculumRelease(map_version=version,map_ref='review/'+review_id,
                dependencies=[{'kind':'normalized_sources','ref':review['catalog_id'],'version':catalog['catalog_version']},
                              {'kind':'lexicon','ref':self.repository.map['lexicon']['database'],'version':self.repository.version}],
                release_scope='backend_map_data',learner_content_ready=False).model_dump()
            for t in review['targets']:self.store.put('TargetDefinition',version+'/'+t['target_id'],'system',t,conn=c)
            self.store.put('CurriculumRelease',version,'system',release,conn=c)
            try:
                active=self.store.get('ActiveCurriculum','current',conn=c)
                self.store.put('ActiveCurriculum','current','system',{'map_version':version},expected=active['version'],conn=c)
            except Missing:self.store.put('ActiveCurriculum','current','system',{'map_version':version},conn=c)
            self.store.emit('map:'+version,release,c)
        return release
