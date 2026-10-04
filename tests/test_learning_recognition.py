import asyncio
from backend.byte_speech import DeepSeekByteProvider

def test_recognition_context_is_vocabulary_not_an_answer_rewrite():
    provider=object.__new__(DeepSeekByteProvider);received=[]
    async def transcribe(data,filename,hotwords=None):
        received.extend(hotwords)
        return {'text':'I unpack the kitchen stuff.','quality':'final_transcript_available'}
    provider.transcribe=transcribe
    result=asyncio.run(provider.transcribe_learning(b'audio','recording.wav',{'expression':'Let me check: I pack the kitchen stuff, and you pack the books?'}))
    assert {'kitchen','stuff','books'}<=set(received)
    assert 'pack' not in received and 'unpack' not in received
    assert result['text']=='I unpack the kitchen stuff.'


def test_failure_reason_retains_meaning_without_revealing_english_answer():
    from backend.learning_practice import chinese_reason
    reason=chinese_reason('把“打包”说成了“unpack”（拆包），任务内容与意图不符。')
    assert '打包' in reason and '拆包' in reason and 'unpack' not in reason
    assert '任务内容与意图不符' in reason


def test_pack_word_boundary_ambiguity_does_not_rewrite_real_unpack():
    from backend.learning_practice import pack_boundary_ambiguous
    material={'expression':'Let me check: I pack the kitchen stuff, and you pack the books?'}
    assert pack_boundary_ambiguous('Let me check. Unpack the kitchen stocks.',material)
    assert pack_boundary_ambiguous('Let me check. Unpack the kitchen stocks.',{'expression':'I bring the snacks.'},'明天搬家，确认你打包厨房物品。')
    assert not pack_boundary_ambiguous('Let me check. I unpack the kitchen stuff.',material)
    assert not pack_boundary_ambiguous('I pack the kitchen stuff.',material)
    assert not pack_boundary_ambiguous('Unpack the books.',{'expression':'Please unpack the books.'})
