import SwiftUI

struct LessonScreen:View {
    @Bindable var model:LearningModel
    @State private var audio=AudioController()
    @State private var learningShadow=false
    @State private var showTranscriptCorrection=false
    @State private var correctedTranscript=""
    @State private var correctionFeedback:LearningPracticeView.Feedback?
    @State private var summaryAdvice:ReplyAdvice?
    @State private var summaryAdviceLoading=false
    @State private var summaryAdviceFailed=false
    @State private var showAdvice=false
    @State private var advice:ReplyAdvice?
    @State private var adviceLoading=false
    @State private var adviceError:String?
    @State private var adviceTurnID:String?
    @State private var repairReady=false
    @State private var showHints=false
    @State private var selectedHint:String?
    @State private var hintCache:[String:Dialogue]=[:]
    @State private var hintExplanationVisible=false
    @State private var hintTranslationVisible=false
    @State private var showCourseExpressions=false
    @State private var feedbackOpen=false
    @State private var showTaskInfo=false
    @State private var followConversation=true
    @State private var playedTurns:Set<String>=[]
    @State private var shownTranslations:Set<String>=["material:0"]
    @State private var showExit=false
    @State private var showReturn=false
    @State private var showHistory=false
    @State private var showUsage=false
    @State private var showDemo=false
    @State private var demoTask:Task<Void,Never>?
    @State private var highlightedLine:Int?
    @State private var loadingAudioID:String?
    @State private var playbackTask:Task<Void,Never>?
    @State private var playbackToken=UUID()
    @State private var hold=HoldRecordingGesture()
    @State private var recordingStartTask:Task<Void,Never>?
    @State private var retryingShadow=false
    @Environment(\.scenePhase) private var scenePhase
    @Environment(\.dynamicTypeSize) private var typeSize
    private var current:SessionState? {model.session}
    private var phase:String {current?.view.phase ?? "learning"}
    private var isReview:Bool {current?.view.entryKind=="review"}
    private var isGuided:Bool {phase=="supported_practice"}
    private var isIndependent:Bool {phase=="independent_application"}
    private var isFeedback:Bool {phase=="finished"}
    private var learningPractice:LearningPracticeView? {
        guard current?.view.learningPractice?.materialIndex==model.selectedMaterial else {return nil}
        return current?.view.learningPractice
    }
    private var learningPreparationKey:String {
        guard phase=="learning",current?.view.lexicalPractices?.contains(where:{!$0.completed}) != true else {return "inactive"}
        return (current?.view.sessionId ?? "")+":"+String(model.selectedMaterial)
    }
    private var activeMaterial:Material? {
        guard let view=current?.view,view.materials.indices.contains(model.selectedMaterial) else {return nil}
        return view.materials[model.selectedMaterial]
    }
    private var partner:Turn? {current?.turns.last(where:{$0.speaker=="partner"})}
    private var actions:[String] {current?.view.availableActions ?? []}
    private var status:String {
        if audio.recording {return hold.cancelling ? "松开取消":"录音中 · \(Int(audio.duration)) 秒 · 上滑取消"}
        if !model.requestStatus.isEmpty {return model.requestStatus}
        if model.busy {return "正在准备下一步"}
        if phase=="learning" {return learningShadow ? "按住跟读":"按住说话"}
        return repairReady ? "按住再说一次":"轮到你了"
    }
    var body:some View {
        VStack(spacing:0) {
            sessionHeader
            if (isGuided || isIndependent) && !typeSize.isAccessibilitySize {taskRegion.padding(.horizontal,20).padding(.top,22).padding(.bottom,14).background(Color(uiColor:.systemBackground))}
            Divider()
            GeometryReader {viewport in ScrollViewReader {proxy in ScrollView {
                VStack(alignment:.leading,spacing:16) {
                    if !(isGuided || isIndependent) || typeSize.isAccessibilitySize {taskRegion}
                    if phase=="learning" {
                        if let pending=current?.view.lexicalPractices?.first(where:{!$0.completed}) {LexicalPracticeCard(model:model,practice:pending).id(pending.id)} else {learningContent}
                    }
                    else if phase=="guided_feedback" {guidedSummary}
                    else if isFeedback {feedbackContent}
                    else {conversationContent}
                    Color.clear.frame(height:1).id("conversationBottom").background(GeometryReader {geo in Color.clear.preference(key:ConversationBottomKey.self,value:geo.frame(in:.named("lessonScroll")).minY)})
                }.frame(maxWidth:.infinity,alignment:.leading).padding(.horizontal,20).padding(.top,22).padding(.bottom,20)
            }.background(Color(uiColor:.systemGroupedBackground))
                .accessibilityIdentifier("lessonContent").coordinateSpace(name:"lessonScroll")
                .onPreferenceChange(ConversationBottomKey.self) {y in followConversation=y<=viewport.size.height+60}
                .onChange(of:(current?.turns.last?.turnId ?? "")+(model.outgoingMessage?.id ?? "")) {_,_ in
                    if phase=="learning" || (followConversation && (isGuided || isIndependent)) {proxy.scrollTo("conversationBottom",anchor:.bottom)}
                }
            }}
        }
        .background(Color(uiColor:.systemBackground))
        .safeAreaInset(edge:.bottom,spacing:0) {if phase != "learning" || current?.view.lexicalPractices?.contains(where:{!$0.completed}) != true {footer}}
        .sheet(isPresented:$showAdvice,onDismiss:{audio.stopPlayback()}) {replyAdvicePanel}
        .sheet(isPresented:$showHints) {hintPanel}
        .sheet(isPresented:$showCourseExpressions) {courseExpressionsPanel}
        .sheet(isPresented:$showTaskInfo) {taskInfoPanel}
        .sheet(isPresented:$showUsage) {usagePanel}
        .sheet(isPresented:$showDemo) {demoPanel}
        .sheet(isPresented:$showHistory) {historyPanel}
        .sheet(isPresented:$showTranscriptCorrection) {transcriptCorrectionPanel}
        .confirmationDialog("退出本次任务？未完成的任务不会自动判为能力失败。",isPresented:$showExit,titleVisibility:.visible) {
            Button("退出本次任务",role:.destructive) {audio.discard();run {try await model.transition("exit")}}
            Button("继续学习",role:.cancel) {}
        }
        .confirmationDialog("转回引导练习？本次独立检查将结束，之后换一组内容练习。",isPresented:$showReturn,titleVisibility:.visible) {
            Button("转回引导练习") {audio.discard();run {try await model.transition("return_guided")}}
            Button("继续独立应用",role:.cancel) {}
        }
        .interactiveDismissDisabled()
        .onChange(of:scenePhase) {_,value in
            if value != .active {cancelAudioInteraction()}
        }
        .onChange(of:current?.view.taskId) {_,_ in cancelAudioInteraction();hintCache=[:];selectedHint=nil;showHistory=false;followConversation=true}
        .onChange(of:hintContext) {_,_ in repairReady=false;hintCache=[:];selectedHint=nil;hintExplanationVisible=false;hintTranslationVisible=false}
        .onChange(of:phase) {_,_ in cancelAudioInteraction();retryingShadow=false;showHints=false;showHistory=false;highlightedLine=nil}
        .onChange(of:model.selectedMaterial) {_,_ in retryingShadow=false;learningShadow=false;audio.discard()}
        .task(id:learningPreparationKey) {
            guard learningPreparationKey != "inactive" else {return}
            await model.perform {try await model.learningAction("prepare")}
        }
        .task(id:isFeedback ? current?.view.taskId:nil) {
            summaryAdvice=nil;summaryAdviceFailed=false
            if isFeedback {await loadSummaryAdvice()}
        }
        .task(id:partner?.turnId) {
            guard (isGuided || isIndependent),let ref=partner?.audioRef else {return}
            do {
                while model.busy {try await Task.sleep(for:.milliseconds(50))}
                try Task.checkCancellation()
                guard !audio.recording,!feedbackOpen,scenePhase == .active else {return}
                play(ref,turnID:partner?.turnId)
            } catch is CancellationError {} catch {model.error=error.localizedDescription}
        }
        .onReceive(NotificationCenter.default.publisher(for:Notification.Name("PauseSayWithLearning"))) {_ in
            feedbackOpen=true;cancelAudioInteraction()
        }
        .onReceive(NotificationCenter.default.publisher(for:Notification.Name("ResumeSayWithLearning"))) {_ in feedbackOpen=false}
        .onDisappear {cancelAudioInteraction()}
        .onChange(of:audio.interruptionMessage) {_,message in
            if message != nil && !audio.recording && audio.lastRecording == nil {cancelHoldRecording()}
        }
    }
    private var stageIndex:Int {
        if isFeedback || phase=="evaluating" {return 3}
        if isIndependent {return 2}
        if isGuided || phase=="guided_feedback" {return 1}
        return 0
    }
    private var sessionHeader:some View {
        VStack(spacing:8) {
            HStack {
                Button {audio.discard();model.backToHome()} label: {Image(systemName:"chevron.left").font(.system(size:18)).frame(width:44,height:44)}
                    .accessibilityLabel("返回首页，保存进度").disabled(model.busy).accessibilityIdentifier("exitLesson")
                Spacer()
                Text(isReview ? (isFeedback ? "复习结果" : isGuided ? "引导补练":"复习") : ["学习","引导练习","独立应用","任务反馈"][stageIndex]).font(.headline).lineLimit(1).minimumScaleFactor(0.7).accessibilityIdentifier("phaseTitle")
                Spacer()
                Menu {
                    if isIndependent {Button("需要答案帮助，转回引导练习") {showReturn=true}}
                    if phase=="learning" && learningPractice?.stage != "recall" && current?.view.lexicalPractices?.contains(where:{!$0.completed}) != true {if learningPractice?.stage=="preview" {Button("跟读一下") {learningShadow=true}};Button("用法说明") {showUsage=true};Button("完整示范对话") {showDemo=true}}
                    if isGuided {Button("本课表达") {showCourseExpressions=true}}
                    if phase != "learning" || (learningPractice?.stage ?? "preview")=="preview" {Button("查看任务与条件") {showTaskInfo=true}}
                    Button("退出本次任务",role:.destructive) {showExit=true}
                } label:{Image(systemName:"ellipsis").font(.system(size:18)).frame(width:44,height:44)}
                    .accessibilityLabel("更多学习操作").disabled(model.busy)
            }
        }.padding(.horizontal,20).padding(.top,4).padding(.bottom,8)
        .tint(.accentColor).background(Color(uiColor:.systemBackground))
    }
    private var taskRegion:some View {regularTaskRegion}
    private var taskInfoPanel:some View {
        NavigationStack {
            ScrollView {
                VStack(alignment:.leading,spacing:20) {
                    LookupText(SpeakingCue.learnerTitle(current?.view.title ?? "本次任务")).font(.title3.weight(.semibold))
                    if let round=current?.view.guidedRound {Text("第 \(round) / \(current?.view.guidedRoundTotal ?? 3) 轮")}
                    LookupText(current?.view.instruction ?? "")
                    ForEach((current?.view.learnerFacts ?? [:]).keys.sorted(),id:\.self) {key in
                        LookupText(current?.view.learnerFacts[key]?.text ?? "")
                    }
                    if isIndependent {Text("需要答案帮助时，请转回引导练习。").foregroundStyle(.secondary)}
                    if current?.view.fixture==true {Text("测试内容 · 不计入能力").foregroundStyle(.secondary)}
                }.frame(maxWidth:.infinity,alignment:.leading).padding(20)
            }.navigationTitle("任务与条件").navigationBarTitleDisplayMode(.inline)
                .toolbar {ToolbarItem(placement:.cancellationAction) {Button("关闭") {showTaskInfo=false}}}
        }
    }
    private var ownTimes:[String] {
        if case .array(let values)=current?.view.learnerFacts["available_times"] {return values.map(\.text)}
        return []
    }
    private var regularTaskRegion:some View {
        VStack(alignment:.leading,spacing:12) {
            HStack(alignment:.firstTextBaseline) {
                LookupText(isFeedback ? feedbackTitle : SpeakingCue.learnerTitle(current?.view.title ?? "本次交流任务")).font(.title3.weight(.semibold)).fixedSize(horizontal:false,vertical:true).accessibilityIdentifier("taskTitle")
                Spacer(minLength:8)
                if isReview && !isFeedback {Text("1/1").font(.subheadline).foregroundStyle(.secondary)}
                else if let round=current?.view.guidedRound {Text("\(round)/\(current?.view.guidedRoundTotal ?? 3)").font(.subheadline).foregroundStyle(.secondary).accessibilityIdentifier("guidedRound").accessibilityLabel("第 \(round) 轮，共 \(current?.view.guidedRoundTotal ?? 3) 轮，\(current?.view.guidedRoundTitle ?? "")")}
            }
            if isFeedback {LookupText(result?.summary ?? "正在整理本次表现").font(.subheadline).foregroundStyle(.secondary)}
            else if phase=="learning" && (learningPractice?.stage ?? "preview")=="preview" {LookupText(current?.view.instruction ?? "").font(.subheadline).foregroundStyle(.secondary)}
            else if phase=="guided_feedback" {Text("引导练习已结束").font(.subheadline).foregroundStyle(.secondary)}
            else if !ownTimes.isEmpty {
                HStack(alignment:.center,spacing:16) {
                    Text("我有空").font(.subheadline).foregroundStyle(.secondary)
                    ScrollView(.horizontal,showsIndicators:false) {HStack(spacing:10) {ForEach(ownTimes,id:\.self) {time in Text(time).font(.body).foregroundStyle(Color.accentColor).padding(.horizontal,12).padding(.vertical,8).background(Color.accentColor.opacity(0.08),in:RoundedRectangle(cornerRadius:8))}}}
                }
            }
        }.frame(maxWidth:.infinity,alignment:.leading)
    }
    @ViewBuilder private var learningContent:some View {
        if let material=activeMaterial {
            let stage=learningPractice?.stage ?? "preview"
            if stage=="preview" {
                if let first=current?.view.demonstration?.first {
                    VStack(alignment:.leading,spacing:8) {
                        Text(current?.view.partnerName ?? "对方").font(.caption).foregroundStyle(.secondary)
                        LookupText(first.text).font(.body).fixedSize(horizontal:false,vertical:true)
                        HStack(spacing:4) {
                            if let ref=first.audioRef {playbackButton(ref,label:"重播这句话")}
                            translationButton("demo:0",known:first.meaningZh)
                        }
                        if shownTranslations.contains("demo:0") {Text(first.meaningZh ?? "").font(.subheadline).foregroundStyle(.secondary)}
                    }.frame(maxWidth:.infinity,alignment:.leading).padding(18)
                        .background(Color(uiColor:.secondarySystemGroupedBackground),in:RoundedRectangle(cornerRadius:16))
                }
                VStack(alignment:.leading,spacing:10) {
                    Text("重点表达").font(.subheadline).foregroundStyle(.secondary)
                    LookupText(material.expression).font(.title3).fixedSize(horizontal:false,vertical:true).accessibilityIdentifier("englishExpression")
                    Text(material.meaningZh ?? "").font(.subheadline).foregroundStyle(.secondary)
                    if let ref=material.audioRef {playbackButton(ref,label:"播放示范")}
                    Divider()
                    Text("关键用法").font(.headline)
                    Text(learningPractice?.usageZh ?? material.explanationZh).font(.subheadline)
                        .fixedSize(horizontal:false,vertical:true).accessibilityIdentifier("learningUsage")
                }.frame(maxWidth:.infinity,alignment:.leading).padding(18)
                    .background(Color(uiColor:.secondarySystemGroupedBackground),in:RoundedRectangle(cornerRadius:16))
            } else if stage != "complete",let practice=learningPractice {
                if stage=="recall",let previous=practice.previousFeedback,practice.feedback==nil {
                    VStack(alignment:.leading,spacing:8) {
                        Label("上一轮表达清楚",systemImage:"checkmark.circle.fill").font(.headline).foregroundStyle(Color.accentColor)
                        Text("已进入新场景，试着独立表达。").font(.subheadline).foregroundStyle(.secondary)
                            .accessibilityIdentifier("learningStageTransition")
                        DisclosureGroup("查看上一轮反馈") {
                            learningVoiceMessage(previous)
                            Text(previous.explanationZh).font(.subheadline).foregroundStyle(.secondary)
                            learningCorrectedExpression(previous)
                        }.accessibilityIdentifier("previousLearningFeedback")
                    }.padding(18).frame(maxWidth:.infinity,alignment:.leading)
                        .background(Color(uiColor:.secondarySystemGroupedBackground),in:RoundedRectangle(cornerRadius:16))
                }
                let cue=SpeakingCue(practice.promptZh)
                VStack(alignment:.leading,spacing:12) {
                    if !cue.context.isEmpty {
                        Text(cue.context).font(.subheadline).foregroundStyle(.secondary)
                            .fixedSize(horizontal:false,vertical:true).accessibilityIdentifier("learningContext")
                        Divider()
                    }
                    Text("轮到你").font(.headline)
                    Text(cue.intention).font(.body).fixedSize(horizontal:false,vertical:true).accessibilityIdentifier("learningIntention")
                }.frame(maxWidth:.infinity,alignment:.leading).padding(18)
                    .background(Color(uiColor:.secondarySystemGroupedBackground),in:RoundedRectangle(cornerRadius:16))
                if stage=="supported" {
                    VStack(alignment:.leading,spacing:10) {
                        Text("句型框架").font(.subheadline).foregroundStyle(.secondary)
                        LookupText(practice.pattern).font(.title3).accessibilityIdentifier("learningPattern")
                        Text(practice.usageZh).font(.subheadline).foregroundStyle(.secondary)
                        if let example=practice.example {
                            Divider()
                            Text("可以这样说").font(.subheadline).foregroundStyle(.secondary)
                            LookupText(example.expression).font(.body).accessibilityIdentifier("learningRecoveryExample")
                            Text(example.meaningZh).font(.subheadline).foregroundStyle(.secondary)
                            if let ref=example.audioRef {playbackButton(ref,label:"播放回答示范")}
                        } else {
                            Button("看一句示范") {run {try await model.learningAction("show_example")}}
                                .font(.subheadline).frame(minHeight:44).disabled(model.busy)
                                .accessibilityIdentifier("learningFullExample")
                        }
                    }.frame(maxWidth:.infinity,alignment:.leading).padding(18)
                        .background(Color(uiColor:.secondarySystemGroupedBackground),in:RoundedRectangle(cornerRadius:16))
                }
            }
            if model.outgoingMessage != nil {outgoingBubble}
            else if let feedback=learningPractice?.feedback {
                learningVoiceMessage(feedback)
                VStack(alignment:.leading,spacing:10) {
                    Label(stage=="preview" ? "跟读已收到":stage=="complete" ? "这次能自己说了":feedback.met ? "表达清楚":feedback.confidence=="low" ? "录音需要确认":"需要调整",systemImage:feedback.met ? "checkmark.circle.fill":"arrow.clockwise")
                        .font(.headline).foregroundStyle(feedback.met ? Color.accentColor:Color.primary)
                    Text(feedback.explanationZh).font(.subheadline).foregroundStyle(.secondary).accessibilityIdentifier("learningFailureReason")
                    if !feedback.met,!feedback.fixture {
                        Text("以上反馈依据文字；若与你说的不一致，请回听并更正识别文字。").font(.caption).foregroundStyle(.secondary)
                        Button("更正识别文字") {
                            correctionFeedback=feedback;correctedTranscript=feedback.transcript;showTranscriptCorrection=true
                        }.frame(minHeight:44).disabled(model.busy).accessibilityIdentifier("correctLearningTranscript")
                        Button("识别有误，重新识别") {run {try await model.recheckLearningRecognition(feedback.audioRef)}}
                            .frame(minHeight:44).disabled(model.busy).accessibilityIdentifier("recheckLearningRecognition")
                    }
                    if stage=="supported",feedback.met {
                        Text("已完成有示范的练习。接下来换个场景，试着独立表达。")
                            .font(.subheadline).foregroundStyle(.secondary).accessibilityIdentifier("learningStageTransition")
                    }
                    if stage=="supported" || feedback.met {learningCorrectedExpression(feedback)}
                }.frame(maxWidth:.infinity,alignment:.leading).padding(18)
                    .background(Color(uiColor:.secondarySystemGroupedBackground),in:RoundedRectangle(cornerRadius:16))
                    .accessibilityElement(children:.contain).accessibilityIdentifier("learningFeedback")
            }
        }
    }
    @ViewBuilder private func learningCorrectedExpression(_ feedback:LearningPracticeView.Feedback)->some View {
        if !feedback.betterExpression.isEmpty {
            Divider()
            Text("正确说法").font(.subheadline.weight(.semibold)).foregroundStyle(.secondary)
            LookupText(feedback.betterExpression).font(.body).accessibilityIdentifier("learningCorrectedExpression")
            if !feedback.meaningZh.isEmpty {Text(feedback.meaningZh).font(.subheadline).foregroundStyle(.secondary)}
        }
    }
    @ViewBuilder private var activeLearningFooter:some View {
        if let practice=learningPractice {
            if practice.stage=="complete" {
                mainButton(model.selectedMaterial+1<(current?.view.materials.count ?? 0) ? "学习下一表达":"接着对话",id:"nextPhase") {audio.discard();run {try await model.advanceMaterial()}}
            } else if practice.stage=="preview" && !learningShadow {
                mainButton("换内容说",id:"startSupported") {audio.discard();run {try await model.learningAction("start")}}
                Button("已经会了，直接试试") {audio.discard();run {try await model.learningAction("recall")}}
                    .font(.subheadline).frame(minHeight:44).disabled(model.busy).accessibilityIdentifier("tryRecall")
            } else if practice.stage=="supported" && practice.feedback?.met==true {
                mainButton("换个场景，独立表达",id:"startRecall") {audio.discard();run {try await model.learningAction("recall")}}
            } else {
                HStack(spacing:12) {
                    PracticeHintButton(identifier:practice.stage=="recall" ? "revealLearningExample":"learningHint",
                        disabled:model.busy || audio.recording || hold.active) {
                        audio.discard()
                        if practice.stage=="recall" {run {try await model.learningAction("show_pattern")}}
                        else if practice.stage=="preview" {showDemo=true}
                        else {showUsage=true}
                    }
                    holdRecordingButton
                }
            }

        } else {
            if model.busy {ProgressView("准备表达练习")}
            else {Button("重新准备表达练习") {run {try await model.learningAction("prepare")}}.frame(minHeight:44)}
        }
        if let recording=audio.lastRecording,!audio.recording,audio.interruptionMessage != nil,!model.hasPendingLearning {Button("发送已保存的录音") {run {try await model.learningAttempt(recording,shadow:learningShadow)}}.frame(minHeight:44)}

    }
    private var usagePanel:some View {
        NavigationStack {ScrollView {LookupText(learningPractice?.usageZh ?? activeMaterial?.explanationZh ?? "").frame(maxWidth:.infinity,alignment:.leading).padding(20)}.navigationTitle("用法说明").navigationBarTitleDisplayMode(.inline).toolbar {ToolbarItem(placement:.cancellationAction) {Button("关闭") {showUsage=false}}}}.presentationDetents([.medium,.large])
    }
    private var demoPanel:some View {
        NavigationStack {ScrollView {VStack(alignment:.leading,spacing:20) {
            Button {playDemo()} label:{playbackIcon("demo",playing:demoTask != nil && audio.playing)}.accessibilityLabel("播放完整对话").disabled(model.busy || hold.active)
            ForEach(Array((current?.view.demonstration ?? []).enumerated()),id:\.offset) {index,line in
                VStack(alignment:.leading,spacing:10) {
                    Text(line.speaker=="learner" ? "你":current?.view.partnerName ?? "对方").font(.caption).foregroundStyle(.secondary)
                    LookupText(line.text).foregroundStyle(highlightedLine==index ? Color.accentColor:Color.primary)
                    HStack(spacing:4) {if let ref=line.audioRef {playbackButton(ref,label:"重播这句话")};translationButton("demo-line:\(index)",known:line.meaningZh,source:index==0 ? "demo:0":"material:\(index-1)")}
                    if shownTranslations.contains("demo-line:\(index)") {Text(line.meaningZh ?? model.translations[index==0 ? "demo:0":"material:\(index-1)"] ?? "正在加载翻译").font(.subheadline).foregroundStyle(.secondary)}
                }
            }
            Text("声音由 AI 生成").font(.caption).foregroundStyle(.secondary)
        }.padding(20)}.navigationTitle("完整示范对话").navigationBarTitleDisplayMode(.inline).toolbar {ToolbarItem(placement:.cancellationAction) {Button("关闭") {demoTask?.cancel();audio.stopPlayback();showDemo=false}}}}
    }
    private var historyPanel:some View {
        NavigationStack {ScrollView {VStack(alignment:.leading,spacing:18) {conversationContent}.padding(20)}.background(Color(uiColor:.systemGroupedBackground)).navigationTitle("本次记录").navigationBarTitleDisplayMode(.inline).toolbar {ToolbarItem(placement:.cancellationAction) {Button("关闭") {showHistory=false}}}}
    }
    @ViewBuilder private var conversationContent:some View {
        ForEach(current?.turns ?? []) {turn in
            let own=turn.speaker=="learner"
            HStack(alignment:.top) {
                if own {Spacer(minLength:32)}
                VStack(alignment:own ? .trailing:.leading,spacing:10) {
                    Text(own ? "我" : current?.view.partnerName ?? "对方").font(.caption).foregroundStyle(.secondary)
                    VStack(alignment:.leading,spacing:0) {
                    if own || actions.contains("show_text") {LookupText(turn.content).font(.body).foregroundStyle(own ? Color.white:Color.primary).fixedSize(horizontal:false,vertical:true)}
                    else {Label("对方语音",systemImage:"waveform").font(.subheadline).foregroundStyle(.secondary)}
                    HStack(spacing:4) {
                    if let ref=turn.audioRef,own || actions.contains("request_repeat") || !playedTurns.contains(turn.turnId) || (audio.paused && audio.playingID==ref) {
                        playbackButton(ref,label:own ? "回听自己":"重播这句话",turnID:own ? nil:turn.turnId)

                    }
                        if !own && actions.contains("request_translation") {translationButton(turn.turnId)}
                    }
                    if shownTranslations.contains(turn.turnId),let text=model.translations[turn.turnId] {LookupText(text).font(.subheadline).foregroundStyle(.secondary)}
                    }.tint(own ? Color.white:Color.accentColor).padding(.horizontal,14).padding(.top,12).padding(.bottom,2).background(own ? Color.accentColor:Color(uiColor:.secondarySystemGroupedBackground),in:RoundedRectangle(cornerRadius:16))
                    if own && (isGuided || isFeedback || phase=="guided_feedback") {
                        Button {openReplyAdvice(turn.turnId)} label: {Label("表达建议",systemImage:"text.bubble")}
                            .font(.subheadline).frame(minHeight:44).accessibilityIdentifier("replyAdvice-"+turn.turnId)
                    }
                }
                if !own {Spacer(minLength:32)}
            }.id(turn.turnId)
        }
        if let draft=model.outgoingMessage,!((current?.turns ?? []).contains(where:{$0.turnId==draft.turnId})) {outgoingBubble}
    }
    private func openReplyAdvice(_ turnID:String) {
        cancelAudioInteraction();advice=nil;adviceError=nil;adviceTurnID=turnID;showAdvice=true;adviceLoading=true
        Task { @MainActor in
            do {
                let value=try await model.replyAdvice(turnID)
                guard adviceTurnID==turnID else {return}
                advice=value
            } catch {adviceError=error.localizedDescription}
            adviceLoading=false
        }
    }
    private var replyAdvicePanel:some View {
        NavigationStack {
            ScrollView {
                VStack(alignment:.leading,spacing:16) {
                    if adviceLoading {ProgressView().frame(maxWidth:.infinity).padding(24)}
                    if let adviceError {
                        Text(adviceError).font(.subheadline).foregroundStyle(.secondary)
                        Button("重新获取") {if let adviceTurnID {openReplyAdvice(adviceTurnID)}}.frame(minHeight:44)
                    }
                    if let advice {
                        Text(advice.title).font(.headline)
                        Text(advice.explanationZh).font(.subheadline).foregroundStyle(.secondary)
                        if !advice.expression.isEmpty {
                            VStack(alignment:.leading,spacing:10) {
                                HStack {
                                    Text("可以这样说").font(.subheadline).foregroundStyle(.secondary)
                                    Spacer()
                                    if let ref=advice.audioRef {playbackButton(ref,label:"播放建议说法")}
                                }
                                LookupText(advice.expression).font(.title3).fixedSize(horizontal:false,vertical:true)
                                Text(advice.meaningZh).font(.subheadline).foregroundStyle(.secondary)
                            }.padding(18).frame(maxWidth:.infinity,alignment:.leading)
                                .background(Color(uiColor:.secondarySystemGroupedBackground),in:RoundedRectangle(cornerRadius:16))
                            if !advice.phrases.isEmpty {
                                VStack(alignment:.leading,spacing:12) {
                                    Text("关键表达").font(.headline)
                                    ForEach(advice.phrases.indices,id:\.self) {index in
                                        VStack(alignment:.leading,spacing:4) {
                                            LookupText(advice.phrases[index].expression).font(.body)
                                            Text(advice.phrases[index].meaningZh).font(.subheadline).foregroundStyle(.secondary)
                                        }.frame(maxWidth:.infinity,alignment:.leading)
                                        if index<advice.phrases.count-1 {Divider()}
                                    }
                                }.padding(18).background(Color(uiColor:.secondarySystemGroupedBackground),in:RoundedRectangle(cornerRadius:16))
                            }
                            Button(isGuided ? "再说一次":"进入补练") {
                                showAdvice=false
                                if isGuided {repairReady=true}
                                else {run {try await model.transition("retry_guided")}}
                            }.font(.body.weight(.semibold)).frame(maxWidth:.infinity,minHeight:50)
                                .buttonStyle(.borderedProminent).accessibilityIdentifier("retryReplyAdvice")
                        }
                    }
                }.padding(20)
            }.background(Color(uiColor:.systemGroupedBackground))
                .navigationTitle("表达建议").navigationBarTitleDisplayMode(.inline)
                .toolbar {ToolbarItem(placement:.confirmationAction) {Button("继续对话") {showAdvice=false}}}
        }.presentationDetents([.large]).presentationDragIndicator(.visible)
    }
    private func learningVoiceMessage(_ feedback:LearningPracticeView.Feedback)->some View {
        HStack {
            Spacer(minLength:32)
            VStack(alignment:.trailing,spacing:6) {
                VStack(alignment:.leading,spacing:6) {
                    Label("语音消息",systemImage:"waveform")
                    if !feedback.fixture,!feedback.transcript.isEmpty {LookupText(feedback.transcript).font(.body)}
                    if feedback.transcriptSource=="learner_confirmed" {Text("文字已由你更正").font(.caption)}
                    playbackButton(feedback.audioRef,label:"回听自己的表达")
                }.foregroundStyle(.white).tint(.white).padding(14)
                    .background(Color.accentColor,in:RoundedRectangle(cornerRadius:16))
            }
        }.accessibilityIdentifier("learningVoiceMessage")
    }
    private var transcriptCorrectionPanel:some View {
        NavigationStack {
            Form {
                Section {
                    Text("请按录音中实际说出的内容更正文字。原录音和原始识别结果会保留。").font(.subheadline).foregroundStyle(.secondary)
                    if let feedback=correctionFeedback {playbackButton(feedback.audioRef,label:"回听原录音")}
                    TextField("实际说出的内容",text:$correctedTranscript,axis:.vertical)
                        .lineLimit(3...8).autocorrectionDisabled().accessibilityIdentifier("correctedTranscriptField")
                }
            }.navigationTitle("更正识别文字").navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    ToolbarItem(placement:.cancellationAction) {Button("取消") {showTranscriptCorrection=false}}
                    ToolbarItem(placement:.confirmationAction) {
                        Button("确认并继续") {
                            guard let feedback=correctionFeedback else {return}
                            let text=correctedTranscript.trimmingCharacters(in:.whitespacesAndNewlines)
                            showTranscriptCorrection=false
                            run {try await model.confirmLearningTranscript(text,feedback:feedback)}
                        }.disabled(correctedTranscript.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty || correctedTranscript.count>1000)
                            .accessibilityIdentifier("confirmCorrectedTranscript")
                    }
                }
        }
    }
    private var outgoingBubble:some View {
        HStack {
            Spacer(minLength:32)
            VStack(alignment:.trailing,spacing:6) {
                VStack(alignment:.leading,spacing:8) {
                    Label("语音消息",systemImage:"waveform")
                    if let text=model.outgoingMessage?.text,!text.isEmpty {LookupText(text).font(.body)}
                }.foregroundStyle(.white).padding(14)
                    .background(Color.accentColor,in:RoundedRectangle(cornerRadius:16)).accessibilityIdentifier("outgoingMessage")
                HStack(spacing:6) {
                    if model.outgoingMessage?.stage=="failed" {Image(systemName:"exclamationmark.circle")} else {ProgressView().controlSize(.mini)}
                    Text(model.outgoingMessage?.statusText ?? "正在发送").font(.caption)
                }.foregroundStyle(.secondary).accessibilityIdentifier("messageProcessingStatus")
                if model.outgoingMessage?.stage=="failed" {
                    Button("重试发送") {run {if model.hasPendingLearning {try await model.retryLearningAttempt()} else {try await model.retryInput()}}}
                        .font(.subheadline).frame(minHeight:44).disabled(model.busy).accessibilityIdentifier("retryOutgoingMessage")
                    if model.hasPendingLearning {Button("放弃本次录音") {model.discardLearningAttempt();audio.discard()}.frame(minHeight:44)}
                    if let error=model.error {Text(error).font(.caption).foregroundStyle(.red)}
                }
            }
        }.id(model.outgoingMessage?.id ?? "outgoing")
    }
    private var guidedSummary:some View {
        VStack(alignment:.leading,spacing:24) {
            Text("准备好独立试试了").font(.headline)
            Text((current?.view.supportUsed ?? []).isEmpty ? "本次没有请求答案提示。" : (current?.view.supportUsed ?? []).joined(separator:"、"))
            Text("接下来换一组条件，独立完成对话。").foregroundStyle(.secondary)
            Button("再练一次") {run {try await model.transition("retry_guided")}}.frame(minHeight:44).buttonStyle(.bordered)
        }
    }
    private var result:Assessment? {current?.view.assessment ?? model.assessment}
    private var feedbackTitle:String {
        guard let result else {return "正在整理本次表现"}
        if result.validation["status"]?.text != "accepted" {return "本次评价未完成"}
        return ["completed":isReview ? "复习完成":"任务完成","partial":"已完成部分要求","failed":"还需要练习"][result.targetResults.first?["result"]?.text ?? ""] ?? "本次表现还无法确认"
    }
    private var evidence:[[String:JSONValue]] {
        guard let value=result?.targetResults.first?["checks"],case .array(let checks)=value else {return []}
        return checks.compactMap {if case .object(let d)=$0 {return d};return nil}
    }
    private var improvement:String {
        if result?.validation["status"]?.text != "accepted" {return "可以回听本次记录，或换一组内容再试。"}
        return evidence.first(where:{$0["result"]?.text != "met"})?["criterion"]?.text ?? "换一个场景，再检查能否独立完成。"
    }
    private var taskCompleted:Bool {result?.validation["status"]?.text=="accepted" && result?.targetResults.first?["result"]?.text=="completed"}
    private var usedAnswerHelp:Bool {
        (current?.view.supportUsed ?? []).contains { ["意图提示","句型提示","完整示例","所学表达","模型提示","查词释义","回答示范"].contains($0) }
    }
    private var resultLabel:String {
        guard result?.validation["status"]?.text=="accepted" else {return "证据不足"}
        return ["completed":usedAnswerHelp ? "借助帮助完成":isReview ? "本次复习任务完成":"本次独立完成","partial":"已完成部分要求","failed":"还需要练习"][result?.targetResults.first?["result"]?.text ?? ""] ?? "本次表现还无法确认"
    }
    private var feedbackContent:some View {
        VStack(alignment:.leading,spacing:16) {
            if result?.validation["status"]?.text=="accepted" {
            VStack(alignment:.leading,spacing:12) {
                Label(result?.validation["status"]?.text=="accepted" ? (taskCompleted ? "完成依据":"本次表现"):"本次评价",systemImage:taskCompleted ? "checkmark.circle.fill":"circle").font(.headline)
                Text(resultLabel).font(.subheadline).foregroundStyle(result?.validation["status"]?.text=="accepted" ? Color.accentColor:Color.secondary)
                if result?.validation["status"]?.text=="accepted" {
                    ForEach((current?.turns ?? []).filter {turn in
                        turn.speaker=="learner" && evidence.contains {check in
                            guard case .array(let refs)=check["evidence_refs"] else {return false}
                            return refs.contains(where:{$0.text==turn.turnId})
                        }
                    }) {turn in LookupText(turn.content).font(.body)}
                } else {LookupText(result?.failureExplanation ?? "正在整理本次表现").font(.body)}
                if let check=evidence.first {LookupText(check["criterion"]?.text ?? "").font(.subheadline).foregroundStyle(.secondary)}
            }.frame(maxWidth:.infinity,alignment:.leading).padding(18).background(Color(uiColor:.secondarySystemGroupedBackground),in:RoundedRectangle(cornerRadius:16))
            }
            if summaryAdviceLoading {ProgressView().frame(maxWidth:.infinity)}
            else if let advice=summaryAdvice,advice.status=="correction" || advice.status=="alternative" {
                VStack(alignment:.leading,spacing:10) {
                    Text(advice.status=="correction" ? "重点改进":"更自然的说法").font(.headline)
                    Text(advice.explanationZh).font(.subheadline).foregroundStyle(.secondary)
                    HStack(alignment:.top) {
                        LookupText(advice.expression).font(.title3).fixedSize(horizontal:false,vertical:true)
                        Spacer(minLength:8)
                        if let ref=advice.audioRef {playbackButton(ref,label:"播放建议说法")}
                    }
                    Text(advice.meaningZh).font(.subheadline).foregroundStyle(.secondary)
                    ForEach(advice.phrases.indices,id:\.self) {i in
                        HStack(alignment:.firstTextBaseline) {LookupText(advice.phrases[i].expression).font(.body);Text(advice.phrases[i].meaningZh).font(.subheadline).foregroundStyle(.secondary)}
                    }
                }.frame(maxWidth:.infinity,alignment:.leading).padding(18)
                    .background(Color(uiColor:.secondarySystemGroupedBackground),in:RoundedRectangle(cornerRadius:16))
                    .accessibilityIdentifier("priorityFeedback")
            } else if summaryAdviceFailed {Button("重新获取表达建议") {Task {await loadSummaryAdvice()}}.frame(minHeight:44)}
            Text("下一步").font(.subheadline).foregroundStyle(.secondary)
            LookupText(improvement).font(.subheadline).foregroundStyle(.secondary)
            if !taskCompleted {Button("练习这一点") {run {try await model.transition("retry_guided")}}.frame(minHeight:44).buttonStyle(.borderedProminent).disabled(model.busy).accessibilityIdentifier("targetedPractice")}
            Button("换内容再试") {run {try await model.transition("retry_independent")}}.frame(minHeight:44).disabled(model.busy).accessibilityIdentifier("retryIndependent")
        }
    }
    private func loadSummaryAdvice() async {
        guard let turnID=current?.view.feedbackTurnId else {return}
        let taskID=current?.view.taskId
        summaryAdviceLoading=true;summaryAdviceFailed=false
        defer {summaryAdviceLoading=false}
        do {
            let value=try await model.replyAdvice(turnID)
            guard isFeedback,current?.view.taskId==taskID else {return}
            summaryAdvice=value
        } catch {if isFeedback,current?.view.taskId==taskID {summaryAdviceFailed=true}}
    }
    private var shadowReady:Bool {
        guard phase=="learning",!retryingShadow,let feedback=model.shadowFeedback ?? current?.view.shadowFeedback else {return false}
        return feedback.canContinue && feedback.materialIndexMatches(model.selectedMaterial)
    }
    private var footer:some View {
        VStack(spacing:8) {
            if let error=model.error,model.outgoingMessage==nil {Text(error).font(.footnote).foregroundStyle(.red).lineLimit(2).accessibilityIdentifier("errorMessage");if error.contains("麦克风") {Button("打开系统设置") {if let url=URL(string:UIApplication.openSettingsURLString) {UIApplication.shared.open(url)}}}}
            if let message=audio.interruptionMessage {Text(message).font(.footnote).foregroundStyle(.secondary)}
            if phase=="learning" {activeLearningFooter}
            else if isFeedback {
                mainButton(isReview ? "完成复习":"完成学习",id:"finishLearning") {audio.discard();model.leave()}
                Button("查看本次记录") {showHistory=true}.font(.subheadline).frame(minHeight:44)
            } else if phase=="evaluating" {
                mainButton("继续流程",id:"resumeConversationEnd") {run {
                    if actions.contains("next") {try await model.next()} else {try await model.finish()}
                }}
            } else if phase=="guided_feedback" {
                if model.busy {ProgressView("准备独立任务") }
                mainButton(isReview ? "换内容再试":"开始独立应用",id:"independentTask") {
                    run {try await model.next()}
                }
            } else {
                let hasReply=current?.turns.contains(where:{$0.speaker=="learner"})==true
                if (phase=="learning" && audio.lastRecording != nil) || ((isGuided || isIndependent) && hasReply) {
                    HStack {
                        Spacer(minLength:0)
                        if phase=="learning" {Button("重新跟读") {audio.lastRecording=nil;model.shadowFeedback=nil;retryingShadow=true}.frame(minHeight:44)}
                        else if isGuided {Button((current?.view.guidedRound ?? 1)<(current?.view.guidedRoundTotal ?? 3) ? "继续下一轮":"结束引导练习") {run {try await model.next()}}.frame(minHeight:44).accessibilityIdentifier("nextGuidedRound")}
                        else {Button("结束任务并查看结果") {run {try await model.finish()}}.frame(minHeight:44).accessibilityIdentifier("finishTask")}
                    }.font(.subheadline).disabled(model.busy || audio.recording || hold.active)
                }
                if shadowReady {
                    mainButton(model.selectedMaterial+1<(current?.view.materials.count ?? 0) ? "继续学习下一表达":"试着换个内容说",id:"nextPhase") {audio.discard();run {try await model.advanceMaterial()}}
                } else {
                    HStack(spacing:12) {
                        PracticeHintButton(identifier:isGuided ? "hintButton":"independentHint",
                            disabled:isIndependent || model.busy || audio.recording || hold.active) {showHints=true}
                            .accessibilityHint(isIndependent ? "独立应用需要自己表达，可从更多操作返回引导练习。":"查看表达提示")

                        holdRecordingButton
                    }
                }
                if model.hasPendingShadow {Button("重试提交跟读") {run {try await model.retryShadow();retryingShadow=false}}.frame(minHeight:44);Button("放弃本次录音") {model.discardShadowRequest();audio.lastRecording=nil}.frame(minHeight:44)}
                if model.hasPendingInput && model.outgoingMessage==nil {Button("重试发送") {run {try await model.retryInput()}}.frame(minHeight:44)}
                if let recording=audio.lastRecording,!audio.recording,audio.interruptionMessage != nil {Button("发送已保存的录音") {run {if phase=="learning" {try await model.shadow(recording)} else {try await model.send(kind:"speech",audio:recording)}}}.frame(minHeight:44)}
            }
        }.padding(.horizontal,20).padding(.top,16).padding(.bottom,12).frame(maxWidth:.infinity).background(Color(uiColor:.systemBackground)).overlay(alignment:.top) {Divider()}
    }
    private func loadHint(_ level:String) {
        selectedHint=level;hintExplanationVisible=false;hintTranslationVisible=false
        guard hintCache[level]==nil else {return}
        let context=hintContext
        run {
            try await model.send(kind:"request_hint",hintLevel:level)
            guard hintContext==context,let response=model.hintResponse else {return}
            hintCache[level]=response
        }
    }
    private var hintContext:String {(current?.view.taskId ?? "")+":"+(current?.turns.last?.turnId ?? "")}
    private var hintPanel:some View {
        NavigationStack {
            ScrollView {
                VStack(alignment:.leading,spacing:16) {
                    let level=selectedHint ?? "pattern"
                    let response=hintCache[level]
                    VStack(alignment:.leading,spacing:12) {
                        Text(level=="example" ? "一句示范":"一点提示").font(.headline)
                        if let response {
                            if let direction=response.hintContent?.directionZh,!direction.isEmpty,direction != current?.view.instruction,direction != current?.view.title {
                                Text(direction).font(.subheadline).foregroundStyle(.secondary)
                            }
                            LookupText(response.hintContent?.expression ?? response.text).font(.title3)
                                .fixedSize(horizontal:false,vertical:true).accessibilityIdentifier("hintExpression")
                            if level=="pattern" {Text("换成你自己的内容，再试着说。 ").font(.caption).foregroundStyle(.secondary)}
                            HStack(spacing:4) {
                                if let ref=response.audioRef {playbackButton(ref,label:"播放这句示范")}
                                if response.hintContent?.meaningZh != nil {
                                    Button {hintTranslationVisible.toggle()} label:{Image(systemName:"translate").frame(width:44,height:44)}
                                        .accessibilityLabel(hintTranslationVisible ? "收起翻译":"查看翻译").accessibilityIdentifier("hintTranslation")
                                }
                            }
                            if hintTranslationVisible,let meaning=response.hintContent?.meaningZh {Text(meaning).font(.subheadline).foregroundStyle(.secondary)}
                            if let explanation=response.hintContent?.explanationZh,!explanation.isEmpty {
                                Button(hintExplanationVisible ? "收起解释":"解释这个说法") {hintExplanationVisible.toggle()}.font(.subheadline).frame(minHeight:44)
                                if hintExplanationVisible {Text(explanation).font(.subheadline).foregroundStyle(.secondary)}
                            }
                        } else if model.busy {ProgressView("正在准备本轮提示")}
                        else {
                            Text(model.error ?? "暂时没有获取到提示").font(.subheadline).foregroundStyle(.secondary)
                            Button("重新获取") {loadHint(level)}.frame(minHeight:44)
                        }
                    }.frame(maxWidth:.infinity,alignment:.leading).padding(18)
                        .background(Color(uiColor:.secondarySystemGroupedBackground),in:RoundedRectangle(cornerRadius:16))
                    if level=="pattern" {
                        Button("看一句示范") {loadHint("example")}.frame(minHeight:44).disabled(model.busy).accessibilityIdentifier("hint-example")
                    } else {
                        Button("回到一点提示") {loadHint("pattern")}.frame(minHeight:44).disabled(model.busy).accessibilityIdentifier("hint-pattern")
                    }
                    Button("回到对话，试着说") {audio.stopPlayback();showHints=false}.buttonStyle(.borderedProminent).frame(minHeight:44)
                    Text("有帮助完成后，后续会再练习独立表达。").font(.caption).foregroundStyle(.secondary)
                }.padding(20)
            }.background(Color(uiColor:.systemGroupedBackground))
                .navigationTitle("本轮提示").navigationBarTitleDisplayMode(.inline)
                .toolbar {ToolbarItem(placement:.cancellationAction) {Button("关闭") {audio.stopPlayback();showHints=false}}}
                .task {if hintCache[selectedHint ?? "pattern"]==nil {loadHint(selectedHint ?? "pattern")}}
        }.presentationDetents([.medium,.large]).presentationDragIndicator(.visible)
    }
    private var courseExpressionsPanel:some View {
        NavigationStack {ScrollView {
            VStack(alignment:.leading,spacing:16) {
                ForEach(Array((current?.view.materials ?? []).enumerated()),id:\.offset) {index,material in
                    VStack(alignment:.leading,spacing:8) {
                        LookupText(material.expression).font(.body)
                        if let ref=material.audioRef {playbackButton(ref,label:"播放本课表达")}
                        if let meaning=material.meaningZh {Text(meaning).font(.subheadline).foregroundStyle(.secondary)}
                    }.frame(maxWidth:.infinity,alignment:.leading).padding(16)
                        .background(Color(uiColor:.secondarySystemGroupedBackground),in:RoundedRectangle(cornerRadius:12))
                }
            }.padding(20)
        }.background(Color(uiColor:.systemGroupedBackground)).navigationTitle("本课表达").navigationBarTitleDisplayMode(.inline)
            .toolbar {ToolbarItem(placement:.cancellationAction) {Button("关闭") {audio.stopPlayback();showCourseExpressions=false}}}
        }
    }
    private func mainButton(_ title:String,id:String,action:@escaping()->Void)->some View {
        Button(action:action) {Text(title).font(.headline).foregroundStyle(Color.white).frame(maxWidth:.infinity,minHeight:50)}
            .buttonStyle(.plain).background(Color.accentColor,in:RoundedRectangle(cornerRadius:12)).disabled(model.busy || audio.recording).accessibilityIdentifier(id)
    }
    private func run(_ operation:@escaping () async throws -> Void) {Task {await model.perform(operation)}}
    private func play(_ ref:String,turnID:String?=nil) {
        guard !audio.recording,!hold.active,!model.busy,loadingAudioID != ref else {return}
        stopAudioLoading();demoTask?.cancel();demoTask=nil
        audio.stopPlayback()
        let token=UUID();playbackToken=token;loadingAudioID=ref
        playbackTask=Task {
            defer {if playbackToken==token {loadingAudioID=nil;playbackTask=nil}}
            do {
                if let turnID,playedTurns.contains(turnID) {try await model.recordRepeat(sourceTurnID:turnID)}
                let data=try await model.sound(ref)
                try Task.checkCancellation()
                guard playbackToken==token,scenePhase == .active,!feedbackOpen,!hold.active else {return}
                try audio.play(data,id:ref)
                if let turnID {playedTurns.insert(turnID)}
            } catch is CancellationError {} catch {
                if !Task.isCancelled && playbackToken==token {model.error=error.localizedDescription}
            }
        }
    }
    private func stopAudioLoading() {
        playbackTask?.cancel();playbackTask=nil;playbackToken=UUID();loadingAudioID=nil
    }
    private func playbackIcon(_ ref:String,playing:Bool)->some View {
        ZStack {
            if loadingAudioID==ref {ProgressView().controlSize(.small).accessibilityLabel("正在加载声音")}
            else {Image(systemName:playing ? "pause.fill":"speaker.wave.2.fill")}
        }.frame(width:44,height:44)
    }
    private func playbackButton(_ ref:String,label:String,turnID:String?=nil)->some View {
        Button {
            if loadingAudioID != nil {return}
            if audio.playingID==ref && audio.playing {audio.pausePlayback()}
            else if audio.playingID==ref && audio.paused {do {try audio.resumePlayback()} catch {model.error=error.localizedDescription}}
            else {play(ref,turnID:turnID)}
        } label:{playbackIcon(ref,playing:audio.playingID==ref && audio.playing)}
            .accessibilityLabel(loadingAudioID==ref ? "正在加载声音":audio.playingID==ref && audio.playing ? "暂停播放":label)
            .accessibilityIdentifier("audio-"+ref).disabled(model.busy || audio.recording || hold.active)
    }
    private func tryPlay(_ data:Data) {do {try audio.play(data)} catch {model.error=error.localizedDescription}}
    private func translationButton(_ key:String,known:String?=nil,source:String?=nil)->some View {
        Button {
            if shownTranslations.contains(key) {shownTranslations.remove(key)}
            else {shownTranslations.insert(key);if known?.isEmpty != false && model.translations[source ?? key]==nil {translate(source ?? key)}}
        } label:{Image(systemName:"translate").frame(width:44,height:44)}
            .accessibilityLabel(shownTranslations.contains(key) ? "收起翻译":"查看翻译").disabled(model.busy || audio.recording)
    }
    private func translate(_ key:String) {run {try await model.send(kind:"request_translation",sourceTurnID:key)}}
    private var holdRecordingButton:some View {
        HoldToSpeakButton(hold:$hold,idleTitle:"按住说话",
            processing:model.busy && model.outgoingMessage==nil,disabled:model.busy || model.hasPendingInput || model.hasPendingShadow || model.hasPendingLearning,
            identifier:"recordButton",recording:audio.recording,level:audio.level,duration:audio.duration,canStart:{loadingAudioID==nil},
            onBegin:beginHoldRecording,onFinish:finishHoldRecording,onCancel:cancelHoldRecording)
    }
    private func beginHoldRecording() {
        demoTask?.cancel();demoTask=nil;audio.stopPlayback();model.error=nil
        audio.lastRecording=nil;audio.duration=0
        recordingStartTask?.cancel()
        recordingStartTask=Task {
            do {try await audio.start()}
            catch is CancellationError {} catch {
                if !Task.isCancelled {hold.reset();model.error=error.localizedDescription}
            }
        }
    }
    private func finishHoldRecording(verticalTranslation:CGFloat) {
        guard let release=hold.finish(verticalTranslation:verticalTranslation) else {return}
        recordingStartTask?.cancel();recordingStartTask=nil
        guard release == .send else {audio.discard();return}
        guard audio.recording || audio.lastRecording != nil else {return}
        do {
            let data=try audio.recording ? audio.stop():audio.lastRecording ?? Data()
            guard audio.duration>=0.4,!data.isEmpty else {audio.discard();model.error="录音太短，请按住说完再松开。";return}
            run {if phase=="learning" {try await model.learningAttempt(data,shadow:learningShadow);retryingShadow=false} else {try await model.send(kind:"speech",audio:data)}}
        } catch {model.error=error.localizedDescription}
    }
    private func cancelHoldRecording() {
        hold.reset();recordingStartTask?.cancel();recordingStartTask=nil;audio.discard()
    }
    private func cancelAudioInteraction() {
        demoTask?.cancel();demoTask=nil;stopAudioLoading();cancelHoldRecording()
    }
    private func playDemo() {
        if demoTask != nil {demoTask?.cancel();demoTask=nil;loadingAudioID=nil;audio.stopPlayback();highlightedLine=nil;return}
        stopAudioLoading()
        let token=UUID();playbackToken=token
        demoTask=Task {
            do {
                for (index,line) in (current?.view.demonstration ?? []).enumerated() {
                    try Task.checkCancellation()
                    guard let ref=line.audioRef else {continue}
                    loadingAudioID="demo"
                    let data=try await model.sound(ref)
                    try Task.checkCancellation()
                    guard playbackToken==token else {return}
                    loadingAudioID=nil;highlightedLine=index
                    try await audio.playAndWait(data,id:"demo-\(index)")
                }
            } catch is CancellationError {} catch {model.error=error.localizedDescription}
            if playbackToken==token {highlightedLine=nil;demoTask=nil;loadingAudioID=nil}
        }
    }
}

