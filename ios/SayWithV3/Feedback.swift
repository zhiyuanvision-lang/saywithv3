import SwiftUI
import PhotosUI
import UIKit
import CryptoKit

private let feedbackAccent=Color(red:0.07,green:0.68,blue:0.61)

struct FeedbackMessage:Decodable,Sendable,Identifiable {
    let id:String;let senderType:String;let senderName:String;let content:String
    let images:[String]?;let createdAt:String
}
struct FeedbackTicket:Decodable,Sendable,Identifiable {
    let id:String;let content:String;let status:String;let createdAt:String
    let reply:String?;let messages:[FeedbackMessage]?;let images:[String]?
    var statusLabel:String {["open":"待处理","replied":"已回复","closed":"已结束"][status] ?? status}
}
struct FeedbackList:Decodable,Sendable {let items:[FeedbackTicket]}
struct FeedbackUpload:Decodable,Sendable {let url:String}

extension LearningModel {
    func feedbackClient() async throws -> API {
        try authenticatedClient()
    }
}

struct FeedbackComposer:View {
    var model:LearningModel
    let onClose:()->Void
    @Environment(\.scenePhase) private var scenePhase
    @State private var category="bug"
    @State private var content=""
    @State private var contact=""
    @State private var requestID=UUID().uuidString
    @State private var images:[Data]=[]
    @State private var picked:[PhotosPickerItem]=[]
    @State private var mine:[FeedbackTicket]=[]
    @State private var busy=false
    @State private var error:String?
    @State private var notice:String?
    @State private var restored=false
    @State private var zoomImage:Data?
    private let categories=[("bug","功能异常 / 报错"),("account","账号 / 登录"),("vocab","背单词"),("speak","口语练习"),("suggestion","建议"),("other","其他")]
    private var draftURL:URL {
        let scope=UUID(uuidString:model.profile?.userId ?? "")?.uuidString ?? "visitor"
        let directory=URL.documentsDirectory.appendingPathComponent("feedback-drafts",isDirectory:true)
        try? FileManager.default.createDirectory(at:directory,withIntermediateDirectories:true)
        return directory.appendingPathComponent(SHA256.hash(data:Data(model.baseURL.utf8)).map {String(format:"%02x",$0)}.joined().prefix(16)+"-"+scope+".json")
    }
    var body:some View {
        Form {
            Section {
                ScrollView(.horizontal,showsIndicators:false) {
                    HStack(spacing:8) {ForEach(categories,id:\.0) {key,title in
                        Button {category=key} label:{Text(title).font(.subheadline.weight(.semibold)).fixedSize().padding(.horizontal,12).padding(.vertical,6).background(category==key ? feedbackAccent.opacity(0.16):Color(uiColor:.tertiarySystemFill),in:Capsule()).foregroundStyle(category==key ? feedbackAccent:Color.primary)}.buttonStyle(.plain).accessibilityAddTraits(category==key ? .isSelected:[])
                    }}
                }
                if !images.isEmpty {ScrollView(.horizontal) {HStack {ForEach(images.indices,id:\.self) {index in
                    VStack {if let image=UIImage(data:images[index]) {Button {zoomImage=images[index]} label:{Image(uiImage:image).resizable().scaledToFill().frame(width:72,height:72).clipped().clipShape(RoundedRectangle(cornerRadius:8))}.accessibilityLabel("放大反馈图片")};Button("删除") {images.remove(at:index)}.frame(minHeight:44)}
                }}}}
                if images.count<4 {PhotosPicker(selection:$picked,maxSelectionCount:4-images.count,matching:.images) {Label("添加图片",systemImage:"photo.on.rectangle").frame(minHeight:44)}}
                TextField("请描述你遇到的问题或建议",text:$content,axis:.vertical).lineLimit(4...16).accessibilityIdentifier("feedbackContent")
                TextField("联系方式（选填）",text:$contact).accessibilityIdentifier("feedbackContact")
                if let error {Text(error).foregroundStyle(.red).accessibilityIdentifier("feedbackError")}
                if let notice {Text(notice).foregroundStyle(.secondary).accessibilityIdentifier("feedbackSubmitted")}
            } header:{Text("提交反馈")} footer:{Text("一般建议或非紧急问题我们会尽快处理。最多 4 张图，点缩略图可放大。")}
            Section("我的反馈") {
                if mine.isEmpty {Text("还没有反馈记录").foregroundStyle(.secondary)}
                ForEach(mine) {ticket in NavigationLink {FeedbackThread(model:model,ticket:ticket)} label:{VStack(alignment:.leading,spacing:6) {HStack {Text(ticket.statusLabel).font(.caption).foregroundStyle(.secondary);Spacer();Text(String(ticket.createdAt.replacingOccurrences(of:"T",with:" ").prefix(16))).font(.caption).foregroundStyle(.tertiary)};LookupText(ticket.content).lineLimit(2);if let reply=ticket.reply,!reply.isEmpty {LookupText("官方回复："+reply).font(.footnote).foregroundStyle(.secondary)}}}}
            }
        }.disabled(busy).navigationTitle("意见反馈").navigationBarTitleDisplayMode(.inline).tint(feedbackAccent).scrollDismissesKeyboard(.interactively)
        .toolbar {ToolbarItem(placement:.cancellationAction) {Button("关闭") {save();onClose()}.accessibilityIdentifier("closeFeedback")}}
        .safeAreaInset(edge:.bottom) {Button {submit()} label:{HStack {if busy {ProgressView()};Text("提交反馈").frame(maxWidth:.infinity,minHeight:44)}}.buttonStyle(.borderedProminent).disabled(busy || (content.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty && images.isEmpty)).accessibilityIdentifier("submitFeedback").padding(.horizontal,20).padding(.vertical,10).background(.regularMaterial)}
        .task {restore();await loadMine()}
        .onChange(of:content) {_,_ in changed()}.onChange(of:contact) {_,_ in changed()}.onChange(of:category) {_,_ in changed()}.onChange(of:images) {_,_ in changed()}
        .onChange(of:scenePhase) {_,phase in if phase != .active {save()}}.onDisappear {save()}
        .onChange(of:picked) {_,items in Task {
            do {for item in items.prefix(4-images.count) {if let data=try await item.loadTransferable(type:Data.self),let image=UIImage(data:data) {
                let scale=min(1,1600/max(image.size.width,image.size.height));let size=CGSize(width:image.size.width*scale,height:image.size.height*scale)
                let format=UIGraphicsImageRendererFormat();format.scale=1
                let resized=UIGraphicsImageRenderer(size:size,format:format).image {_ in image.draw(in:CGRect(origin:.zero,size:size))}
                guard let jpeg=resized.jpegData(compressionQuality:0.75),jpeg.count<=2*1024*1024 else {throw APIError.server("图片太大，请选择其他图片")};images.append(jpeg)
            }};picked=[]} catch {self.error=error.localizedDescription}
        }}
        .sheet(isPresented:Binding(get:{zoomImage != nil},set:{if !$0 {zoomImage=nil}})) {if let data=zoomImage,let image=UIImage(data:data) {NavigationStack {Image(uiImage:image).resizable().scaledToFit().toolbar {ToolbarItem(placement:.cancellationAction) {Button("关闭") {zoomImage=nil}}}}}}
    }
    private func submit() {
        UIApplication.shared.sendAction(#selector(UIResponder.resignFirstResponder),to:nil,from:nil,for:nil)
        busy=true;error=nil;notice=nil;save()
        Task {defer {busy=false};do {
            let api=try await model.feedbackClient();var refs:[JSONValue]=[]
            for image in images {refs.append(.string(try await api.feedbackImage(image).url))}
            let info=Bundle.main.infoDictionary ?? [:]
            let version="\(info["CFBundleShortVersionString"] ?? "") (\(info["CFBundleVersion"] ?? ""))"
            let _:FeedbackTicket=try await api.request("v1/feedback",method:"POST",body:["category":.string(category),"content":.string(content),"contact":.string(contact),"images":.array(refs),"app_version":.string(version)],key:requestID)
            content="";contact="";images=[];requestID=UUID().uuidString;save();notice="提交成功，我们会在这里回复。";await loadMine()
        } catch {self.error=error.localizedDescription}}
    }
    private func loadMine() async {do {let api=try await model.feedbackClient();let list:FeedbackList=try await api.request("v1/feedback/mine");mine=list.items} catch {self.error=error.localizedDescription}}
    private struct Draft:Codable {var category:String;var content:String;var contact:String;var requestID:String;var images:[Data]}
    private func restore() {guard !restored else {return};restored=true;if let data=try? Data(contentsOf:draftURL),let draft=try? JSONDecoder().decode(Draft.self,from:data) {category=draft.category;content=draft.content;contact=draft.contact;requestID=draft.requestID;images=draft.images}}
    private func changed() {if !busy {requestID=UUID().uuidString};save()}
    private func save() {guard restored else {return};if let data=try? JSONEncoder().encode(Draft(category:category,content:content,contact:contact,requestID:requestID,images:images)) {try? data.write(to:draftURL,options:[.atomic,.completeFileProtectionUntilFirstUserAuthentication])}}
}

struct FeedbackThread:View {
    var model:LearningModel
    @State var ticket:FeedbackTicket
    @State private var reply=""
    @State private var busy=false
    @State private var error:String?
    @State private var closeConfirm=false
    @State private var replyID=UUID().uuidString
    @State private var replyImages:[Data]=[]
    @State private var selectedImages:[PhotosPickerItem]=[]
    var body:some View {
        ScrollView {
            VStack(alignment:.leading,spacing:20) {
                ForEach(ticket.messages ?? []) {message in
                    VStack(alignment:.leading,spacing:8) {Text(message.senderType=="support" ? "小帆团队":"我").font(.caption).foregroundStyle(.secondary);LookupText(message.content);ForEach(message.images ?? [],id:\.self) {ref in if let url=URL(string:ref) {AsyncImage(url:url) {image in image.resizable().scaledToFit()} placeholder:{ProgressView()}.frame(maxHeight:220)}}}.padding(14).frame(maxWidth:.infinity,alignment:.leading).background(Color(uiColor:.secondarySystemGroupedBackground),in:RoundedRectangle(cornerRadius:12))
                }
                Text(ticket.status=="closed" ? "这条反馈已结束":"收到了，我们会在这里回复").font(.footnote).foregroundStyle(.secondary)
                if let error {Text(error).foregroundStyle(.red)}
            }.padding(20)
        }.background(Color(uiColor:.systemGroupedBackground)).navigationTitle("反馈详情").navigationBarTitleDisplayMode(.inline).tint(feedbackAccent)
        .toolbar {if ticket.status != "closed" {Button("结束工单") {closeConfirm=true}.disabled(busy)}}
        .confirmationDialog("结束这条反馈？结束后不能再回复。",isPresented:$closeConfirm,titleVisibility:.visible) {Button("结束工单",role:.destructive) {operate(close:true)}}
        .safeAreaInset(edge:.bottom) {if ticket.status != "closed" {VStack(spacing:4) {if !replyImages.isEmpty {Text("已添加 \(replyImages.count) 张图片").font(.caption)};HStack {PhotosPicker(selection:$selectedImages,maxSelectionCount:max(1,4-replyImages.count),matching:.images) {Image(systemName:"plus.circle").frame(width:44,height:44)}.disabled(replyImages.count>=4);TextField("回复客服…",text:$reply,axis:.vertical).lineLimit(1...5).padding(10).background(Color(uiColor:.secondarySystemFill),in:Capsule());Button("发送") {operate(close:false)}.frame(minHeight:44).disabled(busy || (reply.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty && replyImages.isEmpty))}}.padding(12).background(Color(uiColor:.systemBackground))}}
        .task {await refresh()}.refreshable {await refresh()}
        .onChange(of:selectedImages) {_,items in Task {for item in items.prefix(4-replyImages.count) {if let data=try? await item.loadTransferable(type:Data.self),let image=UIImage(data:data),let jpeg=image.jpegData(compressionQuality:0.6),jpeg.count<=2*1024*1024 {replyImages.append(jpeg)} else {error="图片太大或无法读取，请重新选择"}};selectedImages=[]}}
        .onChange(of:reply) {_,_ in if !busy {replyID=UUID().uuidString}}
        .onChange(of:replyImages) {_,_ in if !busy {replyID=UUID().uuidString}}

    }
    private func refresh() async {do {let api=try await model.feedbackClient();ticket=try await api.request("v1/feedback/"+ticket.id)} catch {self.error=error.localizedDescription}}
    private func operate(close:Bool) {busy=true;error=nil;Task {defer {busy=false};do {let api=try await model.feedbackClient();var refs:[JSONValue]=[];if !close {for data in replyImages {refs.append(.string(try await api.feedbackImage(data).url))}};ticket=try await api.request("v1/feedback/"+ticket.id+(close ? "/close":"/messages"),method:"POST",body:close ? nil:["content":.string(reply),"images":.array(refs)],key:close ? nil:replyID);reply="";replyImages=[];replyID=UUID().uuidString} catch {self.error=error.localizedDescription}}}
}

/// A separate passthrough window keeps the same draggable entry above tabs and sheets.
struct GlobalFeedbackHost:UIViewRepresentable {
    let model:LearningModel
    func makeUIView(context:Context)->FeedbackAnchor {let view=FeedbackAnchor();view.model=model;return view}
    func updateUIView(_ view:FeedbackAnchor,context:Context) {view.model=model}
}
@MainActor final class FeedbackAnchor:UIView {
    var model:LearningModel?
    private var feedbackWindow:FeedbackWindow?
    override func didMoveToWindow() {
        super.didMoveToWindow()
        guard feedbackWindow==nil,let scene=window?.windowScene,let model else {return}
        let overlay=FeedbackWindow(windowScene:scene)
        overlay.windowLevel = .normal+1
        let controller=FeedbackOrbController(model:model)
        overlay.rootViewController=controller;overlay.isHidden=false;feedbackWindow=overlay
    }
}
@MainActor final class FeedbackWindow:UIWindow {
    override func hitTest(_ point:CGPoint,with event:UIEvent?)->UIView? {
        if rootViewController?.presentedViewController != nil {return super.hitTest(point,with:event)}
        let hit=super.hitTest(point,with:event)
        return hit is UIButton || hit?.superview is UIButton ? hit:nil
    }
}
@MainActor final class FeedbackOrbController:UIViewController,UIAdaptivePresentationControllerDelegate {
    let model:LearningModel
    private let button=UIButton(type:.custom)
    private var start=CGPoint.zero
    private weak var returnWindow:UIWindow?
    init(model:LearningModel) {self.model=model;super.init(nibName:nil,bundle:nil)}
    @available(*,unavailable) required init?(coder:NSCoder) {fatalError()}
    override func viewDidLoad() {
        super.viewDidLoad();view.backgroundColor = .clear
        NotificationCenter.default.addObserver(self,selector:#selector(open),name:Notification.Name("OpenSayWithFeedback"),object:nil)
        button.setImage(UIImage(systemName:"bubble.left.and.bubble.right.fill"),for:.normal)
        button.backgroundColor=UIColor(red:0.07,green:0.68,blue:0.61,alpha:1);button.tintColor = .white
        button.layer.cornerRadius=26;button.layer.shadowOpacity=0.18;button.layer.shadowRadius=8
        button.accessibilityLabel="意见反馈";button.accessibilityHint="拖动可移动位置，轻点打开意见反馈";button.accessibilityIdentifier="feedbackOrb"
        button.addTarget(self,action:#selector(open),for:.touchUpInside)
        button.addGestureRecognizer(UIPanGestureRecognizer(target:self,action:#selector(drag)))
        view.addSubview(button)
    }
    override func viewDidLayoutSubviews() {
        super.viewDidLayoutSubviews()
        let stored=UserDefaults.standard.object(forKey:"feedbackOrbRelativeY") as? Double ?? 0.72
        let x=UserDefaults.standard.object(forKey:"feedbackOrbLeft") as? Bool == true ? 12:view.bounds.width-64
        button.frame=CGRect(x:x,y:max(view.safeAreaInsets.top+8,min(view.bounds.height-view.safeAreaInsets.bottom-90,view.bounds.height*stored)),width:52,height:52)
    }
    @objc private func open() {
        guard presentedViewController==nil else {return}
        NotificationCenter.default.post(name:Notification.Name("PauseSayWithLearning"),object:nil)
        returnWindow=view.window?.windowScene?.windows.first {$0.isKeyWindow && $0 !== view.window}
        let host=UIHostingController(rootView:NavigationStack {FeedbackComposer(model:model,onClose:{[weak self] in self?.closeFeedback()})})
        present(host,animated:true)
        host.presentationController?.delegate=self
        view.window?.makeKey()
    }
    private func closeFeedback() {
        view.window?.endEditing(true)
        dismiss(animated:true) {[weak self] in self?.restoreEntry()}
    }
    func presentationControllerDidDismiss(_ presentationController:UIPresentationController) {restoreEntry()}
    private func restoreEntry() {
        returnWindow?.makeKey();returnWindow=nil
        NotificationCenter.default.post(name:Notification.Name("ResumeSayWithLearning"),object:nil)
    }
    @objc private func drag(_ gesture:UIPanGestureRecognizer) {
        if gesture.state == .began {start=button.center}
        let delta=gesture.translation(in:view)
        button.center=CGPoint(x:max(38,min(view.bounds.width-38,start.x+delta.x)),y:max(view.safeAreaInsets.top+34,min(view.bounds.height-view.safeAreaInsets.bottom-64,start.y+delta.y)))
        if gesture.state == .ended || gesture.state == .cancelled {
            UserDefaults.standard.set(button.center.x<view.bounds.midX,forKey:"feedbackOrbLeft")
            UserDefaults.standard.set((button.frame.minY)/max(1,view.bounds.height),forKey:"feedbackOrbRelativeY")
            view.setNeedsLayout()
        }
    }
}
