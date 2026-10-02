"""原创子目标；顺序对应原地图同一家族的节点顺序。不是标准的译文。"""
FACETS = {
'CONTACT': '''回应问候|主动问候|回应告别
说出姓名与身份|询问对方姓名|回应介绍
用熟悉话题开场|回应对方信息|问一个相关问题
承接上一条信息追问|补充自己的相关经历|用过渡表达换话题
判断加入交谈的时机|联系他人发言接话|维持并适当地结束交谈
识别加入或结束的间接信号|在多人轮次间自然接话|根据关系调整开场和退出
识别含蓄社交意图|传达细微态度并保留余地|澄清暗示而不破坏交谈''',
'INFO': '''说出姓名|识别所问的数字|用词或短语回应
询问时间与地点|提供联系方式|核对听到的信息
询问与说明日程|获取与说明路线|核对数量和单位
发现缺失的关键细节|提出针对性追问|复述核查所得信息
区分各来源的说法|指出具体矛盾|提出核查问题
明确结论适用范围|说明信息来源和可信程度|追问隐含条件
区分事实推断和概括|精确说明例外与边界|修正过度概括''',
'DESCRIBE': '''指出所指人物|说出物品名称|用词说明一个属性
说明人物基本特征|描述物品属性|说明熟悉地点的位置和特点
说明生活习惯和频率|描述周围环境|回应关于描述的追问
说明变化前后的差异|给出变化的具体例子|解释变化对自己的影响
选择描述的组织顺序|突出主要特点|用细节说明复杂现象
判断听者需要的背景|重组复杂描述|核查并补充听者不理解的部分
选择精确的感官或概念细节|保持描述视角与风格|解释细微差别''',
'NEEDS': '''指出所需物品|表达想要|表达不想要
表达喜欢或不喜欢|说明基本感受|提出即时需求
说明更喜欢哪一项|给出一个偏好理由|回应对方偏好
说明感受发生的变化|解释与感受相关的经历|询问并回应对方体验
区分同时存在的不同感受|说明相互冲突的需要|表达权衡后的优先选择
表达敏感感受而不臆测对方|说明期待的回应|核查对方对感受的理解
区分细微情绪|表达保留或不确定的意见|调节表达强度''',
'STORY': '''说出日常活动|标明简单先后顺序|补充时间信息
标明过去的时间与事件|按顺序简述经历|另行说明未来计划
交代事件背景|连接原因与结果|回应经历相关追问
组织多个事件|突出关键转折|解释事件后果
根据沟通目的调整结构|补充复杂经历的必要背景|回应对叙述关系的质疑
保持并调整叙述视角|用修辞传达微妙意义|区分事实叙述与态度''',
'EXPLAIN': '''说明物品所在位置|说明物品用途|回应简单用途问题
按顺序说明操作步骤|描述观察到的问题|确认对方理解步骤
描述故障现象|解释已知原因并说明不确定处|提出并说明可行处理办法
区分多个影响因素|说明条件和限制|解释因素之间的关系
根据听者背景选择解释方式|分段说明复杂过程|用改述或例子消除理解障碍
精确表达机制与条件关系|说明例外和反例|修正易引起误解的解释''',
'REQUEST': '''吸引对方注意|请求具体帮助|回应帮助提议
提出简单请求|接受请求|拒绝请求
发出包含活动的邀请|接受或婉拒邀请|提出替代活动或时间
根据关系选择请求语气|说明请求原因|回应对方的追问
说明请求范围|协商可接受的范围|根据负担程度调整礼貌
提出敏感请求|明确对方可以拒绝或选择|回应保留意见
判断关系和权力对表达的影响|用含蓄方式提出请求|澄清真实请求范围''',
'ARRANGE': '''提出一个时间或地点|理解对方提议|确认最终安排
说明原时间不方便|提出可行替代时间|核对双方最终安排
获取各方限制条件|提出满足限制的共同计划|确认职责和时间
比较不同方案|表达可接受的取舍|确认协商结果
澄清各方利益与分歧|提出调整方案|核查各方是否同意
澄清模糊目标|明确冲突与权衡|总结并促成可执行决定''',
'SERVICE': '''说出所需物品|说明数量|回应简单确认
说明要买或点的东西|询问价格|核对商品数量与价格
询价并核对费用范围|完成预订并确认条件|问路并核对关键路线
说明预订与实际的差异|提出退换请求并说明原因|描述服务故障并请求处理
组织复杂问题的事实和时间线|提出处理诉求及理由|协商并确认解决方案
指出不明确的条款|核查责任和例外|复述确认最终理解''',
'COMPARE': '''指出共同属性|说明一项差异|表达简单选择
按同一标准比较价格|按位置等标准比较|说明比较后的偏好
按多个标准比较选择|给出推荐及理由|回应推荐相关追问
比较短期与长期影响|说明风险和收益|表达权衡及条件
区分证据与主张|说明证据的局限|给出有条件的推荐
识别隐性权衡|精确说明条件变化的影响|限定比较结论''',
'OPINION': '''表达赞同|表达不赞同|回应对方立场
说出自己的观点|给出一个原因|询问对方观点
组织观点与理由|给出相关例子|回应针对观点的追问
建立论点与证据联系|准确理解反对意见|回应反对意见并限定结论
区分复杂议题的不同论点|说明论证的条件与假设|回应抽象议题的质疑
区分细微立场差异|公平重述对方论证|调整或反驳论证中的具体环节''',
'RELATE': '''回应感谢|回应简单道歉|用熟悉礼貌表达结束回应
表达感谢并回应|表达道歉并回应|祝贺并回应祝贺
婉拒提议|表达关心|解释简单理由
说明具体分歧|核查误会发生在哪里|解释原意并修复误会
表达个人边界|给出具体建设性反馈|回应反馈并协商后续
识别隐含立场|表达敏感分歧|调整语气并核查理解
区分立场与关系信号|精确调节语气和表达强度|回应高敏感交流中的含蓄意图''',
'COLLAB': '''理解共同任务|轮流贡献相关信息|确认共同结果
汇报完成情况|澄清任务要求|承接他人发言
在多人讨论中贡献相关意见|总结行动事项|确认责任人和期限
提出议程并组织讨论|帮助他人加入发言|总结分歧和共识
跟进快速复杂讨论|重构分歧双方的意思|促成共同理解并核对''',
'REPAIR': '''表示没听懂|请求帮助|在支持下重新回应
请求重复|请求放慢|请求拼写关键词
复述确认关键意思|指出不理解的词或部分|缺词时用简单描述补足
指出误解的具体位置|换一种说法解释|核查误解是否解决
追问歧义中的指代或条件|区别多种可能理解|复述核查正确理解
定位复杂理解障碍|分段重新组织意思|逐段确认理解
自然重构复杂表达|保留细微限定和态度|确认改述未改变原意''',
'LISTEN': '''识别熟悉问题|识别所需数字|选择与听到内容匹配的回应
识别短问句的询问信息|理解慢速简单指令|依据指令行动
识别短对话的沟通意图|提取时间数量等关键细节|区分否定或改变条件的信息
理解熟悉话题主旨|连接关键细节|针对遗漏提出追问
跟进较长解释的结构|区分说话者观点|理解理由与结论的关系
识别未明说的立场|利用语体和语调理解态度|连接未明确标示的信息关系
跟进快速复杂交流|区分细微含义与限定|核查推断与原话的区别''',
'MEDIA': '''识别公告主题|提取时间|提取地点并采取相应行动
识别常见公告目的|提取语音消息关键细节|依据消息采取行动
概括熟悉主题音频主旨|提取相关细节|区分事件顺序
区分访谈中各方观点|识别观点的论据|概括节目主要信息
识别长音频的隐含结构|追踪主题转换|理解未明确表达的态度
跟进快速密集信息|识别修辞与立场|解释字面意义和意图的差别''',
'PHONE': '''识别来电者与目的|在支持下提供简单信息|确认并结束通话
说明预约需求并商定时间|留下简短语音消息|听取并核对留言
说明熟悉事项的来电目的|请求重复或澄清听不清的部分|确认通话结果
说明通信故障并恢复交流|协调多个远程限制条件|总结并确认安排
管理远程会议发言轮次|澄清多方信息|总结决议并核查理解''',
'MEDIATE': '''提取要转告的时间|提取价格或地点|准确转告给另一人
提取简短消息的关键事实|转述指令的必要步骤|核对接收者理解
概括他人的主要意见|区分原意见与自己的解释|根据第三人的需要改述
分别呈现不同人的意见|指出分歧和共同点|转述以帮助澄清
定位复杂讨论的理解障碍|调整语言帮助各方理解|核查共同理解是否建立
精确重述复杂含蓄信息|保持原有立场和限定|消除歧义并核查各方理解''',
}
SUPPORT = {
'SOUND.CONTRAST':'听辨意义相关音差|在词中说出区别|在沟通中保持可理解',
'SOUND.ENDING':'听出词尾的关键意义|说清必要词尾|核查是否造成数量或时间误解',
'SOUND.SYLLABLE':'辨识音节与词重音|根据声音说出陌生词|在句中保持词可识别',
'SOUND.STRESS':'识别对方强调的信息|突出自己的焦点|用对比重音纠正误解',
'SOUND.REDUCTION':'识别常见缩略形式|听辨熟悉词的弱读连读|在原速新句中识别',
'SOUND.GROUP':'按意义切分信息|在合适边界停顿|保持组块之间的关系',
'SOUND.INTONATION':'识别疑问和态度信号|用语调标示表达意图|用语调标示结束或继续',
'SOUND.VARIETY':'识别不同口音下的熟悉信息|适应新说话者|利用澄清修复理解',
'LEX.RETRIEVE':'从意图提取已知表达|遮住答案独立说出|换情境后仍可提取',
'LEX.CHUNK':'理解表达块的功能|替换可变部分|组合表达块完成新意思',
'LEX.PARAPHRASE':'描述缺失词的特征或用途|用更熟悉词改述|确认对方理解',
'LEX.REGISTER':'判断对象与关系|选择合适搭配和语气|解释或修正不适切表达',
'FORM.QUESTION':'识别所需询问信息|构造可理解问句|根据回应继续追问',
'FORM.TIME':'识别事件时间|表达过去现在未来|区分相互关联事件的先后',
'FORM.CONDITION':'理解条件与结果|表达可能性和建议|明确条件适用范围',
'DISCOURSE.LINK':'连接原因和结果|连接对比信息|总结与前文一致的结论',
'DISCOURSE.HEDGE':'区分确定与不确定|表达可信程度|明确例外与适用范围',
'STRATEGY.PLAN':'用关键词准备|由提示过渡到独立表达|在新任务中快速组织内容',
'STRATEGY.MONITOR':'发现影响意义的错误|及时纠正|核查纠正是否被理解',
'STRATEGY.TURN':'识别接话时机|保持或接续发言|交出轮次并回应',
'LEX.ACQUIRE':'建立声音和意义联系|听辨新词句|从意图独立提取并组合',
'FORM.CLAUSE':'组合主语和谓语|补充必要对象或信息|按意图调整基本句子',
'FORM.NEGATION':'识别否定范围|表达否定|纠正对方不正确的信息',
'FORM.QUANTITY':'理解数量与单位|表达数量和程度|比较并核查差异',
'FORM.SPACE':'理解位置关系|说明方向与目标|核查路线和位置',
'DISCOURSE.REFERENCE':'使用明确指代|追踪指代对象|必要时复述消除歧义',
}
# 英文检索范围由沟通功能设定；候选关系不伪装成官方等价关系。
KEYWORDS = {
'CONTACT':['greet','introduc','conversation','small talk','social'],
'INFO':['information','detail','fact','question','clarif','number','personal'],
'DESCRIBE':['describ','appearance','place','object','experience'],
'NEEDS':['feel','prefer','like','need','emotion','want'],
'STORY':['narrat','story','past','event','experience','sequence'],
'EXPLAIN':['explain','instruction','process','problem','reason','cause'],
'REQUEST':['request','invit','offer','permission','refus','polite','suggest'],
'ARRANGE':['arrange','plan','suggest','agreement','decision','negotiat','schedule'],
'SERVICE':['service','transaction','reservation','shop','price','buy','goods','complaint','direction'],
'COMPARE':['compar','choice','alternative','recommend','advantage','evaluat'],
'OPINION':['opinion','argument','point of view','reason','disagree','discussion'],
'RELATE':['apolog','thank','congratulat','polite','disagree','feeling','critic','attitude'],
'COLLAB':['discussion','meeting','turn','group','participat','collaborat','contribution'],
'REPAIR':['clarif','repeat','paraphras','rephras','understood','understand','check'],
'LISTEN':['understand','recognis','identify','follow','extract'],
'MEDIA':['record','broadcast','announcement','interview','audio','radio','television','documentar'],
'PHONE':['phone','telephone','call','message','remote'],
'MEDIATE':['summaris','summariz','paraphras','relay','rephras','explain','reformulat'],
'SOUND':['pronunc','intonation','stress','articulat','phonolog','accent','spoken'],
'LEX':['word','phrase','vocab','paraphras','express','language'],
'FORM':['question','past','future','present','negat','condition','clause','quantity','place','gramma'],
'DISCOURSE':['link','coheren','structure','connect','qualif','discourse','reference'],
'STRATEGY':['check','clarif','repair','turn','prepar','rephras','conversation'],
}

