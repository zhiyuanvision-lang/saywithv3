"""Turn-level closing intent is separate from task completion and learner mastery."""
import re

# Match a whole farewell, not a quoted phrase, question, negation or substring.
_FAREWELL=re.compile(
    r'(?:(?:ok|okay|great|alright|all right|thanks|thank you|yes|sure)[\s,.!，。！]+)*'
    r'(?:see (?:you|ya)(?: (?:then|soon|later|tomorrow|next time|on monday|on tuesday))?'
    r'|(?:good[ -]?bye|bye(?: bye)?|take care|talk to you (?:soon|later))'
    r'|再见|好的[，, ]*再见)[\s.!，。！]*',re.I)

def learner_closed(turn,reply):
    if turn.get('audio_ref') and turn.get('asr',{}).get('quality')!='final_transcript_available':
        return False
    content=turn.get('transcript','').strip()
    if not content:return False
    if '?' in content or '？' in content or re.search(r'\b(?:say|mean|pronounce|translate|phrase|word|sentence)\b|怎么说|什么意思',content,re.I):
        return False
    return bool(_FAREWELL.fullmatch(content)) or reply.get('conversation_closed') is True
