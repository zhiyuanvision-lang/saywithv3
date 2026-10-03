import SwiftUI

@main
struct SayWithApp: App {
    @State private var model=LearningModel()
    var body: some Scene {WindowGroup {RootView(model:model)}}
}

struct RootView: View {
    @Bindable var model: LearningModel
    @State private var showSettings=false
    @State private var showLearned=false
    @ScaledMetric(relativeTo:.title2) private var homeTitleSize:CGFloat=26
    @Environment(\.scenePhase) private var scenePhase
    var body: some View {
        TabView {
            NavigationStack {
                VStack(alignment:.leading,spacing:0) {
                    Text("学习").font(.system(size:homeTitleSize,weight:.semibold))
                        .padding(.horizontal,20).padding(.top,12).padding(.bottom,2)
                        .accessibilityIdentifier("homeTitle").accessibilityAddTraits(.isHeader)
                ScrollView {
                    VStack(alignment:.leading,spacing:24) {
                        if !model.hasAccount {welcome}
                        else {home}
                        if let error=model.error {
                            Text(error).foregroundStyle(.red).accessibilityIdentifier("errorMessage")
                            if model.hasPendingInput {Button("重试发送") {Task {await model.perform {try await model.retryInput()}}}}
                        }
                        if model.busy {ProgressView("正在处理…").accessibilityIdentifier("busyIndicator")}
                    }.padding(.horizontal,20).padding(.vertical,20)
                }
                }
                .background(Color(uiColor:.systemGroupedBackground))
                .toolbar(.hidden,for:.navigationBar)
            }.tabItem {Label("学习",systemImage:"book.fill")}
            NavigationStack {
                List {
                    Section("能力记录") {
                        if let profile=model.profile, !profile.targetStates.isEmpty {
                            ForEach(Array(profile.targetStates.enumerated()),id:\.offset) {_,s in
                                VStack(alignment:.leading,spacing:6) {
                                    LookupText(model.recommendations?.learned.first(where:{$0.targetId==s["target_id"]?.text})?.title ?? "交流目标")
                                    Text("独立：\(stateName(s["independent"]?.text)) · 保持：\(stateName(s["retention"]?.text)) · 迁移：\(stateName(s["transfer"]?.text))")
                                        .font(.caption).foregroundStyle(.secondary)
                                }
                            }
                        } else {Text("完成任务后，这里会记录你的表现证据。").foregroundStyle(.secondary)}
                    }
                    Section {Text("一次完成只证明本次表现；系统会另行检查隔期保持和换条件应用。").font(.footnote)}
                    Button("查看已学内容") {showLearned=true}
                    Button("刷新能力记录") {Task {await model.perform {try await model.refresh()}}}
                }.navigationTitle("学习进展")
            }.tabItem {Label("进展",systemImage:"chart.bar")}
            NavigationStack {
                List {
                    Section {
                        HStack(spacing:14) {
                            Image(systemName:"person.crop.circle.fill").font(.system(size:44)).foregroundStyle(Color.accentColor)
                            VStack(alignment:.leading,spacing:6) {Text("学习者").font(.headline);Text("难度参考 · \(model.stage)").font(.subheadline).foregroundStyle(.secondary)}
                        }.padding(.vertical,8)
                    }
                    Section {
                        NavigationLink {NotebookPage(model:model)} label:{Label("生词本",systemImage:"bookmark")}.accessibilityIdentifier("notebookEntry")
                        Button {showSettings=true} label:{Label("学习设置",systemImage:"slider.horizontal.3")}
                        Button {NotificationCenter.default.post(name:Notification.Name("OpenSayWithFeedback"),object:nil)} label:{Label("意见反馈",systemImage:"bubble.left.and.bubble.right")}.accessibilityIdentifier("mineFeedbackEntry")
                    }
                    Section {
                        Link("隐私政策",destination:URL(string:"https://saywith.zhiyuanv.com/legal/privacy")!)
                        Link("用户协议",destination:URL(string:"https://saywith.zhiyuanv.com/legal/terms")!)
                        Link("联系支持",destination:URL(string:"https://saywith.zhiyuanv.com/contact.html")!)
                        Text("版本 \(Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "") (\(Bundle.main.infoDictionary?["CFBundleVersion"] as? String ?? ""))").font(.footnote).foregroundStyle(.secondary)
                    }
                }.navigationTitle("我的").navigationBarTitleDisplayMode(.inline)
                    .sheet(isPresented:$showSettings) {settings}
            }.tabItem {Label("我的",systemImage:"person.crop.circle")}
        }
        .sheet(isPresented:$showLearned) {learnedPage}
        .tint(.accentColor)
        .background(GlobalFeedbackHost(model:model).frame(width:0,height:0))
        .background(GlobalDictionaryHost(model:model).frame(width:0,height:0))
        .fullScreenCover(isPresented:Binding(get:{model.session != nil},set:{_ in})) {LessonScreen(model:model)}
        .task {if CredentialStore.read(account:model.baseURL) != nil {await model.perform {try await model.connect()}}}
    }
    private var welcome: some View {
        VStack(alignment:.leading,spacing:20) {
            Text("把英语说出来").font(.largeTitle.bold())
            Text("先理解一种说法，再换成自己的内容，最后完成一次真实交流任务。")
            #if DEBUG
            TextField("后端服务地址",text:$model.baseURL).textInputAutocapitalization(.never).autocorrectionDisabled().keyboardType(.URL)
                .textFieldStyle(.roundedBorder).accessibilityIdentifier("backendURL")
            #endif
            Picker("目前熟悉的难度",selection:$model.stage) {ForEach(["Pre-A1","A1","A2","B1","B2","C1","C2"],id:\.self) {Text($0)}}
            Text("难度只是起点参考，实际表现会影响后续推荐。").font(.footnote).foregroundStyle(.secondary)
            TextField("感兴趣的交流主题",text:$model.context).textFieldStyle(.roundedBorder)
            Button("开始建立学习记录") {Task {await model.perform {try await model.connect(create:true)}}}
                .buttonStyle(.borderedProminent).disabled(model.busy).accessibilityIdentifier("createAccount")
        }
    }
    private var home:some View {
        VStack(alignment:.leading,spacing:20) {
            Text(model.recommendations?.recommended == nil ? "继续学习":"今日复习").font(.subheadline).foregroundStyle(.secondary)
            VStack(alignment:.leading,spacing:12) {
                if let review=model.recommendations?.recommended {
                    LookupText(review.title).font(.headline)
                    Text("\(review.taskCount ?? 1) 个任务 · 约 \(review.minutes) 分钟").font(.subheadline).foregroundStyle(.secondary)
                    Button {Task {await model.perform {try await model.generate(review:review)}}} label:{Text("开始复习").font(.headline).foregroundStyle(.white).frame(maxWidth:.infinity,minHeight:50).background(Color.accentColor,in:RoundedRectangle(cornerRadius:12))}.buttonStyle(.plain).disabled(model.busy).accessibilityIdentifier("startReview")
                } else {
                    LookupText(model.recommendations?.nextLearning?.title ?? "练好一个交流目标").font(.headline)
                    Text("约 \(model.recommendations?.nextLearning?.minutes ?? 10) 分钟").font(.subheadline).foregroundStyle(.secondary)
                    Button {Task {await model.perform {try await model.continueCourse()}}} label:{Text("继续学习").font(.headline).foregroundStyle(.white).frame(maxWidth:.infinity,minHeight:50).background(Color.accentColor,in:RoundedRectangle(cornerRadius:12))}.buttonStyle(.plain).disabled(model.busy).accessibilityIdentifier("startLearning")
                }
            }.frame(maxWidth:.infinity,alignment:.leading).padding(18).background(Color(uiColor:.secondarySystemGroupedBackground),in:RoundedRectangle(cornerRadius:16))
            if model.recommendations?.recommended != nil {
                Text("继续学习").font(.subheadline).foregroundStyle(.secondary).padding(.top,4)
                Button {Task {await model.perform {try await model.continueCourse()}}} label: {
                    HStack(spacing:14) {Image(systemName:"book").font(.system(size:26)).foregroundStyle(Color.accentColor);LookupText(model.recommendations?.nextLearning?.title ?? "继续学习").font(.headline).foregroundStyle(.primary);Spacer();Image(systemName:"chevron.right").foregroundStyle(.secondary)}.frame(maxWidth:.infinity,minHeight:44).padding(18).background(Color(uiColor:.secondarySystemGroupedBackground),in:RoundedRectangle(cornerRadius:16))
                }.buttonStyle(.plain).disabled(model.busy).accessibilityIdentifier("startLearning")
            }
            if model.health?.mode=="fixture" {Text("当前为测试模式，不更新真实能力。").font(.footnote).foregroundStyle(.secondary)}
            if let job=model.job,!job.terminal {
                Text(job.label).accessibilityIdentifier("jobState")
                Button("继续查看生成结果") {Task {await model.perform {try await model.poll()}}}.disabled(model.busy)
                Button("取消生成",role:.destructive) {Task {do {try await model.cancelJob()} catch {model.error=error.localizedDescription}}}
            }
        }
    }
    private var learnedPage:some View {
        NavigationStack {
            List {
                if model.recommendations?.learned.isEmpty != false {Text("完成练习后，可在这里选择已学目标再练。").foregroundStyle(.secondary)}
                ForEach(model.recommendations?.learned ?? []) {review in
                    VStack(alignment:.leading,spacing:12) {
                        LookupText(review.title)
                        Text("约 \(review.minutes) 分钟 · 先尝试，再按需补练").font(.footnote).foregroundStyle(.secondary)
                        Button("练一次") {showLearned=false;Task {await model.perform {try await model.generate(review:review)}}}.frame(minHeight:44).disabled(model.busy)
                    }
                }
            }.navigationTitle("已学内容").navigationBarTitleDisplayMode(.inline)
                .toolbar {ToolbarItem(placement:.cancellationAction) {Button("关闭") {showLearned=false}}}
        }
    }
    private var settings: some View {
        NavigationStack {
            Form {
                #if DEBUG
                TextField("服务地址",text:$model.baseURL).textInputAutocapitalization(.never).keyboardType(.URL)
                #endif
                Picker("难度参考",selection:$model.stage) {ForEach(["Pre-A1","A1","A2","B1","B2","C1","C2"],id:\.self) {Text($0)}}
                TextField("主题",text:$model.context)
                Button("连接并刷新") {Task {await model.perform {try await model.connect(savePreferences:true)};if model.error == nil {showSettings=false}}}
                Link("隐私政策",destination:URL(string:"https://saywith.zhiyuanv.com/legal/privacy")!)
                Link("用户协议",destination:URL(string:"https://saywith.zhiyuanv.com/legal/terms")!)
                Button("意见反馈") {NotificationCenter.default.post(name:Notification.Name("OpenSayWithFeedback"),object:nil)}
                Link("联系支持",destination:URL(string:"https://saywith.zhiyuanv.com/contact.html")!)
                Text("模型与语音服务由后端管理。录音将发送给后端和字节语音服务用于识别。")
                    .font(.footnote).foregroundStyle(.secondary)
            }.navigationTitle("学习设置")
                .toolbar {ToolbarItem(placement:.cancellationAction) {Button("关闭") {showSettings=false}}}
        }
    }
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
