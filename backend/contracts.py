"""Versioned data contracts extending the architecture examples with concrete tasks."""
from typing import Literal, Any
from pydantic import BaseModel, Field, ConfigDict, model_validator

class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid')
    schema_version: Literal['1.0'] = '1.0'

class SourceCatalog(Contract):
    catalog_version: str
    sources: list[dict[str, Any]]
    status: str

class CurriculumRelease(Contract):
    map_version: str
    map_ref: str
    dependencies: list[dict[str, Any]]
    release_scope: str
    learner_content_ready: bool

class TargetDefinition(Contract):
    map_version: str
    target_id: str
    target_version: str
    outcome: str
    reference_stage: str
    contract: dict[str, Any]
    reviewed_standard_references: list[dict[str, Any]]
    reference_note: str | None = None

class NotebookSource(BaseModel):
    model_config = ConfigDict(extra='forbid')
    sentence: str = ''
    session_id: str | None = None
    target_ids: list[str] = Field(default_factory=list)
    scene: str = ''
    recorded_at: float

class NotebookEntry(Contract):
    id: str
    word: str
    created_at: float
    card: dict[str, Any]
    contexts: list[str] = Field(default_factory=list)
    sources: list[NotebookSource] = Field(default_factory=list)
    practice_state: dict[str,Any] | None = None

class LexicalSelection(BaseModel):
    model_config = ConfigDict(extra='forbid')
    resource_id: str
    notebook_entry_id: str
    word: str
    sense_id: str
    meaning_zh: str
    forms: list[str] = Field(default_factory=list)
    recent_contexts: list[str] = Field(default_factory=list)
    target_ids: list[str] = Field(default_factory=list)
    reason: str
    relevance: str
    understanding: str = 'not_checked'
    retrieval: str = 'not_checked'
    due_at: float | None = None

class LexicalPractice(BaseModel):
    model_config = ConfigDict(extra='forbid')
    practice_id: str = ''
    resource_id: str
    sense_id: str
    prompt_zh: str
    example: str
    explanation_zh: str
    hint_pattern: str

class LexicalCheck(BaseModel):
    model_config = ConfigDict(extra='forbid')
    resource_id: str
    sense_id: str
    result: Literal['correct_usage','meaning_mismatch','not_used','unjudgeable']
    confidence: Literal['high','medium','low']
    evidence_refs: list[str] = Field(default_factory=list)
    quote: str = ''

class LexicalResult(LexicalCheck):
    validation: Literal['accepted','rejected']

class LexicalCandidate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    checks: list[LexicalCheck] = Field(default_factory=list, max_length=2)

class LexicalResourceState(Contract):
    resource_id: str
    resource_type: Literal['word'] = 'word'
    word: str
    understanding: str = 'not_checked'
    retrieval: str = 'not_checked'
    practice_signal: str = 'self_selected'
    notebook_active: bool = True
    lookup_count: int = 0
    evidence_strength: str = 'weak'
    observations: list[dict[str,Any]] = Field(default_factory=list)
    senses: dict[str,dict[str,Any]] = Field(default_factory=dict)
    updated_at: float | None = None
    due_at: float | None = None
    last_assessed_sense: str | None = None

class LexicalPracticeInput(Contract):
    input_id: str = Field(min_length=1,max_length=100)
    practice_id: str
    type: Literal['speech','text','request_hint','skip']
    audio_ref: str | None = None
    text: str | None = Field(default=None,max_length=2000)
    hint_level: Literal['meaning','pattern','example'] = 'meaning'

class LexicalPracticeAttempt(Contract):
    request_hash: str
    response: dict[str,Any]
    input: LexicalPracticeInput
    turns: list[dict[str,Any]]
    resource: LexicalSelection
    practice_snapshot: LexicalPractice
    lesson_id: str
    lesson_version: int
    map_version: str
    model_version: str
    policy_version: str
    fixture: bool
    evidence_valid: bool

class LearnerProfile(Contract):
    user_id: str
    profile_version: int = 0
    target_states: list[dict[str, Any]] = Field(default_factory=list)
    resource_states: list[dict[str, Any]] = Field(default_factory=list)
    preferences: dict[str, Any] = Field(default_factory=dict)

class TeachingAssignment(Contract):
    assignment_id: str
    user_id: str
    map_version: str
    profile_version: int
    target_ids: list[str] = Field(min_length=1, max_length=1)
    reason: str
    context: str
    resource_plan: dict[str, Any]
    difficulty: dict[str, Any]
    purpose: Literal['diagnostic','new','consolidation','retention','transfer'] = 'new'
    review_metadata: dict[str,Any] = Field(default_factory=dict)
    completion_standard: str = ''
    minutes: int = Field(default=10, ge=3, le=30)

class Material(BaseModel):
    model_config = ConfigDict(extra='forbid')
    intent_zh: str
    expression: str
    audio_ref: str | None = None
    explanation_zh: str = ''
    personal_prompt_zh: str = ''
    resource_id: str = ''
    meaning_zh: str = ''
    partner_line: str = ''
    partner_meaning_zh: str = ''
    hint_pattern: str = ''

