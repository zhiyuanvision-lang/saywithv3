import SwiftUI

@main
struct SayWithApp: App {
    @State private var model=LearningModel()
    var body: some Scene {WindowGroup {RootView(model:model)}}
}

struct RootView: View {
    @Bindable var model: LearningModel
    @State private var audio=AudioController()
    @State private var showSettings=false
    @Environment(\.scenePhase) private var scenePhase
    var body: some View {
        TabView {
            NavigationStack {
                ScrollView {
                    VStack(alignment:.leading,spacing:24) {
                        if !model.hasAccount {welcome}
                        else if let session=model.session {lesson(session)}
                        else {home}
                        if let error=model.error {
                            Text(error).foregroundStyle(.red).accessibilityIdentifier("errorMessage")
                            if model.hasPendingInput {Button("重试发送") {Task {await model.perform {try await model.retryInput()}}}}
                        }
                        if model.busy {ProgressView("正在处理…").accessibilityIdentifier("busyIndicator")}
                    }.padding()
                }
                .navigationTitle("今天练什么")
                .toolbar {ToolbarItem(placement:.topBarTrailing) {Button("设置",systemImage:"gearshape") {showSettings=true}}}
                .sheet(isPresented:$showSettings) {settings}
            }.tabItem {Label("学习",systemImage:"bubble.left.and.bubble.right")}
            NavigationStack {
                List(model.targets) {target in
                    Button {Task {await model.perform {try await model.generate(target:target)}}} label: {
                        VStack(alignment:.leading) {Text(target.outcome);Text(target.referenceStage).font(.caption).foregroundStyle(.secondary)}
                    }.disabled(model.busy)
                }.navigationTitle("课程地图")
            }.tabItem {Label("地图",systemImage:"map")}
            NavigationStack {
                List {
                    Section("能力记录") {
                        if let profile=model.profile, !profile.targetStates.isEmpty {
                            ForEach(Array(profile.targetStates.enumerated()),id:\.offset) {_,s in
                                VStack(alignment:.leading,spacing:6) {
                                    Text(s["target_id"]?.text ?? "")
                                    Text("独立：\(stateName(s["independent"]?.text)) · 保持：\(stateName(s["retention"]?.text))")
                                        .font(.caption).foregroundStyle(.secondary)
                                }
                            }
                        } else {Text("完成任务后，这里会记录你的表现证据。").foregroundStyle(.secondary)}
                    }
                    Section {Text("一次完成只证明本次表现；系统会另行检查隔期保持和换条件应用。").font(.footnote)}
                    Button("刷新能力记录") {Task {await model.perform {try await model.refresh()}}}
                }.navigationTitle("学习进度")
            }.tabItem {Label("进度",systemImage:"chart.bar")}
        }
        .tint(.teal)
        .task {if CredentialStore.read(account:model.baseURL) != nil {await model.perform {try await model.connect()}}}
        .onChange(of:scenePhase) {_,phase in if phase != .active {audio.discard()}}
    }
    private var welcome: some View {
        VStack(alignment:.leading,spacing:20) {
            Text("把英语说出来").font(.largeTitle.bold())
            Text("先理解一种说法，再换成自己的内容，最后完成一次真实交流任务。")
            TextField("后端服务地址",text:$model.baseURL).textInputAutocapitalization(.never).autocorrectionDisabled().keyboardType(.URL)
                .textFieldStyle(.roundedBorder).accessibilityIdentifier("backendURL")
            Picker("目前熟悉的难度",selection:$model.stage) {ForEach(["Pre-A1","A1","A2","B1","B2","C1","C2"],id:\.self) {Text($0)}}
            Text("难度只是起点参考，实际表现会影响后续推荐。").font(.footnote).foregroundStyle(.secondary)
            TextField("感兴趣的交流主题",text:$model.context).textFieldStyle(.roundedBorder)
            Button("开始建立学习记录") {Task {await model.perform {try await model.connect(create:true)}}}
                .buttonStyle(.borderedProminent).disabled(model.busy).accessibilityIdentifier("createAccount")
        }
    }
    private var home: some View {
        VStack(alignment:.leading,spacing:20) {
            Text("用十分钟，练好一个交流目标。").font(.title2.bold())
            Text("系统会根据你的表现选择新学、巩固或复习任务。")
            if model.health?.mode == "fixture" {Text("当前为测试模式，不更新真实能力。").font(.footnote).foregroundStyle(.secondary)}
            if let job=model.job {
                Text(job.label).accessibilityIdentifier("jobState")
                if let reason=job.reason {Text(reason).foregroundStyle(.secondary)}
                if !job.terminal {
                    Button("继续查看生成结果") {Task {await model.perform {try await model.poll()}}}.disabled(model.busy)
                    Button("取消生成",role:.destructive) {Task {do {try await model.cancelJob()} catch {model.error=error.localizedDescription}}}
                }
            }
            Button("开始今天的学习") {Task {await model.perform {try await model.generate()}}}
                .buttonStyle(.borderedProminent).disabled(model.busy).accessibilityIdentifier("startLearning")
        }
    }
    @ViewBuilder private func lesson(_ session:SessionState) -> some View {
        Text(phaseTitle(session.view.phase)).font(.title2.bold()).accessibilityIdentifier("phaseTitle")
        Text(session.view.instruction)
        if session.view.fixture {Text("测试内容 · 不计入能力记录").font(.footnote).foregroundStyle(.secondary)}
        if session.view.phase == "learning", session.view.materials.indices.contains(model.selectedMaterial) {
            let m=session.view.materials[model.selectedMaterial]
            VStack(alignment:.leading,spacing:18) {
                Text(m.intentZh).font(.headline)
                Text("英文声音由 AI 生成").font(.caption).foregroundStyle(.secondary)
                if model.answerVisible {Text(m.expression).font(.title2).accessibilityIdentifier("englishExpression")
                    Text(m.explanationZh).foregroundStyle(.secondary)
                }
                if let ref=m.audioRef {Button("听英文声音",systemImage:"speaker.wave.2") {play(ref)}}
                Text(m.personalPromptZh)
                TextField("换成自己的说法",text:$model.personalText,axis:.vertical).textFieldStyle(.roundedBorder).accessibilityIdentifier("personalExpression")
                Button(model.answerVisible ? "遮住答案，自己试说" : "查看英文说法") {model.answerVisible.toggle()}
                    .accessibilityIdentifier("hideAnswer")
                Button("已试说，记录这一表达") {Task {await model.perform {try await model.learn()}}}
                    .disabled(model.busy || model.personalText.isEmpty || model.answerVisible).accessibilityIdentifier("recordLearning")
                Button("进入有提示练习") {Task {await model.perform {try await model.next()}}}
                    .buttonStyle(.borderedProminent).disabled(model.busy).accessibilityIdentifier("nextPhase")
            }
        } else if session.view.phase == "finished" {
            Text(model.assessment?.summary ?? "本次任务已结束。")
            Button("回到今日学习") {audio.discard();model.leave()}.buttonStyle(.borderedProminent)
        } else {
            if !session.view.learnerFacts.isEmpty {
                Text(session.view.learnerFacts.sorted(by: {$0.key < $1.key}).map {"\(factName($0.key))：\($0.value.text)"}.joined(separator:"\n"))
                    .font(.callout).foregroundStyle(.secondary)
            }
            ForEach(session.turns) {turn in
                VStack(alignment:.leading,spacing:8) {
                    Text(turn.speaker == "learner" ? "你" : "对方").font(.caption).foregroundStyle(.secondary)
                    Text(turn.content).textSelection(.enabled)
                    if let ref=turn.audioRef {Button("播放声音",systemImage:"play.circle") {play(ref)}}
                }.padding(.vertical,8)
            }
            if let message=audio.interruptionMessage {Text(message).foregroundStyle(.red)}
            if session.view.availableActions.contains("speak") {
                Button(audio.recording ? "结束录音并发送" : "录音说英文",systemImage:audio.recording ? "stop.circle.fill" : "mic.fill") {
                    Task {await model.perform {
                        if audio.recording {let data=try audio.stop();try await model.send(kind:"speech",audio:data)}
                        else {try await audio.start()}
                    }}
                }.buttonStyle(.borderedProminent).disabled(model.busy || model.hasPendingInput)
                DisclosureGroup("也可以输入英文练习") {
                    Text("输入练习不作为口语掌握证据。").font(.footnote)
                    TextField("你的英文回应",text:$model.typedReply,axis:.vertical).textFieldStyle(.roundedBorder)
                        .accessibilityIdentifier("typedReply")
                    Button("发送") {Task {await model.perform {try await model.send(kind:"text")}}}
                        .disabled(model.busy || model.typedReply.isEmpty || model.hasPendingInput).accessibilityIdentifier("sendReply")
                }
                HStack {
                    Button("请对方再说一次") {Task {await model.perform {try await model.send(kind:"request_repeat")}}}.disabled(model.busy)
                    if session.view.availableActions.contains("request_hint") {Button("给我提示") {Task {await model.perform {try await model.send(kind:"request_hint")}}}.disabled(model.busy)}
                }
            }
            if session.view.phase == "supported_practice" || session.view.availableActions.contains("next") {
                Button("独立完成新任务") {Task {await model.perform {try await model.next()}}}
                    .disabled(model.busy || audio.recording).accessibilityIdentifier("independentTask")
            } else {
                Button("结束任务，查看反馈") {Task {await model.perform {try await model.finish()}}}
                    .disabled(model.busy || audio.recording).accessibilityIdentifier("finishTask")
            }
        }
    }
    private var settings: some View {
        NavigationStack {
            Form {
                TextField("服务地址",text:$model.baseURL).textInputAutocapitalization(.never).keyboardType(.URL)
                Picker("难度参考",selection:$model.stage) {ForEach(["Pre-A1","A1","A2","B1","B2","C1","C2"],id:\.self) {Text($0)}}
                TextField("主题",text:$model.context)
                Button("连接并刷新") {Task {await model.perform {try await model.connect(savePreferences:true)};if model.error == nil {showSettings=false}}}
                Text("模型与语音服务由后端管理。录音将发送给后端和字节语音服务用于识别。")
                    .font(.footnote).foregroundStyle(.secondary)
            }.navigationTitle("学习设置")
                .toolbar {ToolbarItem(placement:.cancellationAction) {Button("关闭") {showSettings=false}}}
        }
    }
    private func play(_ ref: String) {Task {await model.perform {try audio.play(try await model.sound(ref))}}}
    private func factName(_ key:String) -> String {
        ["scenario":"交流背景","original_plan":"原定安排","available_times":"你有空的时间","cannot_make_times":"你没空的时间","location":"地点"][key] ?? key
    }
    private func stateName(_ state:String?) -> String {
        ["not_checked":"待检查","insufficient_evidence":"证据不足","supported":"有提示完成","needs_recheck":"需要重新检查","provisional":"本次完成，待复核","demonstrated":"多次完成","needs_practice":"需要补练","not_demonstrated":"尚未证明"][state ?? ""] ?? "待检查"
    }
    private func phaseTitle(_ phase:String) -> String {
        ["learning":"学习一种说法","supported_practice":"有提示地练习","independent_application":"换条件，独立交流","evaluating":"正在评价本次表现","finished":"本次学习反馈"][phase] ?? phase
    }
}
