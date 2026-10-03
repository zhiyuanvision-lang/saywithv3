import SwiftUI
import UIKit
import AVFoundation

struct DictionaryExample:Codable,Sendable {let text:String;let translationCn:String?;let isGenerated:Bool?}
struct DictionarySense:Codable,Sendable {let pos:String?;let meaningCn:String?;let meaningEn:String?;let pattern:String?;let collocation:String?;let examples:[DictionaryExample]?}
struct DictionaryCollocation:Codable,Sendable {let pattern:String;let meaningCn:String?}
struct DictionaryCard:Codable,Sendable {
    let word:String;let tappedWord:String?;let meaning:String?;let phoneticUk:String?;let phoneticUs:String?
    let audioUk:String?;let audioUs:String?;let generated:Bool?;let senses:[DictionarySense]?
    let collocations:[DictionaryCollocation]?
    var commonCollocations:[String] {
        var result:[String]=[]
        for text in (collocations ?? []).map({$0.pattern})+(senses ?? []).compactMap({$0.collocation}) where !text.isEmpty && !result.contains(text) {result.append(text)}
        return Array(result.prefix(3))
    }
    func filling(from full:DictionaryCard)->DictionaryCard {
        DictionaryCard(word:word,tappedWord:tappedWord,meaning:meaning,phoneticUk:full.phoneticUk ?? phoneticUk,phoneticUs:full.phoneticUs ?? phoneticUs,audioUk:full.audioUk ?? audioUk,audioUs:full.audioUs ?? audioUs,generated:generated,senses:full.senses ?? senses,collocations:full.collocations)
    }
    var shortMeaning:String {senses?.prefix(2).map {($0.pos ?? "")+" "+($0.meaningCn ?? "")}.joined(separator:"；") ?? meaning ?? ""}
}
struct NotebookEntry:Codable,Sendable,Identifiable,Hashable {
    let id:String;let word:String;let createdAt:Double;let card:DictionaryCard;let contexts:[String]
    static func ==(lhs:Self,rhs:Self)->Bool {lhs.id==rhs.id}
    func hash(into hasher:inout Hasher) {hasher.combine(id)}
}
struct NotebookList:Decodable,Sendable {let items:[NotebookEntry]}
struct NotebookRemoved:Decodable,Sendable {let removed:Bool}

@MainActor @Observable final class DictionaryAudio {
    private let speaker=AVSpeechSynthesizer()
    func play(_ word:String,accent:String) {
        speaker.stopSpeaking(at:.immediate)
        try? AVAudioSession.sharedInstance().setCategory(.playback,mode:.spokenAudio)
        try? AVAudioSession.sharedInstance().setActive(true)
        let utterance=AVSpeechUtterance(string:word);utterance.voice=AVSpeechSynthesisVoice(language:accent=="uk" ? "en-GB":"en-US");utterance.rate=AVSpeechUtteranceDefaultSpeechRate;speaker.speak(utterance)
    }
    func stop() {speaker.stopSpeaking(at:.immediate)}
}

extension LearningModel {
    func vocabularyBody(word:String,context:String)->[String:JSONValue] {
        var body:[String:JSONValue]=["word":.string(word),"context":.string(String(context.prefix(1200)))]
        if let current=session,!["finished","abandoned","evaluating"].contains(current.view.phase) {body["session_id"] = .string(current.view.sessionId)}
        return body
    }
    func refreshAfterLookup() async throws {
        let api=try await feedbackClient()
        if let current=session {session=try await api.request("v1/sessions/"+current.view.sessionId)}
        try await refresh()
    }
}

