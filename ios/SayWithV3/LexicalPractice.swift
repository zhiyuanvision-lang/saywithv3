import SwiftUI

struct LexicalPracticeView:Decodable,Identifiable,Sendable {
    let practiceId:String;let promptZh:String;let completed:Bool;let supportUsed:[String]
    var id:String {practiceId}
}
struct LexicalPracticeResponse:Decodable,Sendable {
    let message:String;let hint:String;let example:String;let transcript:String;let completed:Bool;let supportUsed:[String];let session:SessionState
}

/// Owns retries and recording for a single server-bound try-first task.
@MainActor @Observable final class LexicalPracticeModel {
    var busy=false;var error:String?;var feedback:LexicalPracticeResponse?
    var audio=AudioController()
    private var pending:[String:JSONValue]?
    private var pendingAudio:Data?
    func submit(_ kind:String,practice:LexicalPracticeView,learning:LearningModel,hint:String="meaning",text:String="",data:Data?=nil) async {
        guard !busy,let session=learning.session else {return}
        busy=true;error=nil;defer {busy=false}
        do {
            let api=try await learning.feedbackClient()
            if pending==nil {
                pending=["schema_version":.string("1.0"),"input_id":.string(UUID().uuidString),"practice_id":.string(practice.id),"type":.string(kind),"hint_level":.string(hint)]
                if !text.isEmpty {pending?["text"] = .string(text)}
                pendingAudio=data
            }
            if let bytes=pendingAudio,pending?["audio_ref"]==nil {
                let asset=try await api.upload(bytes);pending?["audio_ref"] = .string(asset.audioRef)
            }
            let response:LexicalPracticeResponse=try await api.request("v1/sessions/"+session.view.sessionId+"/vocabulary-attempts",method:"POST",body:pending)
            feedback=response;learning.session=response.session;pending=nil;pendingAudio=nil;audio.discard()
            try await learning.refresh()
        } catch {self.error=error.localizedDescription}
    }
    func cancelPending() {pending=nil;pendingAudio=nil;error=nil;audio.discard()}
}

struct LexicalPracticeCard:View {
    let model:LearningModel;let practice:LexicalPracticeView
    @State private var state=LexicalPracticeModel()
    @State private var fixtureText=""
    @State private var showFixtureText=false
    @State private var hold=HoldRecordingGesture()
    @State private var recordingStartTask:Task<Void,Never>?
    @Environment(\.scenePhase) private var scenePhase
    private var nextHint:String {let used=state.feedback?.supportUsed ?? practice.supportUsed;return !used.contains("meaning") ? "meaning":!used.contains("pattern") ? "pattern":"example"}
    var body:some View {
        VStack(alignment:.leading,spacing:16) {
            Label("生词先试一试",systemImage:"bookmark").font(.headline).accessibilityIdentifier("lexicalPracticeCard")
            Text("先表达这个意思，需要时再看提示。").font(.subheadline).foregroundStyle(.secondary)
            LookupText(practice.promptZh).font(.title3.weight(.semibold)).accessibilityIdentifier("lexicalPrompt")
            if let feedback=state.feedback {
                if !feedback.transcript.isEmpty {LookupText(feedback.transcript).foregroundStyle(.secondary)}
                if !feedback.hint.isEmpty {LookupText(feedback.hint).padding(12).background(Color.accentColor.opacity(0.08),in:RoundedRectangle(cornerRadius:10))}
                if !feedback.example.isEmpty {Text("看懂后，换成自己的内容再试说。").font(.footnote).foregroundStyle(.secondary)}
                Text(feedback.message).font(.subheadline).accessibilityIdentifier("lexicalFeedback")
            }
            if let error=state.error {
                Text(error).font(.footnote).foregroundStyle(.red)
                HStack {Button("重试提交") {submit("speech")};Button("取消这次提交") {state.cancelPending()}}.font(.subheadline)
            }
            HStack {
                HoldToSpeakButton(hold:$hold,idleTitle:"按住试说",processing:state.busy,
                    disabled:state.busy || state.error != nil || model.busy,identifier:"lexicalRecord",canStart:{true},
                    onBegin:beginRecording,onFinish:finishRecording,onCancel:cancelRecording)
                Button(nextHint=="meaning" ? "看词义":nextHint=="pattern" ? "看句式":"看示例") {submit("request_hint",hint:nextHint)}.buttonStyle(.bordered).disabled(hold.active).accessibilityIdentifier("lexicalHint")
            }.disabled(state.busy || state.error != nil || model.busy)
            if state.busy {ProgressView("正在处理这次尝试")}
            Button("稍后练，继续课程") {submit("skip")}.font(.subheadline).disabled(state.busy || model.busy || hold.active || state.audio.recording || state.error != nil).accessibilityIdentifier("lexicalSkip")
            if model.session?.view.fixture==true {
                DisclosureGroup("测试文字输入",isExpanded:$showFixtureText) {TextField("测试回应",text:$fixtureText).textFieldStyle(.roundedBorder).accessibilityIdentifier("lexicalTestInput");Button("提交测试回应") {submit("text",text:fixtureText)}.accessibilityIdentifier("lexicalTestSubmit")}
            }
        }.padding(18).frame(maxWidth:.infinity,alignment:.leading).background(Color(uiColor:.secondarySystemGroupedBackground),in:RoundedRectangle(cornerRadius:16))
        .onChange(of:scenePhase) {_,phase in if phase != .active {cancelRecording()}}
        .onReceive(NotificationCenter.default.publisher(for:Notification.Name("PauseSayWithLearning"))) {_ in cancelRecording()}
        .onDisappear {cancelRecording()}
    }
    private func beginRecording() {
        state.audio.lastRecording=nil;state.audio.duration=0
        recordingStartTask?.cancel()
        recordingStartTask=Task {
            do {try await state.audio.start()}
            catch is CancellationError {} catch {if !Task.isCancelled {hold.reset();state.error=error.localizedDescription}}
        }
    }
    private func finishRecording(_ translation:CGFloat) {
        guard let release=hold.finish(verticalTranslation:translation) else {return}
        recordingStartTask?.cancel();recordingStartTask=nil
        guard release == .send else {state.audio.discard();return}
        guard state.audio.recording || state.audio.lastRecording != nil else {return}
        do {
            let data=try state.audio.recording ? state.audio.stop():state.audio.lastRecording ?? Data()
            guard state.audio.duration>=0.4,!data.isEmpty else {state.audio.discard();return}
            Task {await state.submit("speech",practice:practice,learning:model,data:data)}
        } catch {state.error=error.localizedDescription}
    }
    private func cancelRecording() {hold.reset();recordingStartTask?.cancel();recordingStartTask=nil;state.audio.discard()}
    private func submit(_ kind:String,hint:String="meaning",text:String="") {Task {await state.submit(kind,practice:practice,learning:model,hint:hint,text:text)}}
}
