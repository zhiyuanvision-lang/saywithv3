from dataclasses import dataclass, field
import os
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / '.env', override=False)

@dataclass
class Settings:
    workspace: Path = ROOT
    mode: str = field(default_factory=lambda: os.getenv('SAYWITH_MODE', 'fixture'))
    database_url: str = field(default_factory=lambda: os.getenv('SAYWITH_DATABASE_URL', 'sqlite:///var/saywith.sqlite'))
    media_dir: Path = field(default_factory=lambda: Path(os.getenv('SAYWITH_MEDIA_DIR', 'var/media')))
    dictionary_api_base: str = field(default_factory=lambda: os.getenv('SAYWITH_DICTIONARY_API_BASE','https://api.saywith.zhiyuanv.com').rstrip('/'))
    api_base: str = field(default_factory=lambda: os.getenv('SAYWITH_API_BASE', 'https://api.deepseek.com'))
    api_key: str = field(default_factory=lambda: os.getenv('SAYWITH_API_KEY', ''))
    text_model: str = field(default_factory=lambda: os.getenv('SAYWITH_TEXT_MODEL', ''))
    review_model: str = field(default_factory=lambda: os.getenv('SAYWITH_REVIEW_MODEL', ''))
    doubao_key: str = field(default_factory=lambda: os.getenv('DOUBAO_API_KEY', ''))
    doubao_asr_resource: str = field(default_factory=lambda: os.getenv('DOUBAO_ASR_RESOURCE_ID', 'volc.seedasr.sauc.duration'))
    doubao_tts_resource: str = field(default_factory=lambda: os.getenv('DOUBAO_TTS_RESOURCE_ID', 'seed-tts-2.0'))
    doubao_speaker: str = field(default_factory=lambda: os.getenv('DOUBAO_TTS_SPEAKER', 'en_female_dacey_uranus_bigtts'))
    admin_token: str = field(default_factory=lambda: os.getenv('SAYWITH_ADMIN_TOKEN', ''))
    feedback_database_url: str = field(default_factory=lambda: os.getenv('SAYWITH_FEEDBACK_DATABASE_URL', ''))
    feedback_public_base: str = field(default_factory=lambda: os.getenv('SAYWITH_FEEDBACK_PUBLIC_BASE', 'https://api.saywith.zhiyuanv.com/learning'))
    max_audio_bytes: int = field(default_factory=lambda: int(os.getenv('SAYWITH_MAX_AUDIO_BYTES', '10485760')))
    retention_days: int = field(default_factory=lambda: int(os.getenv('SAYWITH_RETENTION_DAYS', '7')))
    max_job_attempts: int = field(default_factory=lambda: int(os.getenv('SAYWITH_MAX_JOB_ATTEMPTS', '3')))

    def validate(self):
        if self.mode not in ('fixture', 'provider'):
            raise ValueError('SAYWITH_MODE must be fixture or provider')
        if self.mode == 'provider' and not all((self.api_key,self.text_model,self.review_model,self.doubao_key)):
            raise ValueError('Provider mode requires DeepSeek and ByteDance credentials')
        if self.retention_days < 1 or self.max_job_attempts < 1:
            raise ValueError('Invalid retention/retry configuration')
        self.media_dir.mkdir(parents=True, exist_ok=True)
