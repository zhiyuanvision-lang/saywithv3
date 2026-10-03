"""Render iOS-styled static proposals with PingFang, SF and SF Symbols."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
ROOT=Path(__file__).resolve().parent/'assets'
S=3;W=390;H=844
CN='/System/Library/AssetsV2/com_apple_MobileAsset_Font8/86ba2c91f017a3749571a82f2c6d890ac7ffb2fb.asset/AssetData/PingFang.ttc'
EN='/System/Library/Fonts/SFNS.ttf'
TYPE={'large_title':26,'title':20,'headline':17,'body':17,'example':20,'secondary':15,'caption':13,'tab':10}
INK='#1C1C1E';SUB='#6C6C70';BLUE='#0069D9';PALE='#EAF2FF';BG='#F2F2F7';SEP='#E4E4E9'

def render(mode):
 im=Image.new('RGB',(W*S,H*S),BG);d=ImageDraw.Draw(im);text_regions=[]
 def font(size,bold=False,en=False):return ImageFont.truetype(EN if en else CN,size*S,index=0 if en else (11 if bold else 3))
 def text(x,y,t,size=17,c=INK,bold=False,en=False):
  f=font(size,bold,en);bounds=d.textbbox((0,0),t,font=f)
  assert x+(bounds[2]-bounds[0])/S<=W, (mode,t,'horizontal overflow')
  pos=(int(x*S),int(y*S))
  area=d.textbbox(pos,t,font=f,anchor='lt')
  for previous,other in text_regions:
   overlap=min(area[2],other[2])-max(area[0],other[0])>0 and min(area[3],other[3])-max(area[1],other[1])>0
   assert not overlap,(mode,t,previous,'text overlap')
  text_regions.append((t,area))
  d.text(pos,t,font=f,fill=c,anchor='lt')
 def text_mid(x,cy,t,size=17,c=INK,bold=False,en=False):
  bounds=d.textbbox((0,0),t,font=font(size,bold,en),anchor='lt')
  h=(bounds[3]-bounds[1])/S
  text(x,cy-h/2,t,size,c,bold,en)
 def center_mid(cy,t,size=17,c=INK,bold=False):
  bounds=d.textbbox((0,0),t,font=font(size,bold),anchor='lt')
  text_mid((W-(bounds[2]-bounds[0])/S)/2,cy,t,size,c,bold)
 def center(y,t,size=17,c=INK,bold=False):
  f=font(size,bold);b=d.textbbox((0,0),t,font=f);text((W-(b[2]-b[0])/S)/2,y,t,size,c,bold)
 def box(b,c='white',r=0):
  b=tuple(int(v*S) for v in b)
  if r:d.rounded_rectangle(b,r*S,fill=c)
  else:d.rectangle(b,fill=c)
 def rule(y,x0=0,x1=W):d.line((x0*S,y*S,x1*S,y*S),fill=SEP,width=S)
 def symbol(name,x,y,size=22,c=INK):
  src=Image.open(ROOT/'symbols'/f'{name}.png').convert('RGBA')
  alpha=src.getchannel('A');bounds=alpha.getbbox()
  if bounds:src=src.crop(bounds)
  ratio=min(size*S/src.width,size*S/src.height);src=src.resize((round(src.width*ratio),round(src.height*ratio)),Image.Resampling.LANCZOS)
  tint=Image.new('RGBA',src.size,c);tint.putalpha(src.getchannel('A'))
  im.paste(tint,(round(x*S+(size*S-src.width)/2),round(y*S+(size*S-src.height)/2)),tint)
 def button(y,label,mic=False):
  box((20,y,370,y+50),BLUE,12)
  if mic:
   f=font(17,True);b=d.textbbox((0,0),label,font=f);tw=(b[2]-b[0])/S
   left=(W-(tw+29))/2
   symbol('mic.fill',left,y+15.5,19,'white');text_mid(left+29,y+25,label,17,'white',True)
  else:center_mid(y+25,label,17,'white',True)
 def nav(title):
  box((0,44,390,101),'#FAFAFC')
  # Minimal back affordance; native implementation labels it for VoiceOver.
  symbol('chevron.right',16,64,16,BLUE)
  # Flip the back symbol in place.
  patch=im.crop((16*S,64*S,32*S,80*S));im.paste(patch.transpose(Image.Transpose.FLIP_LEFT_RIGHT),(16*S,64*S))
  center_mid(72.5,title,17,bold=True)
  symbol('ellipsis',345,60,23,BLUE);rule(100)
 def dock(label='按住说话',help=False):
  box((0,707,390,844),'#FAFAFC');rule(707)
  button(730,label,mic=True)
  if help:center_mid(800,'提示',15,BLUE)
 def bubble(x,y,width,lines,mine=False,audio=False):
  words=' '.join(lines).split();lines=[];current='';f=font(TYPE['body'],en=True)
  for word in words:
   candidate=(current+' '+word).strip()
   if current and d.textlength(candidate,font=f)>(width-28)*S:
    lines.append(current);current=word
   else:current=candidate
  if current:lines.append(current)
  last_height=d.textbbox((0,0),lines[-1],font=f,anchor='lt')[3]/S
  text_bottom=12+(len(lines)-1)*24+last_height
  height=text_bottom+(10+22+12 if audio else 12)
  box((x,y,x+width,y+height),BLUE if mine else 'white',16)
  for i,t in enumerate(lines):text(x+14,y+12+i*24,t,TYPE['body'],'white' if mine else INK,en=True)
  if audio:
   cy=y+text_bottom+10+11
   symbol('speaker.wave.2.fill',x+14,cy-9.5,19,BLUE)
  return y+height
 # Status bar and safe-area home indicator are consistent across pages.
 text(27,15,'9:41',15,bold=True,en=True)
 for i,h in enumerate([4,6,9,12]):box((304+i*4,28-h,306+i*4,28),INK,1)
 box((330,17,353,28),INK,3);box((354,20,356,25),INK,1)
 if mode=='home':
  text(20,70,'学习',TYPE['large_title'],bold=True)
  text(20,117,'今日复习',15,SUB)
  box((20,143,370,290),'white',16)
  text(38,161,'商量时间与说明原因',TYPE['headline'],bold=True)
  text(38,189,'2 个任务 · 约 4 分钟',15,SUB)
  box((38,222,352,272),BLUE,12);center_mid(247,'开始复习',17,'white',True)
  text(20,318,'继续学习',15,SUB)
  box((20,344,370,423),'white',16)
  symbol('book',37,371,25,BLUE)
  text(78,361,'回应邀请',17,bold=True)
  text(78,389,'接受或婉拒',15,SUB)
  symbol('chevron.right',338,377.5,12,SUB)
  box((0,761,390,844),'#FAFAFC');rule(761)
  for name,x,label,selected in [('book.fill',53,'学习',True),('chart.bar',184,'进展',False),('person.crop.circle',313,'我的',False)]:
   symbol(name,x,772,24,BLUE if selected else SUB)
   text_mid(x+12-d.textlength(label,font=font(10))/S/2,806,label,10,BLUE if selected else SUB)
 elif mode in ['review','guided','independent']:
  nav('复习' if mode=='review' else ('引导练习' if mode=='guided' else '独立应用'))
  box((0,101,390,202),'#FAFAFC')
  text(20,123,'商量开会时间' if mode=='review' else '约同学打篮球',TYPE['title'],bold=True)
  if mode=='review':text_mid(342,134,'1/2',13,SUB,en=True)
  text_mid(20,171.5,'我有空',13,SUB)
  times=('14:00','16:00') if mode=='review' else (('17:00','18:00') if mode=='guided' else ('10:00','14:00'))
  for x,t in zip([82,163],times):box((x,157,x+70,186),PALE,7);text_mid(x+11,171.5,t,15,BLUE,en=True)
  rule(201)
  partner='Sam' if mode=='review' else 'Alex'
  # Conversation rhythm follows content height rather than fixed message slots.
  y=222
  text(20,y,partner,13,SUB,en=True)
  y=bubble(20,y+21,296,['Let’s find a time for our meeting.'] if mode=='review' else ['Let’s play basketball. When are you free?'])
  first='two' if mode=='review' else ('five' if mode=='guided' else 'ten')
  sentence=f'Are you free at {first}?'
  mine_width=min(296,d.textlength(sentence,font=font(17,en=True))/S+28)
  y+=18
  text(357,y,'我',13,SUB)
  y=bubble(370-mine_width,y+21,mine_width,[sentence],mine=True)
  y+=18
  text(20,y,partner,13,SUB,en=True)
  y=bubble(20,y+21,296,[f'I’m busy at {first}. Could we meet later?'] if mode=='review' else [f'I’m not free at {first}. What about later?'],audio=True)
  assert y<687,(mode,'conversation overlaps action dock')
  dock(help=mode!='independent')
 elif mode=='learning':
  nav('学习')
  text(20,123,'约同学打篮球',TYPE['title'],bold=True)
  text(20,154,'Alex 三点没空，你想改约四点半。',15,SUB)
  box((20,185,370,261),'white',16)
  text(38,201,'Alex',13,SUB,en=True)
  text(38,226,'I’m not free at three.',17,en=True)
  text(20,285,'重点表达',17,bold=True)
  box((20,314,370,458),'white',16)
  text(38,332,'How about four thirty?',TYPE['example'],en=True)
  text(38,365,'那四点半怎么样？',TYPE['secondary'],SUB)
  rule(396,38,352)
  symbol('speaker.wave.2.fill',38,416.5,21,BLUE)
  dock('按住跟读')
 else:
  nav('复习结果' if mode=='review-result' else '任务反馈')
  text(20,123,'复习完成' if mode=='review-result' else '任务完成',TYPE['title'],bold=True)
  text(20,154,'2 个任务，已记录本次表现。' if mode=='review-result' else '你提出了双方可行的时间。',TYPE['secondary'],SUB)
  box((20,186,370,320),'white',16)
  symbol('checkmark.circle.fill',38,204,22,BLUE)
  text_mid(72,215,'商量时间',17,bold=True)
  text(38,238,'隔期仍能独立完成' if mode=='review-result' else '本次独立完成',15,BLUE)
  text(38,262,'How about four?' if mode=='review-result' else 'How about two?',TYPE['example'],en=True)
  text(38,293,'符合双方的时间安排',13,SUB)
  if mode=='review-result':
   box((20,336,370,434),'white',16)
   text(38,352,'说明原因',17,bold=True)
   text(38,379,'借助提示完成',15,SUB)
   text(38,406,'下一次换个任务再练。',15,SUB)
  box((0,707,390,844),'#FAFAFC');rule(707)
  button(730,'完成复习' if mode=='review-result' else '完成学习')
  center(793,'查看本次记录',13,BLUE)
 box((132,827,258,832),INK,3)
 im.save(ROOT/f'v6-{mode}-ios-hold.png');return im

def board(modes,labels,name):
 out=Image.new('RGB',(len(modes)*430*S,936*S),'#E5E5EA');d=ImageDraw.Draw(out)
 for i,(m,l) in enumerate(zip(modes,labels)):
  x=(20+i*430)*S;out.paste(render(m),(x,64*S));d.text((x,22*S),l,font=ImageFont.truetype(CN,17*S,index=11),fill=INK)
 out.save(ROOT/name)

if __name__=='__main__':
 board(['home','review','review-result'],['学习首页','复习会话','复习结果'],'v6-review-ios-hold-overview.png')
 board(['home','review'],['学习首页','复习会话'],'v6-review-ios-hold-entry.png')
 board(['learning','guided','independent','result'],['学习','引导练习','独立应用','任务反馈'],'v6-ui-ios-hold-overview.png')
 board(['learning','result'],['学习 · 重点表达','反馈 · 页面标题'],'v6-typography-hold-overview.png')
 print('Rendered seven screens with unified typography and four overview images')