private struct DictionaryHeightPreference:PreferenceKey {
    static let defaultValue:CGFloat=120
    static func reduce(value:inout CGFloat,nextValue:()->CGFloat) {value=nextValue()}
}
private struct WordFramePreference:PreferenceKey {
    static let defaultValue:[Int:CGRect]=[:]
    static func reduce(value:inout [Int:CGRect],nextValue:()->[Int:CGRect]) {value.merge(nextValue(),uniquingKeysWith:{$1})}
}
private struct NewlineKey:LayoutValueKey {static let defaultValue=false}
struct WordFlow:Layout {
    func sizeThatFits(proposal:ProposedViewSize,subviews:Subviews,cache:inout ())->CGSize {arrange(proposal.width ?? 10000,subviews).size}
    func placeSubviews(in bounds:CGRect,proposal:ProposedViewSize,subviews:Subviews,cache:inout ()) {
        let positions=arrange(bounds.width,subviews).points
        for (index,view) in subviews.enumerated() {view.place(at:CGPoint(x:bounds.minX+positions[index].x,y:bounds.minY+positions[index].y),anchor:.topLeading,proposal:.unspecified)}
    }
    private func arrange(_ width:CGFloat,_ views:Subviews)->(size:CGSize,points:[CGPoint]) {
        var x:CGFloat=0,y:CGFloat=0,height:CGFloat=0,maxX:CGFloat=0;var points:[CGPoint]=[]
        for v in views {
            let size=v.sizeThatFits(.unspecified)
            if v[NewlineKey.self] {points.append(CGPoint(x:x,y:y));y+=max(height,size.height);x=0;height=0;continue}
            if x>0 && x+size.width>width {y+=height+2;x=0;height=0}
            points.append(CGPoint(x:x,y:y));x+=size.width;maxX=max(maxX,x);height=max(height,size.height)
        }
        return (CGSize(width:min(width,maxX),height:y+height),points)
    }
}
/// Same word-level interaction as the previous app, preserving natural sentence spacing.
struct LookupText:View {
    let text:String
    @State private var frames:[Int:CGRect]=[:]
    init(_ text:String) {self.text=text}
    static func tokens(_ text:String)->[String] {
        let regex=try! NSRegularExpression(pattern:"[A-Za-z]+(?:['’\\-][A-Za-z]+)*|[^A-Za-z]")
        let ns=text as NSString
        return regex.matches(in:text,range:NSRange(location:0,length:ns.length)).map {ns.substring(with:$0.range)}
    }
    var body:some View {
        WordFlow {
            ForEach(Array(Self.tokens(text).enumerated()),id:\.offset) {index,token in
                if token.first?.isASCII==true && token.first?.isLetter==true {
                    Button {
                        NotificationCenter.default.post(name:Notification.Name("OpenSayWithDictionary"),object:nil,userInfo:["word":token,"context":text,"rect":frames[index] ?? .zero])
                    } label:{Text(token).fixedSize()}.buttonStyle(.plain).accessibilityLabel(token).accessibilityHint("点这个词看释义")
                        .background(GeometryReader {geo in Color.clear.preference(key:WordFramePreference.self,value:[index:geo.frame(in:.global)])})
                } else {Text(token=="\n" ? "":token).fixedSize().layoutValue(key:NewlineKey.self,value:token=="\n")}
            }
        }.onPreferenceChange(WordFramePreference.self) {frames=$0}
    }
}

struct DictionaryPhonetics:View {
    let card:DictionaryCard;let audio:DictionaryAudio
    var body:some View {
        HStack(spacing:14) {
            ForEach([("uk","英",card.phoneticUk ?? ""),("us","美",card.phoneticUs ?? "")],id:\.0) {accent,title,ipa in
                HStack(spacing:3) {Text(title+" "+ipa).font(.caption).foregroundStyle(.secondary);Button {audio.play(card.word,accent:accent)} label:{Image(systemName:"speaker.wave.2.fill").frame(width:44,height:44)}.buttonStyle(.plain).foregroundStyle(Color(red:0.07,green:0.68,blue:0.61)).accessibilityLabel("播放\(title)音 \(card.word)")}
            }
        }.fixedSize(horizontal:false,vertical:true)
    }
}

