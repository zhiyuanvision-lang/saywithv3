import SwiftUI

@main
struct SayWithApp: App {
    @State private var model=LearningModel()
    init() {WeChatAuth.shared.registerIfConfigured()}
    var body: some Scene {WindowGroup {RootView(model:model)}}
}

struct RootView: View {
    @Bindable var model: LearningModel
    @State private var showSettings=false
    @State private var showLearned=false
    @State private var confirmLogout=false
    @State private var logoutError:String?
    @ScaledMetric(relativeTo:.title2) private var homeTitleSize:CGFloat=26
    @Environment(\.scenePhase) private var scenePhase
    var body: some View {
        Group {
            if model.restoringLogin {ProgressView("正在恢复登录…")}
            else if model.hasAccount {accountTabs}
            else {LoginView(model:model)}
        }
        .task {
            #if DEBUG
            if ProcessInfo.processInfo.arguments.contains("--ui-test-anonymous") {
                await model.perform {try await model.connect(create:CredentialStore.read(account:model.baseURL)==nil)}
                model.restoringLogin=false
            } else {await model.restoreLogin()}
            #else
            await model.restoreLogin()
            #endif
        }
        .onOpenURL {WeChatAuth.shared.handleOpen(url:$0)}
        .onContinueUserActivity(NSUserActivityTypeBrowsingWeb) {WeChatAuth.shared.handleUniversalLink($0)}
        .onReceive(NotificationCenter.default.publisher(for:.loginExpired)) {notification in
            if notification.userInfo?["baseURL"] as? String == model.baseURL {model.loginExpired()}
        }
    }
    private var accountTabs:some View {
        TabView {
            NavigationStack {
                VStack(alignment:.leading,spacing:0) {
                    Text("学习").font(.system(size:homeTitleSize,weight:.semibold))
                        .padding(.horizontal,20).padding(.top,12).padding(.bottom,2)
                        .accessibilityIdentifier("homeTitle").accessibilityAddTraits(.isHeader)
                ScrollView {
                    VStack(alignment:.leading,spacing:24) {
                        home
                        if let error=model.error {
                            Text(error).foregroundStyle(.red).accessibilityIdentifier("errorMessage")
                            if model.hasPendingInput {Button("重试发送") {Task {await model.perform {try await model.retryInput()}}}}
                        }
                        if model.busy && model.job?.terminal != false {ProgressView("正在处理…").accessibilityIdentifier("busyIndicator")}
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
            NavigationStack {minePage.sheet(isPresented:$showSettings) {settings}}
                .tabItem {Label("我的",systemImage:"person.crop.circle")}

        }
        .sheet(isPresented:$showLearned) {learnedPage}
        .tint(.accentColor)
        .background(GlobalFeedbackHost(model:model).frame(width:0,height:0))
        .background(GlobalDictionaryHost(model:model).frame(width:0,height:0))
        .fullScreenCover(isPresented:Binding(get:{model.session != nil},set:{_ in})) {LessonScreen(model:model)}
        .confirmationDialog("退出当前账号？",isPresented:$confirmLogout,titleVisibility:.visible) {
            Button("退出登录",role:.destructive) {Task {await model.perform {try await model.signOut()};logoutError=model.error}}.accessibilityIdentifier("confirmSignOut")
            Button("取消",role:.cancel) {}
        } message:{Text("学习记录会保留，重新登录后可以继续。")}
        .alert("退出登录未完成",isPresented:Binding(get:{logoutError != nil},set:{if !$0 {logoutError=nil}})) {
            Button("知道了",role:.cancel) {logoutError=nil}
        } message:{Text(logoutError ?? "")}
    }
    private var minePage:some View {
        ScrollView {
            VStack(alignment:.leading,spacing:20) {
                HStack {
                    Text("我的").font(.system(size:homeTitleSize,weight:.semibold)).accessibilityAddTraits(.isHeader)
                    Spacer()
                }
                HStack(spacing:14) {
                    Text(String(model.displayName.prefix(1))).font(.title2.weight(.semibold))
                        .foregroundStyle(Color.accentColor).frame(width:56,height:56)
                        .background(Color.accentColor.opacity(0.10),in:Circle()).accessibilityHidden(true)
                    VStack(alignment:.leading,spacing:7) {
                        Text(model.displayName).font(.title3.weight(.semibold)).lineLimit(2)
                        Text(model.maskedPhone.isEmpty ? "学习账号":model.maskedPhone).font(.subheadline).foregroundStyle(.secondary)
                    }
                    Spacer(minLength:4)
                    Text(model.stage).font(.subheadline.weight(.medium)).foregroundStyle(Color.accentColor)
                        .padding(.horizontal,10).padding(.vertical,6).background(Color.accentColor.opacity(0.08),in:Capsule())
                        .accessibilityLabel("难度参考 \(model.stage)")
                }.padding(18).frame(maxWidth:.infinity,alignment:.leading)
                    .background(Color(uiColor:.secondarySystemGroupedBackground),in:RoundedRectangle(cornerRadius:18))
                NavigationLink {NotebookPage(model:model).toolbar(.visible,for:.navigationBar)} label:{
                    HStack(spacing:14) {
                        Image(systemName:"bookmark.fill").font(.system(size:23)).foregroundStyle(Color.accentColor)
                            .frame(width:44,height:44).background(Color.accentColor.opacity(0.10),in:RoundedRectangle(cornerRadius:12))
                        VStack(alignment:.leading,spacing:6) {
                            Text("生词本").font(.headline).foregroundStyle(.primary)
                            Text("收藏词语，在课程中练习").font(.subheadline).foregroundStyle(.secondary)
                        }
                        Spacer(minLength:8)
                        Image(systemName:"chevron.right").font(.system(size:13,weight:.semibold)).foregroundStyle(.tertiary)
                    }.padding(18).frame(maxWidth:.infinity,alignment:.leading)
                        .background(Color(uiColor:.secondarySystemGroupedBackground),in:RoundedRectangle(cornerRadius:18))
                }.buttonStyle(.plain).accessibilityIdentifier("notebookEntry")
                VStack(spacing:0) {
                    Button {showSettings=true} label:{mineRow("学习设置",symbol:"slider.horizontal.3")}.accessibilityIdentifier("mineSettings")
                    Divider().padding(.leading,62)
                    Button {NotificationCenter.default.post(name:Notification.Name("OpenSayWithFeedback"),object:nil)} label:{mineRow("意见反馈",symbol:"bubble.left.and.bubble.right")}.accessibilityIdentifier("mineFeedbackEntry")
                    Divider().padding(.leading,62)
                    Link(destination:URL(string:"https://saywith.zhiyuanv.com/contact.html")!) {mineRow("联系支持",symbol:"lifepreserver")}
                }.buttonStyle(.plain).background(Color(uiColor:.secondarySystemGroupedBackground),in:RoundedRectangle(cornerRadius:18))
                Button("退出登录",role:.destructive) {confirmLogout=true}
                    .font(.body).frame(maxWidth:.infinity,minHeight:50)
                    .background(Color(uiColor:.secondarySystemGroupedBackground),in:RoundedRectangle(cornerRadius:16))
                    .disabled(model.busy).accessibilityIdentifier("signOut")
                VStack(spacing:4) {
                    HStack(spacing:8) {
                        Link("用户协议",destination:URL(string:"https://saywith.zhiyuanv.com/legal/terms")!)
                            .frame(minHeight:44).accessibilityIdentifier("mineTerms")
                        Text("·").accessibilityHidden(true)
                        Link("隐私政策",destination:URL(string:"https://saywith.zhiyuanv.com/legal/privacy")!)
                            .frame(minHeight:44).accessibilityIdentifier("minePrivacy")
                    }.font(.footnote).foregroundStyle(.secondary).tint(.secondary)
                    Text("版本 \(Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "")")
                        .font(.caption2).foregroundStyle(.secondary).accessibilityIdentifier("appVersion")
                    Link("京ICP备2024066384号-6A",destination:URL(string:"https://beian.miit.gov.cn/")!)
                        .font(.caption2).foregroundStyle(.secondary).tint(.secondary)
                        .frame(minHeight:44).accessibilityIdentifier("mineFiling")
                }.frame(maxWidth:.infinity).padding(.top,-12).padding(.bottom,8)
            }.padding(.horizontal,20).padding(.top,8).padding(.bottom,20)
        }.background(Color(uiColor:.systemGroupedBackground)).toolbar(.hidden,for:.navigationBar)
    }
    private func mineRow(_ title:String,symbol:String)->some View {
        HStack(spacing:14) {
            Image(systemName:symbol).font(.system(size:19)).foregroundStyle(.secondary).frame(width:26)
            Text(title).font(.body).foregroundStyle(.primary)
            Spacer(minLength:8)
            Image(systemName:"chevron.right").font(.system(size:12,weight:.semibold)).foregroundStyle(.tertiary)
        }.padding(.horizontal,18).frame(minHeight:54).contentShape(Rectangle())
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
                VStack(alignment:.leading,spacing:12) {
                    HStack {ProgressView();Text(job.label).font(.headline).accessibilityIdentifier("jobState")}
                    if let progress=job.progress,let total=progress["audio_total"],total>0 {
                        if job.state == "generating_audio" {Text("声音已准备 \(progress["audio_ready"] ?? 0) / \(total)").font(.subheadline).foregroundStyle(.secondary)}
                        if job.state == "checking_audio" {Text("声音已检查 \(progress["audio_checked"] ?? 0) / \(total)").font(.subheadline).foregroundStyle(.secondary)}
                    }
                    if let created=job.createdAt {
                        TimelineView(.periodic(from:.now,by:1)) {context in
                            let seconds=max(0,Int(context.date.timeIntervalSince1970-created))
                            Text("已等待 \(seconds) 秒").font(.footnote).foregroundStyle(.secondary).monospacedDigit()
                        }
                    }
                    Text((job.textRevisions ?? 0)>0 ? "正在调整内容，让练习更符合本次目标。完成后会自动打开。":"正在准备适合你的练习和声音，完成后会自动打开。")
                        .font(.footnote).foregroundStyle(.secondary)
                    if !model.busy {Button("继续查看生成结果") {Task {await model.perform {try await model.poll()}}}}
                    Button("取消生成",role:.destructive) {Task {do {try await model.cancelJob()} catch {model.error=error.localizedDescription}}}
                }.padding(18).frame(maxWidth:.infinity,alignment:.leading)
                    .background(Color(uiColor:.secondarySystemGroupedBackground),in:RoundedRectangle(cornerRadius:16))
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
