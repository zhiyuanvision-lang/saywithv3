"""Render v6 iOS design proposals, at 3x resolution (static mockups)."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import math
ROOT=Path(__file__).resolve().parent/'assets'
ROOT.mkdir(exist_ok=True)
S=3
CN='/System/Library/Fonts/STHeiti Medium.ttc'
EN='/System/Library/Fonts/SFNS.ttf'
BG='#F8F9F7'; INK='#172923'; SUB='#617069'; ACC='#17634D'; TINT='#E6EFE9'; LINE='#E1E6E2'

def render(mode):
 im=Image.new('RGB',(390*S,844*S),BG); d=ImageDraw.Draw(im)
 def rect(b,fill,r=0,stroke=None):
  b=tuple(int(v*S) for v in b)
  if r: d.rounded_rectangle(b,r*S,fill=fill,outline=stroke,width=S)
  else: d.rectangle(b,fill=fill,outline=stroke,width=S)
 def txt(x,y,t,size=17,color=INK,font=CN):
  d.text((int(x*S),int(y*S)),t,font=ImageFont.truetype(font,int(size*S)),fill=color)
 def center(y,t,size=17,color=INK,font=CN):
  f=ImageFont.truetype(font,int(size*S)); w=d.textbbox((0,0),t,font=f)[2]/S
  txt((390-w)/2,y,t,size,color,font)
 def line(points,color=INK,width=1):
  d.line([(int(x*S),int(y*S)) for x,y in points],fill=color,width=int(width*S))
 def circle(x,y,r,fill): d.ellipse(((x-r)*S,(y-r)*S,(x+r)*S,(y+r)*S),fill=fill)
 def play(x,y,color=ACC): d.polygon([(x*S,y*S),((x+10)*S,(y+6)*S),(x*S,(y+12)*S)],fill=color)
 def mic(x,y):
  rect((x-6,y-15,x+6,y+6),'white',6)
  d.arc(((x-12)*S,(y-10)*S,(x+12)*S,(y+13)*S),0,180,fill='white',width=2*S)
  line([(x,y+13),(x,y+20)],'white',2); line([(x-7,y+20),(x+7,y+20)],'white',2)
 def primary(y,label):
  rect((24,y,366,y+54),ACC,18); center(y+17,label,17,'white')
 def replay(y,label='再听一次'):
  rect((125,y,265,y+44),TINT,22); play(141,y+16); txt(164,y+13,label,15,ACC)
 txt(28,18,'9:41',15,font=EN)
 for i,h in enumerate([4,6,9,12]):rect((306+i*4,30-h,308+i*4,30),INK)
 rect((334,19,357,30),INK,3); rect((358,22,360,27),INK,1)
 circle(44,77,22,'#EEF1ED');line([(39,72),(49,82)],INK,1.6);line([(49,72),(39,82)],INK,1.6)
 stages={'learning':'学习','guided-practice':'引导练习','independent':'独立应用','feedback':'本次反馈'}
 center(68,stages[mode],17)
 circle(346,77,22,'#EEF1ED')
 for x in [340,346,352]:circle(x,77,1.2,INK)
 for i in range(4): rect((24+i*87,116,103+i*87,119),ACC if i<={'learning':0,'guided-practice':1,'independent':2,'feedback':3}[mode] else '#E0E6E0',1)
 # Three stable regions: task header, grouped content, fixed action dock.
 rect((0,132,390,248),'white')
 rect((0,248,390,686),'white')
 line([(0,248),(390,248)],LINE)
 if mode=='learning':
  txt(24,150,'约同学打篮球',24)
  txt(24,193,'Alex 三点没空，试着换个时间。',15,SUB)
  rect((0,270,390,619),'white')
  txt(24,291,'学习表达',14,ACC)
  txt(24,331,'Alex: I’m not free at three.',16,SUB,EN)
  line([(24,368),(366,368)],LINE)
  txt(24,398,'How about',32,INK,EN)
  txt(24,440,'four thirty?',32,INK,EN)
  txt(24,490,'那四点半怎么样？',17,SUB)
  rect((24,546,242,590),TINT,14)
  play(42,562);txt(65,560,'听示范',15,ACC)
  rect((254,546,366,590),'#F2F4F1',14);txt(290,560,'慢速',15,ACC)
 elif mode in ['guided-practice','independent']:
  rect((0,132,390,248),'white')
  txt(24,144,'提出双方可行的时间',21)
  txt(24,190,'我有空',14,SUB)
  for x,t in [(88,'17:00' if mode=='guided-practice' else '10:00'),(169,'18:00' if mode=='guided-practice' else '14:00')]:
   rect((x,182,x+72,214),TINT,9);txt(x+11,190,t,15,ACC,EN)
  txt(24,270,'Alex',13,SUB,EN)
  rect((24,295,311,366),'#F3F5F2',16)
  txt(40,311,'Let’s play basketball.',19,INK,EN)
  txt(40,340,'When are you free?',19,INK,EN)
  txt(326,384,'我',13,SUB)
  rect((85,409,366,478),TINT,16)
  txt(101,425,'Are you free',19,INK,EN)
  txt(101,452,'at five?' if mode=='guided-practice' else 'at ten?',19,INK,EN)
  txt(24,496,'Alex',13,SUB,EN)
  rect((24,521,344,625),'#F3F5F2',16)
  txt(40,536,'I’m not free at five.' if mode=='guided-practice' else 'I’m not free at ten.',19,INK,EN)
  txt(40,565,'What about later?',19,INK,EN)
  txt(40,601,'播放语音',14,ACC)
  if mode=='guided-practice':txt(263,601,'翻译',14,ACC)
 elif mode=='feedback':
  txt(24,150,'这次协商完成了',24)
  txt(24,193,'你提出了双方都有空的时间。',15,SUB)
  rect((0,270,390,456),'white')
  txt(24,291,'完成证据',14,ACC)
  txt(24,335,'How about two?',26,INK,EN)
  line([(24,384),(366,384)],LINE)
  txt(24,407,'14:00 符合双方的时间安排',15,SUB)
  line([(24,465),(366,465)],LINE)
  txt(24,498,'下一步',14,ACC)
  txt(24,540,'换一个场景，再试一次。',19)
 # Compact fixed dock; only conversation history scrolls above it.
 rect((0,686,390,844),'white')
 line([(0,686),(390,686)],LINE)
 if mode=='feedback':
  primary(711,'完成学习')
 else:
  txt(24,707,'跟着示范说' if mode=='learning' else '轮到你了',16)
  if mode=='guided-practice':
   rect((274,694,366,738),TINT,13);txt(289,708,'给我提示',14,ACC)
  primary(753,'录音跟读' if mode=='learning' else '点击说话')
 rect((132,822,258,827),INK,3)
 dest=ROOT/f'v6-{mode}-compact.png';im.save(dest)
 return im

if __name__=='__main__':
 modes=['learning','guided-practice','independent','feedback']
 imgs=[render(m) for m in modes]
 board=Image.new('RGB',(4*430*S,960*S),'#E8EDE8');bd=ImageDraw.Draw(board)
 labels=['学习 · 听懂并跟读','引导练习 · 按需帮助','独立应用 · 新任务','反馈 · 清楚下一步']
 for i,(im,label) in enumerate(zip(imgs,labels)):
  x=(20+i*430)*S;board.paste(im,(x,80*S))
  bd.text((x,28*S),label,font=ImageFont.truetype(CN,19*S),fill=INK)
 board.save(ROOT/'v6-ui-compact-overview.png')
 print('Rendered four screens and overview')
