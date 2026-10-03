import asyncio
import json
import struct
import pytest
import httpx
from backend.config import Settings
from backend.providers import APIProvider, ProviderFailure, normalized
from backend.doubao.asr_client import DoubaoASRClient
from backend.doubao.protocol import build_header, pack_u32

def test_deepseek_disables_thinking_and_parses_json():
    seen={}
    def request(req):
        seen.update(json.loads(req.content))
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':'{"result":"ok"}'}}]})
    async def run():
        p=APIProvider(Settings(),httpx.MockTransport(request))
        try:assert await p.json('Return JSON',{})=={'result':'ok'}
        finally:await p.close()
    asyncio.run(run())
    assert seen['thinking']=={'type':'disabled'}
    assert seen['response_format']=={'type':'json_object'}

def test_truncated_content_is_not_used_as_a_course():
    async def run():
        p=APIProvider(Settings(),httpx.MockTransport(lambda r:httpx.Response(200,json={
            'choices':[{'finish_reason':'length','message':{'content':'{}','reasoning_content':'ignored'}}]})))
        try:
            with pytest.raises(ProviderFailure,match='token budget'):await p.json('Return JSON',{})
        finally:await p.close()
    asyncio.run(run())

def test_audio_numbers_are_canonicalized():
    assert normalized('How about two?')==normalized('How About 2?')
    assert normalized('How about three?')!=normalized('How About 2?')

def test_asr_final_flag_without_sequence():
    payload=json.dumps({'result':{'text':'How about two?'}}).encode()
    frame=build_header(9,2,1,0)+pack_u32(len(payload))+payload
    result=DoubaoASRClient(api_key='test')._parse_message(frame)
    assert result.is_last and result.text=='How about two?'

def test_asr_final_positive_sequence():
    payload=json.dumps({'result':{'text':'How about two?'}}).encode()
    frame=build_header(9,3,1,0)+struct.pack('>i',5)+pack_u32(len(payload))+payload
    result=DoubaoASRClient(api_key='test')._parse_message(frame)
    assert result.is_last and result.text=='How about two?'
