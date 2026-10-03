import SwiftUI
import AuthenticationServices

struct LoginView:View {
    @Bindable var model:LearningModel
    @State private var phone=""
    @State private var code=""
    @State private var agreed=false
    @State private var sending=false
    @State private var authorizing=false
    @State private var retryDates:[String:Date]=[:]
    @State private var methods:LoginMethods?
    @State private var methodsError:String?
    @State private var wechatInstalled=false
    private enum Field:Hashable {case phone,code}
    private enum Action {case sendCode,sms,wechat,apple}
    @State private var pendingAction:Action?
    @State private var showingConsent=false
    @State private var continueAfterConsent=false
    @FocusState private var focusedField:Field?
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.scenePhase) private var scenePhase
    private var validPhone:Bool {phone.range(of:"^1[3-9][0-9]{9}$",options:.regularExpression) != nil}
    private var consent:some View {
        HStack(alignment:.center,spacing:0) {
            Button {agreed.toggle()} label:{
                Image(systemName:agreed ? "checkmark.circle.fill":"circle")
                    .font(.system(size:20)).foregroundStyle(agreed ? Color.accentColor:Color.secondary)
                    .frame(width:44,height:44)
            }.buttonStyle(.plain).accessibilityLabel("同意用户协议和隐私政策")
                .accessibilityValue(agreed ? "已勾选":"未勾选").accessibilityIdentifier("loginConsent")
            Text("同意[用户协议](https://saywith.zhiyuanv.com/legal/terms)和[隐私政策](https://saywith.zhiyuanv.com/legal/privacy)")
                .font(.footnote).foregroundStyle(.secondary).tint(.accentColor)
                .fixedSize(horizontal:false,vertical:true)
            Spacer(minLength:0)
        }
    }
    var body:some View {
        NavigationStack {
            ScrollView {
                VStack(alignment:.leading,spacing:0) {
                    HStack(spacing:12) {
                        Image("BrandMark").resizable().scaledToFit().frame(width:44,height:44)
                            .clipShape(RoundedRectangle(cornerRadius:12)).accessibilityHidden(true)
                        Text("背单词练口语").font(.title3.weight(.semibold))
                    }.padding(.bottom,32)
                    Text("登录账号").font(.title.weight(.bold)).accessibilityAddTraits(.isHeader)
                    Text("登录后，接着学、继续练。")
                        .font(.subheadline).foregroundStyle(.secondary).padding(.top,8).padding(.bottom,28)
                    smsForm
                    consent.padding(.top,8).padding(.bottom,12)
                    Button {
                        request(.sms)
                    } label:{
                        HStack(spacing:10) {
                            if model.busy {ProgressView().tint(.white)}
                            Text(model.busy ? "正在登录":"登录").font(.headline)
                        }.foregroundStyle(.white).frame(maxWidth:.infinity,minHeight:52)
                            .background(Color.accentColor.opacity(model.busy || sending || authorizing ? 0.45:1),in:RoundedRectangle(cornerRadius:14))
                    }.buttonStyle(.plain).disabled(model.busy || sending || authorizing || methods?.sms == false).accessibilityIdentifier("smsLoginSubmit")
                    Text("首次登录将自动创建账号").font(.caption).foregroundStyle(.secondary)
                        .frame(maxWidth:.infinity).padding(.top,12)
                    if let error=model.error {Text(error).font(.footnote).foregroundStyle(.red).padding(.top,12).accessibilityIdentifier("loginError")}
                    otherMethods.padding(.top,28)
                    if CredentialStore.login(account:model.baseURL) != nil {
                        Button("恢复上次登录") {Task {await model.restoreLogin()}}.font(.subheadline).disabled(model.busy).padding(.top,16)
                    }
                    if let methodsError {
                        Text(methodsError).font(.footnote).foregroundStyle(.secondary).padding(.top,16)
                        Button("重新连接") {Task {await loadMethods()}}.font(.subheadline).frame(minHeight:44)
                    }
                    #if DEBUG
                    DisclosureGroup("开发设置") {
                        TextField("后端服务地址",text:$model.baseURL).textInputAutocapitalization(.never).autocorrectionDisabled().keyboardType(.URL)
                            .textFieldStyle(.roundedBorder).accessibilityIdentifier("backendURL")
                    }.font(.footnote).foregroundStyle(.secondary).padding(.top,24)
                    #endif
                }.padding(.horizontal,24).padding(.top,32).padding(.bottom,24)
                    .frame(maxWidth:480).frame(maxWidth:.infinity)
            }.scrollDismissesKeyboard(.interactively)
                .background(Color(uiColor:.systemGroupedBackground).ignoresSafeArea())
                .toolbar(.hidden,for:.navigationBar)
                .toolbar {ToolbarItemGroup(placement:.keyboard) {Spacer();Button("完成") {focusedField=nil}}}
        }.sheet(isPresented:$showingConsent,onDismiss:{
            let action=pendingAction
            pendingAction=nil
            if continueAfterConsent,let action {continueAfterConsent=false;execute(action)}
        }) {
            VStack(spacing:20) {
                Text("请阅读并同意").font(.title3.bold()).accessibilityAddTraits(.isHeader)
                Text("继续前，请阅读并同意[用户协议](https://saywith.zhiyuanv.com/legal/terms)和[隐私政策](https://saywith.zhiyuanv.com/legal/privacy)。")
                    .font(.body).tint(.accentColor).multilineTextAlignment(.center)
                Button("同意并继续") {agreed=true;continueAfterConsent=true;showingConsent=false}
                    .buttonStyle(.borderedProminent).controlSize(.large).accessibilityIdentifier("agreeAndContinue")
                Button("暂不同意") {continueAfterConsent=false;showingConsent=false}
                    .frame(minHeight:44).accessibilityIdentifier("cancelConsent")
            }.padding(24).presentationDetents([.height(300)])
        }.task {wechatInstalled=showWeChat;await loadMethods()}
            .onChange(of:scenePhase) {_,phase in if phase == .active {wechatInstalled=showWeChat}}
    }
    private var smsForm:some View {
        VStack(spacing:0) {
            HStack(spacing:12) {
                Text("+86").font(.body).foregroundStyle(.secondary)
                Rectangle().fill(Color(uiColor:.separator)).frame(width:0.5,height:20)
                TextField("手机号",text:$phone).keyboardType(.phonePad).textContentType(.telephoneNumber)
                    .focused($focusedField,equals:.phone).accessibilityLabel("手机号").accessibilityIdentifier("loginPhone")
                if !phone.isEmpty {Button {phone=""} label:{Image(systemName:"xmark.circle.fill").foregroundStyle(.tertiary).frame(width:44,height:44)}.accessibilityLabel("清空手机号")}
            }.frame(minHeight:58).padding(.leading,18).padding(.trailing,6)
            Divider().padding(.leading,18)
            HStack(spacing:8) {
                TextField("6 位验证码",text:$code).keyboardType(.numberPad).textContentType(.oneTimeCode)
                    .focused($focusedField,equals:.code).accessibilityLabel("验证码").accessibilityIdentifier("loginCode")
                TimelineView(.periodic(from:.now,by:1)) {timeline in
                    let remaining=max(0,Int(ceil((retryDates[phone] ?? .distantPast).timeIntervalSince(timeline.date))))
                    Button {request(.sendCode)} label:{
                        Group {
                            if sending {ProgressView().controlSize(.small)}
                            else {Text(remaining>0 ? "\(remaining) 秒后重试":"获取验证码").font(.subheadline.weight(.medium))}
                        }.frame(minWidth:104,minHeight:44)
                    }.disabled(sending || model.busy || remaining>0 || methods?.sms == false)
                        .accessibilityLabel("获取验证码").accessibilityIdentifier("sendLoginCode")
                }
            }.frame(minHeight:58).padding(.leading,18).padding(.trailing,10)
        }.background(Color(uiColor:.secondarySystemGroupedBackground),in:RoundedRectangle(cornerRadius:16))
            .onChange(of:phone) {_,new in phone=String(new.filter {$0.isASCII && $0.isNumber}.prefix(11));code=""}
            .onChange(of:code) {_,new in code=String(new.filter {$0.isASCII && $0.isNumber}.prefix(6))}
    }
    private var otherMethods:some View {
        VStack(spacing:16) {
            HStack(spacing:12) {Rectangle().frame(height:0.5);Text("其他方式登录").fixedSize();Rectangle().frame(height:0.5)}
                .font(.caption).foregroundStyle(.tertiary)
            HStack(alignment:.top,spacing:48) {
                if wechatInstalled && methods?.wechat != false {
                    VStack(spacing:8) {
                        Button {request(.wechat)} label:{
                            Image(systemName:"bubble.left.and.bubble.right.fill").font(.system(size:24))
                                .foregroundStyle(.white).frame(width:52,height:52).background(Color.green,in:Circle())
                        }.buttonStyle(.plain).disabled(model.busy || sending || authorizing)
                            .accessibilityLabel("微信登录").accessibilityIdentifier("wechatLogin")
                        Text("微信").font(.caption).foregroundStyle(.secondary)
                    }
                }
                if methods?.apple != false {
                    VStack(spacing:8) {
                        Button {request(.apple)} label:{
                            Image(systemName:"apple.logo").font(.system(size:26))
                                .foregroundStyle(colorScheme == .dark ? Color.black:Color.white)
                                .frame(width:52,height:52)
                                .background(colorScheme == .dark ? Color.white:Color.black,in:Circle())
                        }.buttonStyle(.plain).disabled(model.busy || sending || authorizing)
                            .accessibilityLabel("通过 Apple 登录").accessibilityIdentifier("appleLogin")
                        Text("Apple").font(.caption).foregroundStyle(.secondary)
                    }
                }
            }.frame(maxWidth:.infinity)
        }
    }
    private func request(_ action:Action) {
        guard !model.busy,!sending,!authorizing else {return}
        model.error=nil
        if action == .sendCode || action == .sms {
            guard validPhone else {model.error="请输入正确的 11 位手机号。";focusedField = .phone;return}
            if action == .sms && code.count != 6 {model.error="请输入 6 位验证码。";focusedField = .code;return}
        }
        focusedField=nil
        guard agreed else {pendingAction=action;continueAfterConsent=false;showingConsent=true;return}
        execute(action)
    }
    private func execute(_ action:Action) {
        switch action {
        case .sendCode:sendCode()
        case .sms:
            let target=phone,verification=code
            Task {await model.perform {try await model.login(path:"v1/auth/sms/login",body:["phone":.string(target),"code":.string(verification)])}}
        case .wechat:
            Task {await model.perform {
                let code=try await WeChatAuth.shared.requestCode()
                try await model.login(path:"v1/auth/wechat",body:["code":.string(code)])
            }}
        case .apple:
            authorizing=true
            Task {
                defer {authorizing=false}
                do {
                    let identity=try await AppleAuth.requestIdentity()
                    await model.perform {try await model.login(path:"v1/auth/apple",body:["identity_token":.string(identity.identityToken),"full_name":.string(identity.fullName)])}
                } catch {
                    if (error as? ASAuthorizationError)?.code != .canceled {model.error=error.localizedDescription}
                }
            }
        }
    }
    private func sendCode() {
        guard validPhone,agreed,!sending,!model.busy else {return}
        let target=phone
        sending=true;model.error=nil
        Task {
            defer {sending=false}
            do {
                let client=try model.loginClient()
                let sent:SMSDelivery=try await client.request("v1/auth/sms/send",method:"POST",body:["phone":.string(target)],auth:false)
                retryDates[target]=Date().addingTimeInterval(TimeInterval(max(1,sent.retryAfter)))
                if phone==target {focusedField = .code}
            } catch {model.error=error.localizedDescription}
        }
    }
    private var showWeChat:Bool {
        #if DEBUG
        if ProcessInfo.processInfo.arguments.contains("--ui-test-show-wechat") {return true}
        #endif
        return WeChatAuth.shared.isAvailable
    }
    private func loadMethods() async {
        do {methods=try await model.loginClient().request("v1/auth/methods",auth:false);methodsError=nil}
        catch {methodsError="暂时无法获取登录方式，请检查网络后重试。"}
    }
}
