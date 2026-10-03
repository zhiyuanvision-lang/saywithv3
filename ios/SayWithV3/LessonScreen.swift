import SwiftUI

struct LessonScreen:View {
    @Bindable var model:LearningModel
    @State private var audio=AudioController()
    @State private var showHints=false
    @State private var feedbackOpen=false
    @State private var showTextInput=false
    @State private var showTaskInfo=false
    @State private var followConversation=true
    @State private var playedTurns:Set<String>=[]
    @State private var shownTranslations:Set<String>=["material:0"]
    @FocusState private var replyFocused:Bool
    @State private var showExit=false
    @State private var showReturn=false
    @State private var showHistory=false
    @State private var showUsage=false
    @State private var showDemo=false
    @State private var demoTask:Task<Void,Never>?
    @State private var highlightedLine:Int?
    @Environment(\.scenePhase) private var scenePhase
    @Environment(\.dynamicTypeSize) private var typeSize
    private var current:SessionState? {model.session}
    private var phase:String {current?.view.phase ?? "learning"}
    private var isReview:Bool {current?.view.entryKind=="review"}
    private var isGuided:Bool {phase=="supported_practice"}
    private var isIndependent:Bool {phase=="independent_application"}
    private var isFeedback:Bool {phase=="finished"}
    private var activeMaterial:Material? {
        guard let view=current?.view,view.materials.indices.contains(model.selectedMaterial) else {return nil}
        return view.materials[model.selectedMaterial]
    }
    private var partner:Turn? {current?.turns.last(where:{$0.speaker=="partner"})}
    private var actions:[String] {current?.view.availableActions ?? []}
    private var status:String {
        if audio.recording {return "录音中 · \(Int(audio.duration)) 秒"}
        if !model.requestStatus.isEmpty {return model.requestStatus}
        if model.busy {return "正在准备下一步"}
        if audio.paused {return "语音已暂停"}
        if audio.playing {return audio.playingID=="own" || current?.turns.contains(where:{$0.speaker=="learner" && $0.audioRef==audio.playingID})==true ? "正在回听自己" : phase=="learning" ? "示范播放中" : "对方说话中"}
        if phase=="learning" {return typeSize.isAccessibilitySize ? "点击录音跟读":"点击录音，跟着示范说"}
        return "轮到你了"
    }
    var body:some View {
        VStack(spacing:0) {
            sessionHeader
            if (isGuided || isIndependent) && !typeSize.isAccessibilitySize {taskRegion.padding(.horizontal,20).padding(.top,22).padding(.bottom,14).background(Color(uiColor:.systemBackground))}
            Divider()
            GeometryReader {viewport in ScrollViewReader {proxy in ScrollView {
                VStack(alignment:.leading,spacing:16) {
                    if !(isGuided || isIndependent) || typeSize.isAccessibilitySize {taskRegion}
                    if phase=="learning" {learningContent}
                    else if phase=="guided_feedback" {guidedSummary}
                    else if isFeedback {feedbackContent}
                    else {conversationContent}
                    Color.clear.frame(height:1).id("conversationBottom").background(GeometryReader {geo in Color.clear.preference(key:ConversationBottomKey.self,value:geo.frame(in:.named("lessonScroll")).minY)})
                }.frame(maxWidth:.infinity,alignment:.leading).padding(.horizontal,20).padding(.top,22).padding(.bottom,20)
            }.background(Color(uiColor:.systemGroupedBackground))
                .accessibilityIdentifier("lessonContent").coordinateSpace(name:"lessonScroll")
                .onPreferenceChange(ConversationBottomKey.self) {y in followConversation=y<=viewport.size.height+60}
                .onChange(of:current?.turns.last?.turnId) {_,_ in
                    if followConversation && (isGuided || isIndependent) {proxy.scrollTo("conversationBottom",anchor:.bottom)}
                }
            }}
        }
        .background(Color(uiColor:.systemBackground))
        .safeAreaInset(edge:.bottom,spacing:0) {footer}
        .sheet(isPresented:$showHints) {hintPanel}
        .sheet(isPresented:$showTextInput) {textInputPanel}
        .sheet(isPresented:$showTaskInfo) {taskInfoPanel}
        .sheet(isPresented:$showUsage) {usagePanel}
        .sheet(isPresented:$showDemo) {demoPanel}
        .sheet(isPresented:$showHistory) {historyPanel}
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
            if value != .active {demoTask?.cancel();audio.discard()}
        }
        .onChange(of:current?.view.taskId) {_,_ in audio.discard();showHistory=false;replyFocused=false;followConversation=true}
        .onChange(of:phase) {_,_ in demoTask?.cancel();audio.discard();showHints=false;showHistory=false;highlightedLine=nil;replyFocused=false}
        .task(id:partner?.turnId) {
            guard (isGuided || isIndependent),let ref=partner?.audioRef else {return}
            do {
                while model.busy {try await Task.sleep(for:.milliseconds(50))}
                try Task.checkCancellation()
                guard !audio.recording,!feedbackOpen,scenePhase == .active else {return}
                try audio.play(try await model.sound(ref),id:ref);playedTurns.insert(partner?.turnId ?? "")
            } catch is CancellationError {} catch {model.error=error.localizedDescription}
        }
        .onReceive(NotificationCenter.default.publisher(for:Notification.Name("PauseSayWithLearning"))) {_ in
            feedbackOpen=true;demoTask?.cancel();if audio.recording {audio.discard()} else {audio.pausePlayback()}
        }
        .onReceive(NotificationCenter.default.publisher(for:Notification.Name("ResumeSayWithLearning"))) {_ in feedbackOpen=false}
        .onDisappear {demoTask?.cancel();audio.discard()}
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
                    if phase=="learning" {Button("用法说明") {showUsage=true};Button("完整示范对话") {showDemo=true}}
                    Button("查看任务与条件") {showTaskInfo=true}
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
                    Text(current?.view.title ?? "本次任务").font(.title3.weight(.semibold))
                    if let round=current?.view.guidedRound {Text("第 \(round) / 3 轮")}
                    Text(current?.view.instruction ?? "")
                    ForEach((current?.view.learnerFacts ?? [:]).keys.sorted(),id:\.self) {key in
                        Text(current?.view.learnerFacts[key]?.text ?? "")
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
                Text(isFeedback ? feedbackTitle : current?.view.title ?? "本次交流任务").font(.title3.weight(.semibold)).fixedSize(horizontal:false,vertical:true).accessibilityIdentifier("taskTitle")
                Spacer(minLength:8)
                if isReview && !isFeedback {Text("1/1").font(.subheadline).foregroundStyle(.secondary)}
                else if let round=current?.view.guidedRound {Text("\(round)/3").font(.subheadline).foregroundStyle(.secondary).accessibilityIdentifier("guidedRound").accessibilityLabel("第 \(round) 轮，共三轮，\(current?.view.guidedRoundTitle ?? "")")}
            }
            if isFeedback {Text(result?.summary ?? "正在整理本次表现").font(.subheadline).foregroundStyle(.secondary)}
            else if phase=="learning" {Text(current?.view.instruction ?? "").font(.subheadline).foregroundStyle(.secondary)}
            else if phase=="guided_feedback" {Text("三轮引导练习已结束").font(.subheadline).foregroundStyle(.secondary)}
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
            if let first=current?.view.demonstration?.first {
                VStack(alignment:.leading,spacing:10) {
                    Text(current?.view.partnerName ?? "对方").font(.caption).foregroundStyle(.secondary)
                    Text(first.text).font(.body).fixedSize(horizontal:false,vertical:true)
                    HStack(spacing:4) {
                        if let ref=first.audioRef {Button {togglePlayback(ref)} label:{Image(systemName:audio.playingID==ref && audio.playing ? "pause.fill":"speaker.wave.2.fill").frame(width:44,height:44)}.accessibilityLabel("重播这句话")}
                        translationButton("demo:0",known:first.meaningZh)
                    }
                    if shownTranslations.contains("demo:0") {Text(first.meaningZh ?? model.translations["demo:0"] ?? "正在加载翻译").font(.subheadline).foregroundStyle(.secondary)}
                }.frame(maxWidth:.infinity,alignment:.leading).padding(.horizontal,18).padding(.vertical,12).background(Color(uiColor:.secondarySystemGroupedBackground),in:RoundedRectangle(cornerRadius:16))
            }
            Text("重点表达").font(.headline).padding(.top,4)
            VStack(alignment:.leading,spacing:12) {
                Text(material.expression).font(.title3).fixedSize(horizontal:false,vertical:true).accessibilityIdentifier("englishExpression")
                if shownTranslations.contains("material:\(model.selectedMaterial)") {Text(material.meaningZh ?? model.translations["material:\(model.selectedMaterial)"] ?? "正在加载翻译").font(.subheadline).foregroundStyle(.secondary)}
                Divider()
                HStack(spacing:4) {
                    if let ref=material.audioRef {Button {togglePlayback(ref)} label:{Image(systemName:audio.playingID==ref && audio.playing ? "pause.fill":"speaker.wave.2.fill").frame(width:44,height:44)}.accessibilityLabel("播放示范")}
                    translationButton("material:\(model.selectedMaterial)",known:material.meaningZh)
                    Spacer()
                    if let ref=material.audioRef {Button("慢速") {play(ref,rate:0.75)}.font(.subheadline).frame(minWidth:44,minHeight:44)}
                }.disabled(model.busy || audio.recording)
            }.frame(maxWidth:.infinity,alignment:.leading).padding(18).background(Color(uiColor:.secondarySystemGroupedBackground),in:RoundedRectangle(cornerRadius:16))
        }
    }
    private var usagePanel:some View {
        NavigationStack {ScrollView {Text(activeMaterial?.explanationZh ?? "").frame(maxWidth:.infinity,alignment:.leading).padding(20)}.navigationTitle("用法说明").navigationBarTitleDisplayMode(.inline).toolbar {ToolbarItem(placement:.cancellationAction) {Button("关闭") {showUsage=false}}}}.presentationDetents([.medium,.large])
    }
    private var demoPanel:some View {
        NavigationStack {ScrollView {VStack(alignment:.leading,spacing:20) {
            Button {playDemo()} label:{Image(systemName:audio.playing ? "pause.fill":"speaker.wave.2.fill").frame(width:44,height:44)}.accessibilityLabel("播放完整对话")
            ForEach(Array((current?.view.demonstration ?? []).enumerated()),id:\.offset) {index,line in
                VStack(alignment:.leading,spacing:10) {
                    Text(line.speaker=="learner" ? "你":current?.view.partnerName ?? "对方").font(.caption).foregroundStyle(.secondary)
                    Text(line.text).foregroundStyle(highlightedLine==index ? Color.accentColor:Color.primary)
                    HStack(spacing:4) {if let ref=line.audioRef {Button {togglePlayback(ref)} label:{Image(systemName:"speaker.wave.2.fill").frame(width:44,height:44)}.accessibilityLabel("重播这句话")};translationButton("demo-line:\(index)",known:line.meaningZh,source:index==0 ? "demo:0":"material:\(index-1)")}
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
                    VStack(alignment:.leading,spacing:10) {
                    if own || actions.contains("show_text") {Text(turn.content).font(.body).foregroundStyle(own ? Color.white:Color.primary).fixedSize(horizontal:false,vertical:true)}
                    else {Text("请听对方的声音，再说出回应。").font(.body)}
                    HStack(spacing:4) {
                    if let ref=turn.audioRef,own || actions.contains("request_repeat") || !playedTurns.contains(turn.turnId) || (audio.paused && audio.playingID==ref) {
                        Button {
                            if audio.playingID==ref && audio.playing {audio.pausePlayback()}
                            else if audio.playingID==ref && audio.paused {do {try audio.resumePlayback()} catch {model.error=error.localizedDescription}}
                            else if own {play(ref)}
                            else {run {
                                if playedTurns.contains(turn.turnId) {try await model.send(kind:"request_repeat",sourceTurnID:turn.turnId)}
                                try audio.play(try await model.sound(ref),id:ref);playedTurns.insert(turn.turnId)
                            }}
                        } label:{Image(systemName:audio.playingID==ref && audio.playing ? "pause.fill":"speaker.wave.2.fill").frame(width:44,height:44)}
                        .accessibilityLabel(audio.playingID==ref && audio.playing ? "暂停播放":own ? "回听自己":"重播这句话").disabled(model.busy || audio.recording)
                    }
                        if !own && actions.contains("request_translation") {translationButton(turn.turnId)}
                    }
                    if shownTranslations.contains(turn.turnId),let text=model.translations[turn.turnId] {Text(text).font(.subheadline).foregroundStyle(.secondary)}
                    }.tint(own ? Color.white:Color.accentColor).padding(.horizontal,14).padding(.vertical,12).background(own ? Color.accentColor:Color(uiColor:.secondarySystemGroupedBackground),in:RoundedRectangle(cornerRadius:16))
                }
                if !own {Spacer(minLength:32)}
            }.id(turn.turnId)
        }
    }
    private var guidedSummary:some View {
        VStack(alignment:.leading,spacing:24) {
            Text("本次使用的帮助").font(.headline).foregroundStyle(Color.accentColor)
            Text((current?.view.supportUsed ?? []).isEmpty ? "本次没有请求答案提示。" : (current?.view.supportUsed ?? []).joined(separator:"、"))
            Text("提示下完成只证明本次练习表现。接下来换一组条件，检查独立交流。").foregroundStyle(.secondary)
            Button("再练一次") {run {try await model.transition("retry_guided")}}.frame(minHeight:44).buttonStyle(.bordered)
        }
    }
    private var result:Assessment? {model.assessment ?? current?.view.assessment}
    private var feedbackTitle:String {
        guard let result else {return "正在整理本次表现"}
        if result.validation["status"]?.text != "accepted" {return "本次表现还无法确认"}
        return ["completed":isReview ? "复习完成":"任务完成","partial":"已完成部分要求","failed":"还需要练习"][result.targetResults.first?["result"]?.text ?? ""] ?? "本次表现还无法确认"
    }
    private var evidence:[[String:JSONValue]] {
        guard let value=result?.targetResults.first?["checks"],case .array(let checks)=value else {return []}
        return checks.compactMap {if case .object(let d)=$0 {return d};return nil}
    }
    private var improvement:String {
        if result?.validation["status"]?.text != "accepted" {return "回听录音，再用一组有效任务确认表现。"}
        return evidence.first(where:{$0["result"]?.text != "met"})?["criterion"]?.text ?? "换一个场景，再检查能否独立完成。"
    }
    private var taskCompleted:Bool {result?.validation["status"]?.text=="accepted" && result?.targetResults.first?["result"]?.text=="completed"}
    private var resultLabel:String {
        guard result?.validation["status"]?.text=="accepted" else {return "证据不足"}
        return ["completed":isReview ? "本次复习任务完成":"本次独立完成","partial":"已完成部分要求","failed":"还需要练习"][result?.targetResults.first?["result"]?.text ?? ""] ?? "本次表现还无法确认"
    }
    private var feedbackContent:some View {
        VStack(alignment:.leading,spacing:16) {
            VStack(alignment:.leading,spacing:12) {
                Label("完成证据",systemImage:taskCompleted ? "checkmark.circle.fill":"circle").font(.headline)
                Text(resultLabel).font(.subheadline).foregroundStyle(result?.validation["status"]?.text=="accepted" ? Color.accentColor:Color.secondary)
                if let turn=current?.turns.last(where:{$0.speaker=="learner"}),!turn.content.isEmpty {Text(turn.content).font(.title3)}
                if let check=evidence.first {Text(check["criterion"]?.text ?? "").font(.subheadline).foregroundStyle(.secondary)}
            }.frame(maxWidth:.infinity,alignment:.leading).padding(18).background(Color(uiColor:.secondarySystemGroupedBackground),in:RoundedRectangle(cornerRadius:16))
            Text("下一步").font(.subheadline).foregroundStyle(.secondary)
            Text(improvement).font(.subheadline).foregroundStyle(.secondary)
            Button("针对性补练") {run {try await model.transition("retry_guided")}}.frame(minHeight:44)
        }
    }
    private var shadowReady:Bool {
        guard phase=="learning",let feedback=model.shadowFeedback ?? current?.view.shadowFeedback else {return false}
        return feedback.canContinue && feedback.materialIndexMatches(model.selectedMaterial)
    }
    private var footer:some View {
        VStack(spacing:8) {
            if let error=model.error {Text(error).font(.footnote).foregroundStyle(.red).lineLimit(2).accessibilityIdentifier("errorMessage");if error.contains("麦克风") {Button("打开系统设置") {if let url=URL(string:UIApplication.openSettingsURLString) {UIApplication.shared.open(url)}}}}
            if let message=audio.interruptionMessage {Text(message).font(.footnote).foregroundStyle(.secondary)}
            if isFeedback {
                mainButton(isReview ? "完成复习":"完成学习",id:"finishLearning") {audio.discard();model.leave()}
                Button("查看本次记录") {showHistory=true}.font(.subheadline).frame(minHeight:44)
            } else if phase=="guided_feedback" {
                mainButton(isReview ? "换内容再试":"开始独立应用",id:"independentTask") {
                    if isReview,let review=model.recommendations?.learned.first(where:{$0.targetId==current?.view.reviewMetadata?["target_id"]?.text}) {model.leave();run {try await model.generate(review:review)}} else {run {try await model.next()}}
                }
            } else if phase=="evaluating" {
                ProgressView("正在整理本次表现")
                Button("继续等待结果") {run {if actions.contains("next") {try await model.next()} else {try await model.finish()}}}.frame(minHeight:44)
            } else {
                if audio.recording || model.busy || audio.playing || audio.paused || audio.lastRecording != nil {
                    HStack {if model.busy {ProgressView()};Text(status).font(.caption).foregroundStyle(.secondary).accessibilityIdentifier("audioStatus")}
                }
                if phase=="learning",let feedback=model.shadowFeedback ?? current?.view.shadowFeedback,feedback.materialIndexMatches(model.selectedMaterial) {Text(feedback.message).font(.caption).foregroundStyle(.secondary).lineLimit(2)}
                if shadowReady {
                    mainButton(model.selectedMaterial+1<(current?.view.materials.count ?? 0) ? "继续学习下一表达":"试着换个内容说",id:"nextPhase") {audio.discard();run {try await model.advanceMaterial()}}
                } else {
                    Button {if audio.lastRecording != nil && !audio.recording {audio.lastRecording=nil};record()} label:{HStack(spacing:8) {Image(systemName:audio.recording ? "stop.fill":"mic.fill");Text(audio.recording ? "结束录音":model.busy ? "正在处理":phase=="learning" ? "录音跟读":"开始录音")}.font(.headline).frame(maxWidth:.infinity,minHeight:50).foregroundStyle(Color.white).background(audio.recording ? Color.red:Color.accentColor,in:RoundedRectangle(cornerRadius:12))}.buttonStyle(.plain).accessibilityLabel(audio.recording ? "结束录音":phase=="learning" ? "录音跟读":"开始录音").accessibilityIdentifier("recordButton").disabled(model.busy || model.hasPendingInput || model.hasPendingShadow)
                }
                if audio.lastRecording != nil || isGuided || isIndependent {
                    HStack(spacing:12) {
                        if let recording=audio.lastRecording {
                            Button {if audio.playingID=="own" && audio.playing {audio.pausePlayback()} else {tryPlay(recording)}} label:{Image(systemName:audio.playingID=="own" && audio.playing ? "pause.fill":"speaker.wave.2.fill").frame(width:44,height:44)}.accessibilityLabel("回听自己").accessibilityIdentifier("playOwnRecording")
                            if phase=="learning" {Button("重试") {audio.lastRecording=nil;model.shadowFeedback=nil;record()}.frame(minHeight:44)}
                        }
                        Spacer(minLength:0)
                        if isGuided {Button("提示") {showHints=true}.font(.subheadline).frame(minHeight:44).accessibilityIdentifier("hintButton")}
                        if actions.contains("text_input") {Button {showTextInput=true} label:{Image(systemName:"keyboard").frame(width:44,height:44)}.accessibilityLabel("也可以输入英文练习")}
                        if current?.turns.contains(where:{$0.speaker=="learner"})==true {
                            if isGuided {Button((current?.view.guidedRound ?? 1)<3 ? "继续下一轮":"结束引导练习") {run {try await model.next()}}.font(.subheadline).frame(minHeight:44).accessibilityIdentifier("nextGuidedRound")}
                            else if isIndependent {Button("结束任务") {run {try await model.finish()}}.font(.subheadline).frame(minHeight:44).accessibilityIdentifier("finishTask")}
                        }
                        Spacer(minLength:0)
                    }.disabled(model.busy || audio.recording)
                }
                if model.hasPendingShadow {Button("重试提交跟读") {run {try await model.retryShadow()}}.frame(minHeight:44);Button("放弃本次录音") {model.discardShadowRequest();audio.lastRecording=nil}.frame(minHeight:44)}
                if model.hasPendingInput {Button("重试发送") {run {try await model.retryInput()}}.frame(minHeight:44)}
                if let recording=audio.lastRecording,!audio.recording,audio.interruptionMessage != nil {Button("发送已保存的录音") {run {if phase=="learning" {try await model.shadow(recording)} else {try await model.send(kind:"speech",audio:recording)}}}.frame(minHeight:44)}
            }
        }.padding(.horizontal,20).padding(.top,16).padding(.bottom,12).frame(maxWidth:.infinity).background(Color(uiColor:.systemBackground)).overlay(alignment:.top) {Divider()}
    }
    private var textInputPanel:some View {
        NavigationStack {
            Form {
                Text("文字练习不计入口语能力。").font(.footnote).foregroundStyle(.secondary)
                TextField("你的英文回应",text:$model.typedReply,axis:.vertical)
                    .textInputAutocapitalization(.sentences).focused($replyFocused).accessibilityIdentifier("typedReply")
                Button("发送") {
                    replyFocused=false;showTextInput=false
                    run {try await model.send(kind:"text")}
                }.frame(minHeight:44).disabled(model.busy || model.typedReply.isEmpty || model.hasPendingInput).accessibilityIdentifier("sendReply")
            }.navigationTitle("输入英文练习").navigationBarTitleDisplayMode(.inline)
                .toolbar {ToolbarItem(placement:.cancellationAction) {Button("关闭") {replyFocused=false;showTextInput=false}}}
        }.presentationDetents([.medium,.large]).presentationDragIndicator(.visible)
    }
    private var hintPanel:some View {
        NavigationStack {
            ScrollView {
                VStack(alignment:.leading,spacing:20) {
                    Text("先自己尝试，需要时再逐步展开帮助。").foregroundStyle(.secondary)
                    ForEach([("intent","表达意图"),("pattern","句型提示"),("example","完整示范"),("learned","所学表达")],id:\.0) {level,title in
                        Button(title) {run {try await model.send(kind:"request_hint",hintLevel:level)}}.buttonStyle(.bordered).frame(minHeight:44).disabled(model.busy).accessibilityIdentifier("hint-"+level)
                    }
                    if let text=model.hintText {Text(text).font(.title3).textSelection(.enabled).accessibilityIdentifier("hintText")}
                    if let error=model.error {Text(error).foregroundStyle(.red)}
                    if model.busy {ProgressView("正在准备提示")}
                }.frame(maxWidth:.infinity,alignment:.leading).padding(20)
            }.navigationTitle("提示").navigationBarTitleDisplayMode(.inline)
                .toolbar {ToolbarItem(placement:.cancellationAction) {Button("关闭") {showHints=false}}}
        }.presentationDetents([.medium,.large]).presentationDragIndicator(.visible)
    }
    private func mainButton(_ title:String,id:String,action:@escaping()->Void)->some View {
        Button(action:action) {Text(title).font(.headline).foregroundStyle(Color.white).frame(maxWidth:.infinity,minHeight:50)}
            .buttonStyle(.plain).background(Color.accentColor,in:RoundedRectangle(cornerRadius:12)).disabled(model.busy || audio.recording).accessibilityIdentifier(id)
    }
    private func run(_ operation:@escaping () async throws -> Void) {Task {await model.perform(operation)}}
    private func togglePlayback(_ ref:String) {
        if audio.playingID==ref && audio.playing {audio.pausePlayback()}
        else if audio.playingID==ref && audio.paused {
            do {try audio.resumePlayback()} catch {model.error=error.localizedDescription}
        } else {play(ref)}
    }
    private func play(_ ref:String,rate:Float=1) {run {try audio.play(try await model.sound(ref),id:ref,rate:rate)}}
    private func tryPlay(_ data:Data) {do {try audio.play(data)} catch {model.error=error.localizedDescription}}
    private func translationButton(_ key:String,known:String?=nil,source:String?=nil)->some View {
        Button {
            if shownTranslations.contains(key) {shownTranslations.remove(key)}
            else {shownTranslations.insert(key);if known?.isEmpty != false && model.translations[source ?? key]==nil {translate(source ?? key)}}
        } label:{Image(systemName:"translate").frame(width:44,height:44)}
            .accessibilityLabel(shownTranslations.contains(key) ? "收起翻译":"查看翻译").disabled(model.busy || audio.recording)
    }
    private func translate(_ key:String) {run {try await model.send(kind:"request_translation",sourceTurnID:key)}}
    private func record() {
        run {
            if audio.recording {
                let data=try audio.stop()
                if phase=="learning" {try await model.shadow(data)} else {try await model.send(kind:"speech",audio:data)}
            } else {try await audio.start()}
        }
    }
    private func playDemo() {
        if demoTask != nil {demoTask?.cancel();demoTask=nil;audio.stopPlayback();highlightedLine=nil;return}
        demoTask=Task {
            do {
                for (index,line) in (current?.view.demonstration ?? []).enumerated() {
                    try Task.checkCancellation()
                    guard let ref=line.audioRef else {continue}
                    let data=try await model.sound(ref);highlightedLine=index
                    try await audio.playAndWait(data,id:"demo-\(index)")
                }
            } catch is CancellationError {} catch {model.error=error.localizedDescription}
            highlightedLine=nil;demoTask=nil
        }
    }
}

private struct ConversationBottomKey:PreferenceKey {
    static let defaultValue:CGFloat=0
    static func reduce(value:inout CGFloat,nextValue:()->CGFloat) {value=nextValue()}
}
