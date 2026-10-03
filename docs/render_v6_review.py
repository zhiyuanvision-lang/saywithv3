"""Static review-flow proposals using the approved full-width layout."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
ROOT=Path(__file__).resolve().parent/'assets';ROOT.mkdir(exist_ok=True)
S=3;CN='/System/Library/Fonts/STHeiti Medium.ttc';EN='/System/Library/Fonts/SFNS.ttf'
INK='#172923';SUB='#617069';ACC='#17634D';TINT='#E6EFE9';LINE='#E1E6E2'

def render(mode):
 im=Image.new('RGB',(390*S,844*S),'white');d=ImageDraw.Draw(im)
 def text(x,y,t,size=17,color=INK,font=CN):d.text((int(x*S),int(y*S)),t,font=ImageFont.truetype(font,size*S),fill=color)
 def rect(b,c,r=0):
  b=tuple(int(v*S) for v in b)
  if r:d.rounded_rectangle(b,r*S,fill=c)
  else:d.rectangle(b,fill=c)
 def line(points,c=LINE,w=1):d.line([(x*S,y*S) for x,y in points],fill=c,width=w*S)
 def center(y,t,size=17,color=INK):
  f=ImageFont.truetype(CN,size*S);width=d.textbbox((0,0),t,font=f)[2]/S;text((390-width)/2,y,t,size,color)
 def button(y,label):rect((24,y,366,y+54),ACC,16);center(y+17,label,17,'white')
 def circle(x,y,r,c):d.ellipse(((x-r)*S,(y-r)*S,(x+r)*S,(y+r)*S),fill=c)
 text(28,18,'9:41',15,font=EN)
 for i,h in enumerate([4,6,9,12]):rect((306+i*4,30-h,308+i*4,30),INK)
 rect((334,19,357,30),INK,3);rect((358,22,360,27),INK,1)
 if mode=='home':
  rect((0,42,390,756),'#F3F5F3')
  text(24,72,'学习',30)
  rect((24,144,366,438),'white',22)
  text(44,166,'今日复习',15,ACC)
  text(44,212,'商量时间',27)
  text(44,253,'说明原因',19,SUB)
  text(44,299,'约 4 分钟 · 2 个任务',14,SUB)
  rect((44,358,346,414),ACC,16)
  center(377,'开始复习',18,'white')
  text(24,480,'继续课程',18)
  rect((24,520,366,622),'white',20)
  text(44,542,'回应邀请',21)
  text(44,579,'接受或婉拒',14,SUB)
  line([(331,561),(339,569),(331,577)],ACC,2)
  line([(0,756),(390,756)])
  line([(67,778),(77,772),(87,778),(77,784),(67,778)],ACC,2)
  line([(68,783),(77,789),(86,783)],ACC,2)
  for x,h in [(188,8),(195,14),(202,20)]:rect((x,792-h,x+3,792),SUB,1)
  circle(320,778,5,SUB)
  d.arc((310*S,782*S,330*S,799*S),180,360,fill=SUB,width=2*S)
  for x,t in [(62,'学习'),(181,'进展'),(306,'我的')]:text(x,799,t,12,ACC if t=='学习' else SUB)
 elif mode=='task':
  circle(44,77,22,'#EEF1ED');line([(39,72),(49,82)],INK,2);line([(49,72),(39,82)],INK,2)
  center(68,'复习 · 1 / 2')
  rect((24,113,366,116),LINE,1);rect((24,113,195,116),ACC,1)
  text(24,139,'商量一个开会时间',21)
  text(24,181,'我有空',14,SUB)
  for x,t in [(88,'14:00'),(169,'16:00')]:rect((x,175,x+72,207),TINT,9);text(x+11,183,t,15,ACC,EN)
  line([(0,230),(390,230)])
  text(24,250,'Sam',13,SUB,EN)
  rect((24,275,317,344),'#F3F5F2',16)
  text(40,291,'Let’s find a time',19,font=EN);text(40,317,'for our meeting.',19,font=EN)
  text(326,363,'我',13,SUB)
  rect((85,388,366,465),TINT,16)
  text(101,405,'Are you free',19,font=EN);text(101,432,'at two?',19,font=EN)
  text(24,486,'Sam',13,SUB,EN)
  rect((24,511,344,625),'#F3F5F2',16)
  text(40,527,'I’m busy at two.',19,font=EN)
  text(40,554,'Could we meet later?',19,font=EN)
  text(40,593,'播放语音',14,ACC)
  line([(0,686),(390,686)])
  text(24,706,'你的回应',16)
  rect((274,694,366,738),TINT,13);text(289,708,'需要帮助',14,ACC)
  button(753,'开始录音')
 else:
  center(68,'复习结果');line([(0,113),(390,113)])
  text(24,144,'今天的复习完成了',24)
  text(24,190,'2 个任务，已记录本次表现。',15,SUB)
  line([(0,232),(390,232)])
  text(24,258,'协商时间',19);text(24,294,'隔期仍能独立完成',15,ACC)
  rect((24,331,366,399),'#F3F5F2',14)
  text(40,346,'How about four?',20,font=EN)
  text(40,376,'16:00 符合双方的时间安排',13,SUB)
  line([(24,424),(366,424)])
  text(24,450,'说明原因',19);text(24,486,'借助提示完成',15,ACC)
  text(24,527,'表达了原因，但仍需要句型帮助。',15,SUB)
  line([(24,570),(366,570)])
  text(24,595,'下一步',14,SUB)
  text(24,628,'换个任务，练习独立说明原因。',17)
  line([(0,686),(390,686)])
  button(711,'完成复习');center(780,'查看本次记录',14,ACC)
 rect((132,822,258,827),INK,3)
 im.save(ROOT/f'v6-review-{mode}-simple.png');return im

if __name__=='__main__':
 modes=['home','task','result'];imgs=[render(m) for m in modes]
 board=Image.new('RGB',(1290*S,960*S),'#E8EDE8');d=ImageDraw.Draw(board)
 labels=['首页 · 一个主要入口','会话 · 直接开始对话','结果 · 简短反馈']
 for i,(im,t) in enumerate(zip(imgs,labels)):
  x=(20+430*i)*S;board.paste(im,(x,80*S));d.text((x,28*S),t,font=ImageFont.truetype(CN,19*S),fill=INK)
 board.save(ROOT/'v6-review-simple-overview.png')
 intro=Image.new('RGB',(860*S,960*S),'#E8EDE8');dd=ImageDraw.Draw(intro)
 for i,(im,t) in enumerate(zip(imgs[:2],labels[:2])):
  x=(20+430*i)*S;intro.paste(im,(x,80*S));dd.text((x,28*S),t,font=ImageFont.truetype(CN,19*S),fill=INK)
 intro.save(ROOT/'v6-review-simple-entry.png')
 print('Rendered simplified home, direct conversation and results')
