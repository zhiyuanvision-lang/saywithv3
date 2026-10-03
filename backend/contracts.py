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

class LessonPackage(Contract):
    lesson_id: str
    lesson_version: int = Field(ge=1)
    assignment_id: str
    map_version: str
    target_ids: list[str] = Field(min_length=1,max_length=1)
    learning_materials: list[Material] = Field(min_length=1,max_length=8)
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
    fixture: bool = False

class DialogueResponse(Contract):
    session_id: str
    task_id: str
    turn_id: str
    reply_to: str | None
    speaker: Literal['partner'] = 'partner'
    text: str
    audio_ref: str | None = None
    support_provided: list[str] = Field(default_factory=list)

class LearnerInput(Contract):
    session_id: str
    task_id: str
    input_id: str
    type: Literal['speech','text','request_repeat','request_hint']
    audio_ref: str | None = None
    recorded_at: str
    text: str | None = Field(default=None,max_length=4000)
    expected_session_version: int | None = None

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
    task_snapshot_ref: str
    turns: list[dict[str, Any]]
    support_used: list[str]
    fixture: bool = False
    started_at: str | None = None
    finished_at: str | None = None

class AssessmentResult(Contract):
    assessment_id: str
    attempt_id: str
    assessment_version: str
    model_version: str
    target_results: list[dict[str, Any]]
    evidence_ids: list[str]
    validation: dict[str, Any]
    example_notice: str | None = None

CONTRACTS = {c.__name__:c for c in (SourceCatalog,CurriculumRelease,TargetDefinition,LearnerProfile,
    TeachingAssignment,LessonPackage,LearnerLessonView,DialogueResponse,LearnerInput,TaskAttempt,AssessmentResult)}


class AssessmentCheckCandidate(BaseModel):
    criterion: str
    result: Literal['met','not_met','unjudgeable']
    evidence_refs: list[str]

class AssessmentCandidate(BaseModel):
    result: Literal['completed','partial','failed','unjudgeable']
    confidence: Literal['high','medium','low']
    checks: list[AssessmentCheckCandidate]
    diagnosis: list[dict[str,Any]] = Field(default_factory=list)