private struct ConversationBottomKey:PreferenceKey {
    static let defaultValue:CGFloat=0
    static func reduce(value:inout CGFloat,nextValue:()->CGFloat) {value=nextValue()}
}

/// Shared left-hand help control beside every voice input.
struct PracticeHintButton:View {
    let identifier:String
    let disabled:Bool
    let action:()->Void
    var body:some View {
        Button("提示",action:action)
            .font(.subheadline.weight(.medium)).frame(width:64,height:50)
            .buttonStyle(.plain).foregroundStyle(disabled ? Color.secondary:Color.accentColor)
            .background(Color.accentColor.opacity(disabled ? 0.04:0.08),in:RoundedRectangle(cornerRadius:12))
            .disabled(disabled).accessibilityIdentifier(identifier)
    }
}

/// Same press/release/cancel behavior for course and vocabulary practice.
struct HoldToSpeakButton:View {
    @Binding var hold:HoldRecordingGesture
    let idleTitle:String
    let processing:Bool
    let disabled:Bool
    let identifier:String
    var recording=false
    var level:Double=0
    var duration:TimeInterval=0
    let canStart:()->Bool
    let onBegin:()->Void
    let onFinish:(CGFloat)->Void
    let onCancel:()->Void
    @GestureState private var touching=false
    private func barHeight(_ index:Int)->CGFloat {
        guard recording,!hold.cancelling else {return 8}
        return CGFloat(8+level*32*(index%2==0 ? 1:0.65))
    }
    private var recordingFeedback:some View {
                    VStack(spacing:12) {
                        HStack(spacing:4) {
                            ForEach(0..<9,id:\.self) {i in
                                Capsule().fill(.white).frame(width:5,height:barHeight(i))
                            }
                        }.frame(height:40).accessibilityHidden(true)
                        Text(hold.cancelling ? "松开取消录音":recording ? "正在录音 · \(Int(duration)) 秒":"正在开启麦克风")
                            .font(.headline).accessibilityIdentifier("recordingFeedback")
                        Text(hold.cancelling ? "移回按钮继续录音":"松开发送，上滑取消").font(.footnote)
                    }.foregroundStyle(.white).padding(20).frame(width:240)
                        .background(hold.cancelling ? Color.red:Color.black.opacity(0.85),in:RoundedRectangle(cornerRadius:20))

    }
    var body:some View {
        HStack(spacing:8) {
            Image(systemName:hold.cancelling ? "xmark":"mic.fill")
            Text(processing ? "正在处理":hold.active ? (hold.cancelling ? "松开取消":"松开发送"):idleTitle)
        }.font(.headline).frame(maxWidth:.infinity,minHeight:50).foregroundStyle(Color.white)
            .background(hold.cancelling ? Color.red:hold.active ? Color.green:Color.accentColor,in:RoundedRectangle(cornerRadius:12))
            .overlay {RoundedRectangle(cornerRadius:12).strokeBorder(.white.opacity(hold.active ? 0.65:0),lineWidth:3)}
            .scaleEffect(hold.active ? 0.98:1)
            .sensoryFeedback(.impact(weight:.medium),trigger:hold.active) {_,active in active}
            .sensoryFeedback(.warning,trigger:hold.cancelling) {_,cancelling in cancelling}
            .overlay(alignment:.bottom) {
                if hold.active {
                    recordingFeedback
                        .padding(.bottom,76).allowsHitTesting(false)
                }
            }
            .contentShape(Rectangle())
            .gesture(DragGesture(minimumDistance:0,coordinateSpace:.global)
                .updating($touching) {_,active,_ in active=true}
                .onChanged {value in
                    guard !disabled,canStart() else {return}
                    if hold.update(verticalTranslation:value.translation.height) {onBegin()}
                }
                .onEnded {value in onFinish(value.translation.height)})
            .onChange(of:touching) {_,active in
                if !active {Task { @MainActor in
                    await Task.yield()
                    if !touching && hold.active {onCancel()}
                }}
            }
            .accessibilityElement(children:.ignore).accessibilityAddTraits(.isButton)
            .accessibilityLabel(hold.active ? "结束录音并发送":idleTitle)
            .accessibilityHint("按住录音，松开发送，上滑松开取消。辅助操作可双击开始，再次双击发送。")
            .accessibilityAction {
                if hold.active {onFinish(0)}
                else if !disabled,canStart() {_ = hold.update(verticalTranslation:0);onBegin()}
            }
            .accessibilityAction(named:Text("取消录音")) {onCancel()}
            .accessibilityIdentifier(identifier).disabled(disabled)
    }
}

/// Keep provider paragraphs intact; never truncate or combine alternative expressions.
enum HintParagraphs {
    static func blocks(_ text:String)->[String] {
        text.components(separatedBy:.newlines).map {$0.trimmingCharacters(in:.whitespacesAndNewlines)}.filter {!$0.isEmpty}
    }
    static func containsEnglish(_ text:String)->Bool {
        text.unicodeScalars.contains {CharacterSet(charactersIn:"abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ").contains($0)}
    }
}