class Task(BaseModel):
    model_config = ConfigDict(extra='forbid')
    task_id: str
    task_version: int = Field(ge=1)
    learner_facts: dict[str, Any]
    partner_private_facts: dict[str, Any]
    role_rules: list[str] = Field(min_length=1)
    allowed_support: list[str]
    assessment_contract: dict[str, Any]
    learner_prompt: str = ''
    opening: str = ''
    scenario_signature: str = ''
    modality: Literal['spoken_interaction','text_interaction'] = 'spoken_interaction'
    interaction_policy: dict[str,bool] = Field(default_factory=dict)

class LessonPackage(Contract):
    title_zh: str = ""
    lesson_id: str
    lesson_version: int = Field(ge=1)
    assignment_id: str
    map_version: str
    target_ids: list[str] = Field(min_length=1,max_length=1)
    learning_materials: list[Material] = Field(min_length=1,max_length=8)
    lexical_practices: list[LexicalPractice] = Field(default_factory=list,max_length=2)
    practice_task_ref: str
    practice_task: Task | None = None
    independent_task: Task
    quality: dict[str, Any]
    provenance: dict[str, Any]
    learner_ready: bool = False
    example_notice: str | None = None

    @model_validator(mode='after')
    def publish_shape(self):
        if self.learner_ready and (self.quality.get('status') != 'approved' or
                                  not all(m.audio_ref for m in self.learning_materials)):
            raise ValueError('Ready lessons require approval and audio')
        return self

class LearnerLessonView(Contract):
    session_id: str
    lesson_id: str
    lesson_version: int
    task_id: str
    phase: str
    instruction: str
    learner_facts: dict[str, Any]
    available_actions: list[str]
    materials: list[dict[str, Any]] = Field(default_factory=list)
    completed_material_indices: list[int] = Field(default_factory=list)
    lexical_practices: list[dict[str,Any]] = Field(default_factory=list)
    fixture: bool = False
    entry_kind: str = 'course'
    review_metadata: dict[str,Any] = Field(default_factory=dict)
    title: str = ''
    partner_name: str = '对方'
    demonstration: list[dict[str,Any]] = Field(default_factory=list)
    guided_round: int | None = None
    guided_round_title: str = ''
    support_used: list[str] = Field(default_factory=list)
    shadow_feedback: dict[str,Any] | None = None
    assessment: dict[str,Any] | None = None

class HintContent(Contract):
    direction_zh: str | None = Field(default=None,max_length=100)
    expression: str = Field(min_length=1,max_length=240)
    meaning_zh: str | None = Field(default=None,max_length=160)
    explanation_zh: str | None = Field(default=None,max_length=200)

class DialogueResponse(Contract):
    session_id: str
    task_id: str
    turn_id: str
    reply_to: str | None
    speaker: Literal['partner'] = 'partner'
    text: str
    audio_ref: str | None = None
    support_provided: list[str] = Field(default_factory=list)
    kind: Literal['dialogue','hint','translation','repeat'] = 'dialogue'
    hint_content: HintContent | None = None

class LearnerInput(Contract):
    session_id: str
    task_id: str
    input_id: str
    type: Literal['speech','text','request_repeat','request_hint','request_translation']
    audio_ref: str | None = None
    recorded_at: str
    text: str | None = Field(default=None,max_length=4000)
    expected_session_version: int | None = None
    hint_level: Literal['intent','pattern','example','learned'] = 'intent'
    source_turn_id: str | None = None

class InputProgress(Contract):
    session_id: str
    input_id: str
    status: Literal['recognizing','responding','completed']
    turn_id: str
    transcript: str | None = None
    audio_ref: str | None = None

class TaskAttempt(Contract):
    attempt_id: str
    user_id: str
    session_id: str
    lesson_id: str
    lesson_version: int
    map_version: str
    task_id: str
    task_version: int
    target_ids: list[str]
    phase: str
    review_metadata: dict[str,Any] = Field(default_factory=dict)
    status: Literal['completed','abandoned'] = 'completed'
    task_snapshot_ref: str
    turns: list[dict[str, Any]]
    support_used: list[str]
    lexical_resources: list[LexicalSelection] = Field(default_factory=list,max_length=2)
    fixture: bool = False
    started_at: str | None = None
    finished_at: str | None = None

class AssessmentResult(Contract):
    assessment_id: str
    attempt_id: str
    assessment_version: str
    model_version: str
    target_results: list[dict[str, Any]]
    lexical_results: list[LexicalResult] = Field(default_factory=list)
    evidence_ids: list[str]
    validation: dict[str, Any]
    example_notice: str | None = None

CONTRACTS = {c.__name__:c for c in (SourceCatalog,CurriculumRelease,TargetDefinition,LearnerProfile,
    TeachingAssignment,LessonPackage,HintContent,LearnerLessonView,DialogueResponse,LearnerInput,TaskAttempt,AssessmentResult,NotebookEntry,LexicalPracticeInput,LexicalResourceState,LexicalSelection,LexicalPractice,LexicalResult,LexicalPracticeAttempt,InputProgress)}


class AssessmentCheckCandidate(BaseModel):
    criterion: str
    result: Literal['met','not_met','unjudgeable']
    evidence_refs: list[str]

class AssessmentCandidate(BaseModel):
    result: Literal['completed','partial','failed','unjudgeable']
    confidence: Literal['high','medium','low']
    checks: list[AssessmentCheckCandidate]
    diagnosis: list[dict[str,Any]] = Field(default_factory=list)