# 每个沟通节点的英文功能检索词，顺序仍对应原节点；避免只按家族宽泛词命中。
ANCHORS = {
'CONTACT': 'greet;farewell\nintroduce themselves;name\nsmall talk;start or end;show interest\nkeep a conversation;change the topic;maintain and close\nengage in extended;participatory;conversation already\njoin a conversation;fast-paced conversation;conversational cues\nimplicit;nuance;subtle',
'INFO': 'say their name;numbers\nphone number;time of day;dates;personal details\narrangements;directions;quantities\ncheck facts;check understanding;detailed information\ncontradiction;different sources;precision of questions\nqualify;precisely;reliability\nqualify;precision;ambiguity',
'DESCRIBE': 'name a few;describe objects\ndescribe objects;physical appearance;describe where\ndaily routines;home town;living conditions\nchanges;feelings and reactions\ndetailed description;characteristics;describe the personal\ncomplex descriptions;listener;audience\nsubtle;nuance;detailed descriptions',
'NEEDS': 'wants;want;food and drink\nlikes and dislikes;feel;needs\nreasons to explain preferences;explain what they like\nfeelings and reactions;respond to feelings\nfeelings;emotions;mood\nfeelings;emotional;check understanding\nnuance;subtle;degree of',
'STORY': 'daily routines;simple phrases;sequence\nevents in the past;future plans;plans for the near future\nnarrate a story;linear sequence;relate a straightforward\nnarrate a story in detail;plot and sequence\nelaborate narratives;complex narrative\nnuance;subtle;narrative',
'EXPLAIN': 'position of things;what something is used for\nsimple instructions;everyday process;technical problem\nsolutions to problems;main points in an idea or problem\nproblem-solution;explain complex;conditions\ncomplex procedure;listener;problem-solution\ncomplex;exceptions;precise',
'REQUEST': 'ask for help;immediate personal needs\nagree to simple requests;basic requests;decline offers\nsimple invitations;refuse requests;respond to suggestions\npolite requests;requests politely;permission;request\nrequests;negotiate;politeness\nsensitive;polite;requests\nimplicit;subtle;politeness',
'ARRANGE': 'arrangements to meet;time of day;agreement\narrangements to meet;schedule;confirm information;excuses\ncommon goal;future arrangements;plans;conflict\nnegotiation;alternatives;compromise\nnegotiating position;resolve conflicts;complex negotiation\nresolve conflicts;complex negotiation;decision',
'SERVICE': 'objects;numbers, quantities;food and drink\norder a meal;buy tickets;price;simple purchases\nreservation;price;directions\ncomplaint;reservation;exchange;refund\ncomplaint;compensation;negotiate\ncontract;terms;responsibility',
'COMPARE': 'compare;differences\ncomparisons;compare;choice\nadvantages;disadvantages;reasons for a choice\nadvantages;disadvantages;evaluate;alternative\nevaluate;assumptions;recommendations\nsubtle;nuance;evaluate',
'OPINION': 'agreement;disagreement\nsimple opinions;simple reasons\nreasons for their opinions;point of view;examples\ndevelop an argument;counter-arguments;defend\ncomplex arguments;abstract;counter-argument\nnuance;subtle;arguments',
'RELATE': 'politeness;apology;thank\napology;congratulat;thank\nrefuse;encouragement;feelings\ndisagree;misunderstanding;apology\ncriticism;feedback;disagreement\nsensitive;controversial;implicit\nsubtle;nuance;attitude',
'COLLAB': 'simple task;take part;discussion\nprogress;discussion;turn\ngroup discussion;meeting;action\nchair;manage discussions;encourage;contribution\ncomplex discussions;synthesise;reformulate',
'REPAIR': 'repetition\nrepeat;slowly;spell\nclarify;clarification;word they;circumlocution\nmisunderstand;rephrase;clarification\nprecision of questions;clarification;ambiguous\nreformulation;paraphrase;clarify\nclarify;nuance;reformulate',
'LISTEN': 'cardinal numbers;basic questions\nquestions addressed;simple instructions\nsimple dialogues;arrangements;factual information\nmain points;misunderstanding;familiar topics\ncomplex arguments;different points of view;extended\nimplied;implicit;register;attitude\nabstract and complex;nuance;variety of accents',
'MEDIA': 'announcements;recorded message\nannouncements;audio recordings;voicemail\nradio;audio recording;main points\nradio programme;interviews;documentaries\ncomplex audio;implicit;attitude\ncomplex audio;nuance;irony;rhetoric',
'PHONE': 'phone;caller\nappointment;phone messages;reservation\nphone;clarify information\nteleconference;communication breakdowns;remote\nteleconference;remote;conference call',
'MEDIATE': 'pass on;personal information\npass on;message;instructions\nparaphrase a simple;summarise;other people\nsummarise;reformulate;different views\nreformulation;reformulate;neutral language\nreformulate;subtle;nuance',
}