struct DictionaryGlance:View {
    let model:LearningModel;let word:String;let sentence:String;let close:()->Void
    @State private var card:DictionaryCard?
    @State private var error:String?
    @State private var saved=false
    @State private var saving=false
    @State private var audio=DictionaryAudio()
    var body:some View {
        VStack(alignment:.leading,spacing:10) {
                HStack {Text(card?.word ?? word).font(.title3.bold());Spacer();Button(action:close) {Image(systemName:"xmark.circle.fill").foregroundStyle(.tertiary).frame(width:44,height:44)}.buttonStyle(.plain).accessibilityLabel("关闭查词").accessibilityIdentifier("closeDictionary")}
                if let card {
                    DictionaryPhonetics(card:card,audio:audio)
                    if let tapped=card.tappedWord,tapped.lowercased() != card.word.lowercased() {Text("\(tapped) 的词头：\(card.word)").font(.caption).foregroundStyle(.secondary)}
                    if card.generated==true {Label("AI 释义，仅供参考",systemImage:"sparkles").font(.caption).foregroundStyle(.secondary)}
                    ForEach(Array((card.senses ?? []).prefix(8).enumerated()),id:\.offset) {_,sense in LookupText((sense.pos ?? "")+" "+(sense.meaningCn ?? "")).font(.subheadline)}
                    if (card.senses ?? []).isEmpty {LookupText(card.meaning ?? "暂无释义").font(.subheadline)}
                    if !card.commonCollocations.isEmpty {Text("常用搭配").font(.caption.weight(.semibold)).foregroundStyle(.secondary);ForEach(card.commonCollocations,id:\.self) {LookupText($0).font(.caption)}}
                    Divider()
                    Button {add(card)} label:{Label(saved ? "已在生词本":"加入生词本",systemImage:saved ? "checkmark.circle.fill":"text.badge.plus").font(.subheadline.weight(.semibold)).frame(minHeight:44)}.buttonStyle(.plain).disabled(saved || saving).accessibilityIdentifier("addToNotebook")
                    if saving {ProgressView("正在保存…")}
                } else if error==nil {ProgressView("正在查词…")}
                if let error {Text(error).font(.caption).foregroundStyle(.red);Button("重试查词") {Task {await load()}}}
        }.padding(14).frame(maxWidth:.infinity,alignment:.leading).fixedSize(horizontal:false,vertical:true)
        .background(GeometryReader {geo in Color.clear.preference(key:DictionaryHeightPreference.self,value:geo.size.height)})
        .onPreferenceChange(DictionaryHeightPreference.self) {_ in NotificationCenter.default.post(name:Notification.Name("SayWithDictionaryLayout"),object:nil)}
        .background(Color(uiColor:.systemBackground),in:RoundedRectangle(cornerRadius:16))
        .overlay(RoundedRectangle(cornerRadius:16).stroke(Color.primary.opacity(0.08),lineWidth:0.5))
        .shadow(color:.black.opacity(0.12),radius:16,y:6).tint(Color(red:0.07,green:0.68,blue:0.61))
        .task(id:word) {await load()}.onDisappear {audio.stop()}
    }
    private func load() async {
        error=nil;card=nil;saved=false
        do {
            let api=try await model.feedbackClient()
            let found:DictionaryCard=try await api.request("v1/vocabulary/lookup",method:"POST",body:model.vocabularyBody(word:word,context:sentence));card=found
            try await model.refreshAfterLookup()
            let list:NotebookList=try await api.request("v1/notebook");saved=list.items.contains {$0.word==found.word}
            audio.play(found.word,accent:"us")
            let encoded=found.word.addingPercentEncoding(withAllowedCharacters:.urlQueryAllowed) ?? found.word
            if let full:DictionaryCard=try? await api.request("v1/vocabulary/knowledge?word="+encoded) {card=found.filling(from:full)}
        } catch {self.error="暂时无法加载释义，请重试或选择其他单词。"}
    }
    private func add(_ card:DictionaryCard) {
        saving=true;error=nil
        Task {defer {saving=false};do {let api=try await model.feedbackClient();let _:NotebookEntry=try await api.request("v1/notebook",method:"POST",body:model.vocabularyBody(word:card.word,context:sentence));saved=true;try await model.refreshAfterLookup()} catch {self.error=error.localizedDescription}}
    }
}

