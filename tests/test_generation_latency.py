"""Provider concurrency and reuse must retain audio QA and account isolation."""
import asyncio
import hashlib
import io
import wave
from pathlib import Path

import pytest

from backend.config import Settings
from backend.generation import Generator
from backend.providers import ReviewRequired
from backend.store import Store, Missing


class Speech:
    fixture=False
    def __init__(self):
        self.spoken={};self.speech_calls=0;self.asr_calls=0;self.active=0;self.peak=0
    async def speech(self,text):
        self.speech_calls+=1;self.active+=1;self.peak=max(self.peak,self.active)
        try:
            await asyncio.sleep(.02)
            out=io.BytesIO()
            with wave.open(out,'wb') as w:
                w.setparams((1,2,16000,0,'NONE','not compressed'))
                w.writeframes(bytes([len(text),0])*1600)
            data=out.getvalue();self.spoken[hashlib.sha256(data).hexdigest()]=text
            return data
        finally:self.active-=1
    async def transcribe(self,data,filename):
        self.asr_calls+=1
        return {'text':self.spoken[hashlib.sha256(data).hexdigest()]}


def setup(tmp_path):
    settings=Settings(database_url='sqlite:///'+str(tmp_path/'db.sqlite'),media_dir=tmp_path/'media')
    settings.media_dir.mkdir()
    provider=Speech()
    return Generator(Store(settings.database_url),None,None,provider,settings),provider


def test_verified_cache_skips_repeat_asr_and_keeps_assets_private(tmp_path):
    generator,provider=setup(tmp_path)
    async def run():
        first=await generator.audio('I can meet at four.','alice','example')
        await generator.check_audio(first)
        generator.remember_audio_check(first,'alice')
        other=await generator.audio(first['text'],'bob','example')
        assert other['quality']=='passed' and other['asset_id']!=first['asset_id']
        with pytest.raises(Missing):generator.store.get('AudioAsset',other['asset_id'],'alice')
        assert provider.speech_calls==1 and provider.asr_calls==1
        (generator.settings.media_dir/other['filename']).write_bytes(b'corrupted')
        with pytest.raises(ReviewRequired,match='校验失败'):
            await generator.audio(first['text'],'bob','example')
    asyncio.run(run())


def test_provider_requests_overlap_but_are_bounded_and_failures_cancel_siblings(tmp_path):
    generator,provider=setup(tmp_path)
    async def run():
        results=[]
        async def synthesize(text):return await generator.audio(text,'alice','example')
        async for text,asset in generator.concurrent(['one','two longer','three even longer','four'],synthesize):results.append(asset)
        assert len(results)==4 and provider.peak==3 and provider.active==0
        active=set()
        async def fails(index):
            active.add(index)
            try:
                if index==0:
                    await asyncio.sleep(.01)
                    raise RuntimeError('provider failure')
                await asyncio.sleep(30)
            finally:active.discard(index)
        with pytest.raises(RuntimeError):
            async for _ in generator.concurrent(range(7),fails):pass
        assert not active
    asyncio.run(run())


def test_parallel_qa_still_rejects_changed_negation(tmp_path):
    generator,provider=setup(tmp_path)
    async def run():
        asset=await generator.audio('I can meet at four.','alice','example')
        async def wrong(data,filename):return {'text':"I can't meet at four."}
        provider.transcribe=wrong
        with pytest.raises(ReviewRequired):await generator.check_audio(asset)
        assert generator.store.get('AudioAsset',asset['asset_id'],'alice')['payload']['quality']=='pending'
    asyncio.run(run())


def test_audio_qa_normalizes_equivalent_spoken_times_without_hiding_wrong_numbers():
    from backend.providers import audio_normalized
    assert audio_normalized('at half past five')==audio_normalized('at 5:30')
    assert audio_normalized('at half past five p.m.')==audio_normalized('at 17:30')
    assert audio_normalized('at half past five')!=audio_normalized('at 6:30')
    assert audio_normalized('fifteen hundred')==audio_normalized('1500')
    assert audio_normalized('fifteen hundred')!=audio_normalized('1501')


def test_pronunciation_keeps_meridiem_audible_and_qa_keeps_missing_meridiem_distinct():
    from backend.providers import audio_normalized,speech_pronunciation
    assert speech_pronunciation('Two p.m. works.')=='Two in the afternoon works.'
    assert audio_normalized('Two p.m.')==audio_normalized('two in the afternoon')
    assert audio_normalized('Two p.m.')!=audio_normalized('2:00')
    assert audio_normalized('Two p.m.')!=audio_normalized('two in the morning')
