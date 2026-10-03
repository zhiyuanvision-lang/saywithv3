"""DeepSeek text + ByteDance 16k PCM ASR / 24k PCM TTS."""
import asyncio
import io
import wave
from .providers import APIProvider, ProviderFailure, ReviewRequired
from .doubao.asr_client import DoubaoASRClient, AsrResult, AsrErrorResult
from .doubao.tts_client import (DoubaoTTSClient, EVENT_SESSION_FINISHED, EVENT_SESSION_FAILED,
                              EVENT_SESSION_CANCELED)

def wav_info(data):
    try:
        with wave.open(io.BytesIO(data),'rb') as f:
            info={'rate':f.getframerate(),'channels':f.getnchannels(),'width':f.getsampwidth(),
                  'frames':f.getnframes(),'duration':f.getnframes()/f.getframerate()}
            pcm=f.readframes(f.getnframes())
    except (wave.Error,EOFError,ZeroDivisionError) as e:raise ValueError('Invalid WAV audio') from e
    if not pcm or info['duration']>120 or len(pcm)!=info['frames']*info['channels']*info['width']:
        raise ValueError('Audio must contain valid 0–120 seconds of PCM')
    return info,pcm

class DeepSeekByteProvider(APIProvider):
    async def speech(self,text):
        client=DoubaoTTSClient(api_key=self.settings.doubao_key,resource_id=self.settings.doubao_tts_resource,
            speaker=self.settings.doubao_speaker,audio_format='pcm',sample_rate=24000)
        chunks=[]
        try:
            async with asyncio.timeout(60):
                await client.connect();id=await client.start_session()
                await client.send_text(id,text);await client.finish_session(id)
                async for msg in client.messages():
                    if msg.audio:chunks.append(msg.audio)
                    if msg.event in (-1,EVENT_SESSION_FAILED,EVENT_SESSION_CANCELED):raise ProviderFailure('ByteDance synthesis failed')
                    if msg.event==EVENT_SESSION_FINISHED:break
                else:raise ProviderFailure('ByteDance synthesis ended without final marker')
            if not chunks:raise ProviderFailure('ByteDance returned no audio')
            b=io.BytesIO()
            with wave.open(b,'wb') as f:
                f.setnchannels(1);f.setsampwidth(2);f.setframerate(24000);f.writeframes(b''.join(chunks))
            return b.getvalue()
        finally:await client.close()

    async def transcribe(self,data,filename):
        info,pcm=wav_info(data)
        if info['channels']!=1 or info['width']!=2:raise ValueError('ASR requires mono PCM16 WAV')
        if info['rate']!=16000:
            # Linear interpolation is sufficient for the mono PCM speech boundary.
            import struct
            samples=struct.unpack('<'+'h'*(len(pcm)//2),pcm)
            ratio=info['rate']/16000;length=int(len(samples)/ratio)
            converted=[]
            for i in range(length):
                x=i*ratio;j=int(x);frac=x-j
                converted.append(round(samples[j]*(1-frac)+samples[min(j+1,len(samples)-1)]*frac))
            pcm=struct.pack('<'+'h'*len(converted),*converted)
        client=DoubaoASRClient(api_key=self.settings.doubao_key,resource_id=self.settings.doubao_asr_resource,
            language='en-US',two_pass=True)
        async def send():
            for start in range(0,len(pcm),6400):await client.send_audio(pcm[start:start+6400])
            await client.send_audio(b'',is_last=True)
        try:
            async with asyncio.timeout(60):
                await client.connect()
                sender=asyncio.create_task(send())
                text='';final=False
                try:
                    async for result in client.responses():
                        if isinstance(result,AsrErrorResult):raise ProviderFailure('ByteDance recognition failed '+str(result.code))
                        if result.text:text=result.text
                        if result.is_last:final=True
                    await sender
                finally:
                    if not sender.done():sender.cancel()
                    await asyncio.gather(sender,return_exceptions=True)
            if not final or not text.strip():raise ReviewRequired('No reliable final audio transcription')
            return {'text':text,'quality':'final_transcript_available','confidence':'unknown',
                    'model':self.settings.doubao_asr_resource,'two_pass':True,'duration':info['duration']}
        finally:await client.close()