/// Lives above every navigation stack, full-screen lesson and feedback/settings sheet.
struct GlobalDictionaryHost:UIViewRepresentable {
    let model:LearningModel
    func makeUIView(context:Context)->DictionaryAnchor {let v=DictionaryAnchor();v.model=model;return v}
    func updateUIView(_ view:DictionaryAnchor,context:Context) {view.model=model}
}
@MainActor final class DictionaryAnchor:UIView {
    var model:LearningModel?
    private var overlay:UIWindow?
    override func didMoveToWindow() {
        super.didMoveToWindow()
        guard overlay==nil,let scene=window?.windowScene,let model else {return}
        let w=DictionaryWindow(windowScene:scene);w.windowLevel = .normal+2;w.rootViewController=DictionaryController(model:model);w.isHidden=false;overlay=w
    }
}
@MainActor final class DictionaryWindow:UIWindow {
    override func hitTest(_ point:CGPoint,with event:UIEvent?)->UIView? {
        guard let controller=rootViewController as? DictionaryController,controller.opened else {return nil}
        return super.hitTest(point,with:event)
    }
}
@MainActor final class DictionaryController:UIViewController,UIGestureRecognizerDelegate {
    let model:LearningModel;var opened=false
    private var card:UIHostingController<DictionaryGlance>?
    private var anchorRect=CGRect.zero
    private let popup=UIScrollView()
    private let plate=UIView()
    init(model:LearningModel) {self.model=model;super.init(nibName:nil,bundle:nil)}
    @available(*,unavailable) required init?(coder:NSCoder) {fatalError()}
    override func viewDidLoad() {super.viewDidLoad();view.backgroundColor = .clear;let tap=UITapGestureRecognizer(target:self,action:#selector(dismissCard));tap.delegate=self;view.addGestureRecognizer(tap);NotificationCenter.default.addObserver(self,selector:#selector(open(_:)),name:Notification.Name("OpenSayWithDictionary"),object:nil);NotificationCenter.default.addObserver(self,selector:#selector(relayout(_:)),name:Notification.Name("SayWithDictionaryLayout"),object:nil)}
    @objc private func open(_ n:Notification) {
        guard let word=n.userInfo?["word"] as? String else {return}
        dismissCard();opened=true;anchorRect=n.userInfo?["rect"] as? CGRect ?? .zero
        NotificationCenter.default.post(name:Notification.Name("PauseSayWithLearning"),object:nil)
        let host=UIHostingController(rootView:DictionaryGlance(model:model,word:word,sentence:n.userInfo?["context"] as? String ?? "",close:{[weak self] in self?.dismissCard()}))
        host.sizingOptions = [.preferredContentSize];host.view.backgroundColor = .clear
        plate.backgroundColor = .clear;plate.layer.shadowOpacity=0.12;plate.layer.shadowRadius=16;plate.layer.shadowOffset=CGSize(width:0,height:6)
        popup.backgroundColor = .systemBackground;popup.layer.cornerRadius=16;popup.clipsToBounds=true
        addChild(host);popup.addSubview(host.view);plate.addSubview(popup);view.addSubview(plate);host.didMove(toParent:self);card=host;view.setNeedsLayout()
        UIAccessibility.post(notification:.screenChanged,argument:host.view)
    }
    @objc private func relayout(_ n:Notification) {view.setNeedsLayout()}
    func gestureRecognizer(_ gestureRecognizer:UIGestureRecognizer,shouldReceive touch:UITouch)->Bool {
        return touch.view?.isDescendant(of:plate) != true
    }
    override func preferredContentSizeDidChange(forChildContentContainer container:any UIContentContainer) {view.setNeedsLayout()}
    override func viewDidLayoutSubviews() {
        super.viewDidLayoutSubviews();guard let card else {return}
        let gutter:CGFloat=20,width=min(380,view.bounds.width-2*gutter)
        let natural=card.sizeThatFits(in:CGSize(width:width,height:10000));let height=min(440,natural.height)
        let safeTop=view.safeAreaInsets.top+8,lower=view.bounds.height-view.safeAreaInsets.bottom-height-8
        var y=anchorRect.maxY+8
        if y>lower {y=anchorRect.minY-height-8}
        if anchorRect == .zero {y=view.bounds.midY-height/2}
        plate.frame=CGRect(x:max(gutter,min(view.bounds.width-width-gutter,anchorRect.midX-width/2)),y:max(safeTop,min(lower,y)),width:width,height:height)
        popup.frame=plate.bounds;card.view.frame=CGRect(x:0,y:0,width:width,height:natural.height);popup.contentSize=natural
    }
    @objc private func dismissCard() {
        guard opened else {return};opened=false
        card?.willMove(toParent:nil);card?.view.removeFromSuperview();card?.removeFromParent();card=nil;plate.removeFromSuperview()
        NotificationCenter.default.post(name:Notification.Name("ResumeSayWithLearning"),object:nil)
    }
}

struct NotebookPage:View {
    let model:LearningModel
    @State private var entries:[NotebookEntry]=[]
    @State private var openedEntry:NotebookEntry?
    @State private var error:String?
    @State private var audio=DictionaryAudio()
    private var days:[Date] {Array(Set(entries.map {Calendar.current.startOfDay(for:Date(timeIntervalSince1970:$0.createdAt))})).sorted(by:>)}
    var body:some View {
        List {
            if entries.isEmpty && error==nil {ContentUnavailableView("还没有生词",systemImage:"bookmark",description:Text("点英文句子里的词，可以加入生词本。"))}
            if let error {Text(error).foregroundStyle(.red);Button("重新加载") {Task {await load()}}}
            ForEach(days,id:\.self) {day in
                HStack {Text(dayTitle(day)).font(.subheadline.weight(.semibold));Spacer();Text("\(dayEntries(day).count) 个").font(.caption).foregroundStyle(.secondary)}.listRowBackground(Color.clear).listRowSeparator(.hidden).deleteDisabled(true)
                ForEach(dayEntries(day)) {entry in
                    HStack(spacing:8) {
                        Button {openedEntry=entry} label:{VStack(alignment:.leading,spacing:4) {HStack {Text(entry.word).font(.subheadline.weight(.semibold));Text(entry.card.phoneticUs ?? entry.card.phoneticUk ?? "").font(.caption).foregroundStyle(.secondary)};Text(entry.card.shortMeaning).font(.footnote).foregroundStyle(.secondary).lineLimit(1)}}.buttonStyle(.plain).frame(maxWidth:.infinity,alignment:.leading).accessibilityIdentifier("notebook-"+entry.word)
                        Button {audio.play(entry.word,accent:"us")} label:{Image(systemName:"speaker.wave.2.fill").frame(width:44,height:44)}.buttonStyle(.borderless).accessibilityLabel("朗读 "+entry.word)
                        Image(systemName:"chevron.right").font(.caption).foregroundStyle(.tertiary)
                    }.padding(10).background(Color(uiColor:.secondarySystemGroupedBackground),in:RoundedRectangle(cornerRadius:16)).listRowInsets(EdgeInsets(top:4,leading:20,bottom:4,trailing:20)).listRowBackground(Color.clear).listRowSeparator(.hidden)
                }.onDelete {offsets in let selected=offsets.map {dayEntries(day)[$0]};Task {for entry in selected {await remove(entry)};await load()}}
            }
        }.listStyle(.plain).scrollContentBackground(.hidden).background(Color(uiColor:.systemGroupedBackground))
        .navigationTitle("生词本").navigationBarTitleDisplayMode(.inline).toolbar(.hidden,for:.tabBar)
        .navigationDestination(item:$openedEntry) {NotebookDetail(model:model,entry:$0)}
        .task {await load()}.refreshable {await load()}.onDisappear {audio.stop()}
    }
    private func dayTitle(_ day:Date)->String {Calendar.current.isDateInToday(day) ? "今天":Calendar.current.isDateInYesterday(day) ? "昨天":day.formatted(date:.abbreviated,time:.omitted)}
    private func dayEntries(_ day:Date)->[NotebookEntry] {entries.filter {Calendar.current.isDate(Date(timeIntervalSince1970:$0.createdAt),inSameDayAs:day)}}
    private func load() async {do {let api=try await model.feedbackClient();let list:NotebookList=try await api.request("v1/notebook");entries=list.items;error=nil} catch {self.error=error.localizedDescription}}
    private func remove(_ entry:NotebookEntry) async {do {let api=try await model.feedbackClient();let _:NotebookRemoved=try await api.request("v1/notebook/"+entry.id,method:"DELETE");try await model.refresh()} catch {self.error=error.localizedDescription}}
}
struct NotebookDetail:View {
    let model:LearningModel;let entry:NotebookEntry
    @Environment(\.dismiss) private var dismiss
    @State private var card:DictionaryCard?
    @State private var error:String?
    @State private var audio=DictionaryAudio()
    @State private var removing=false
    @State private var confirm=false
    var body:some View {
        ScrollView {
            VStack(alignment:.leading,spacing:20) {
                VStack(alignment:.leading,spacing:8) {LookupText(entry.word).font(.title.bold());DictionaryPhonetics(card:card ?? entry.card,audio:audio)}.padding(18).frame(maxWidth:.infinity,alignment:.leading).background(Color(uiColor:.secondarySystemGroupedBackground),in:RoundedRectangle(cornerRadius:16))
                if let error {Text(error).font(.footnote).foregroundStyle(.red)}
                ForEach(Array(((card ?? entry.card).senses ?? []).enumerated()),id:\.offset) {_,sense in
                    VStack(alignment:.leading,spacing:12) {
                        LookupText((sense.pos ?? "")+" "+(sense.meaningCn ?? "")).font(.headline)
                        if let meaning=sense.meaningEn {LookupText(meaning).font(.subheadline).foregroundStyle(.secondary)}
                        if let pattern=sense.pattern,!pattern.isEmpty {LookupText(pattern).font(.subheadline)}
                        if let collocation=sense.collocation,!collocation.isEmpty {LookupText(collocation).font(.subheadline).foregroundStyle(Color.accentColor)}
                        ForEach(Array((sense.examples ?? []).enumerated()),id:\.offset) {_,example in exampleView(example)}
                    }.padding(18).frame(maxWidth:.infinity,alignment:.leading).background(Color(uiColor:.secondarySystemGroupedBackground),in:RoundedRectangle(cornerRadius:16))
                }
                if !entry.contexts.isEmpty {Text("收藏时的内容").font(.headline);ForEach(entry.contexts,id:\.self) {LookupText($0).font(.subheadline)}}
            }.padding(20)
        }.background(Color(uiColor:.systemGroupedBackground)).navigationTitle("生词").navigationBarTitleDisplayMode(.inline)
        .toolbar {Button("移出",role:.destructive) {confirm=true}.disabled(removing).accessibilityIdentifier("removeNotebookWord")}
        .confirmationDialog("移出生词本？已有学习证据会保留。",isPresented:$confirm,titleVisibility:.visible) {Button("移出",role:.destructive) {remove()}.accessibilityIdentifier("confirmRemoveNotebookWord")}
        .task {do {let api=try await model.feedbackClient();let encoded=entry.word.addingPercentEncoding(withAllowedCharacters:.urlQueryAllowed) ?? entry.word;card=try await api.request("v1/vocabulary/knowledge?word="+encoded);audio.play(entry.word,accent:"us")} catch {self.error="完整词条暂时无法加载，保留已保存的释义。"}}
        .onDisappear {audio.stop()}
    }
    private func exampleView(_ example:DictionaryExample)->some View {
        VStack(alignment:.leading,spacing:6) {
            LookupText(example.text)
            if let cn=example.translationCn {LookupText(cn).font(.subheadline).foregroundStyle(.secondary)}
            HStack {
                Button {audio.play(example.text,accent:"us")} label:{Image(systemName:"speaker.wave.2.fill").frame(width:44,height:44)}.accessibilityLabel("播放例句")
                if example.isGenerated==true {Text("AI 例句").font(.caption).foregroundStyle(.secondary)}
            }
        }
    }
    private func remove() {removing=true;Task {defer {removing=false};do {let api=try await model.feedbackClient();let _:NotebookRemoved=try await api.request("v1/notebook/"+entry.id,method:"DELETE");try await model.refresh();dismiss()} catch {self.error=error.localizedDescription}}}
}
