import Foundation
import Observation

@MainActor @Observable
final class LearningModel {
    static var defaultBackendURL: String {
        let configured=Bundle.main.object(forInfoDictionaryKey:"SayWithBackendURL") as? String ?? ""
        return configured.hasPrefix("https://") ? configured : "https://api.saywith.zhiyuanv.com/learning"
    }
    var baseURL = LearningModel.defaultBackendURL
    var stage = "A2"
    var context = "校园与日常生活"
    var profile: Profile?
    var restoringLogin=true
    var displayName:String {CredentialStore.login(account:baseURL)?.displayName ?? "学习者"}
    var maskedPhone:String {
        let phone=CredentialStore.login(account:baseURL)?.phone ?? ""
        return phone.count == 11 ? String(phone.prefix(3))+"****"+String(phone.suffix(4)) : ""
    }
    var recommendations:Recommendations?
    var reviewEntry=false
    var health: Health?
    var job: Job?
    var session: SessionState?
    var assessment: Assessment?
    var busy = false
    var error: String?
    var personalText = ""
    var selectedMaterial = 0
    var answerVisible = true
    var typedReply = ""
    var requestStatus=""
    var hintResponse:Dialogue?
    var hintText:String?
    var translations:[String:String]=[:]
    var shadowFeedback:ShadowFeedback?
    var outgoingMessage:OutgoingMessage?
    private var pendingUpload:Data?
    private var pendingShadowAudio:Data?
    var hasPendingShadow:Bool {pendingShadowAudio != nil}
    private var pendingLearningAudio:Data?
    private var pendingLearningShadow=false
    private var pendingLearningRequest:[String:JSONValue]?
    var hasPendingLearning:Bool {pendingLearningAudio != nil || pendingLearningRequest != nil}
    private var pendingShadowRequest:[String:JSONValue]?
    private var api: API?
    private var activeJobKey: String?
    var storageScope: String { Self.accountStorageScope(baseURL:apiScope ?? baseURL,userID:profile?.userId ?? "visitor") }
    static func accountStorageScope(baseURL:String,userID:String)->String {"-"+baseURL+"-"+userID}
    private var apiScope: String?
    private var pendingInput: [String: JSONValue]?
    private var repeatInFlight=false
    private var pendingRepeat:[String:JSONValue]?
    var hasAccount: Bool {profile != nil}

    init() {
        #if DEBUG
        baseURL=UserDefaults.standard.string(forKey:"backendURL") ?? baseURL
        let args=ProcessInfo.processInfo.arguments
        if let i=args.firstIndex(of:"--backend-url"),args.indices.contains(i+1) {baseURL=args[i+1]}
        #endif
    }
    func perform(_ operation: () async throws -> Void) async {
        guard !busy,!repeatInFlight else {return}
        busy=true;error=nil
        defer {busy=false;requestStatus=""}
        do {try await operation()}
        catch is CancellationError {}
        catch {self.error=error.localizedDescription;if outgoingMessage != nil {outgoingMessage?.stage="failed"}}
    }
    func connect(create: Bool = false, savePreferences: Bool = false) async throws {
        let url=try API.validatedURL(baseURL)
        let client=API(base:url,token:CredentialStore.read(account:url.absoluteString))
        let loadedHealth: Health=try await client.request("health",auth:false)
        if create {
            #if DEBUG
            guard loadedHealth.mode == "fixture",ProcessInfo.processInfo.arguments.contains("--ui-test-anonymous") else {throw APIError.missingToken}
            let registration: Registration=try await client.request("v1/users",method:"POST",body:[
                "context":.string(context),"reference_stage":.string(stage),"interests":.array([])],auth:false)
            try CredentialStore.save(registration.accessToken,account:url.absoluteString)
            await client.authenticate(registration.accessToken)
            #else
            throw APIError.missingToken
            #endif
        }
        let identity:AccountStatus=try await client.request("v1/auth/me")
        #if DEBUG
        let fixtureAccount=loadedHealth.mode == "fixture" && ProcessInfo.processInfo.arguments.contains("--ui-test-anonymous")
        #else
        let fixtureAccount=false
        #endif
        guard identity.verified || fixtureAccount else {throw APIError.missingToken}
        #if DEBUG
        if loadedHealth.mode == "fixture" && ProcessInfo.processInfo.arguments.contains("--ui-test-notebook") {
            let _:NotebookEntry=try await client.request("v1/notebook",method:"POST",body:["word":.string("available"),"context":.string("Are you available tomorrow?")])
        }
        #endif
        let loaded: Profile = try await client.request("v1/profile")
        let connected: Profile
        if savePreferences {
            connected=try await client.request("v1/profile/preferences",method:"PATCH",body:[
                "context":.string(context),"reference_stage":.string(stage),"interests":loaded.preferences["interests"] ?? .array([])])
        } else {
            connected=loaded
            stage=loaded.preferences["reference_stage"]?.text ?? stage
            context=loaded.preferences["context"]?.text ?? context
        }
        if apiScope != url.absoluteString || profile?.userId != connected.userId {clearAccountMemory()}
        recommendations=try await client.request("v1/recommendations")
        api=client;profile=connected;health=loadedHealth;apiScope=url.absoluteString
        if create {
            session=nil;job=nil;assessment=nil;pendingInput=nil;activeJobKey=nil
            for key in ["activeSession","activeJob","pendingJobKey","pendingJobRequest","activeEntryKind"] {UserDefaults.standard.removeObject(forKey:key+storageScope)}
        }
        else {
            reviewEntry=UserDefaults.standard.string(forKey:"activeEntryKind"+storageScope)=="review" || (UserDefaults.standard.data(forKey:"pendingJobRequest"+storageScope).flatMap {try? JSONDecoder().decode([String:JSONValue].self,from:$0)}?["entry_kind"]?.text)=="review"
            activeJobKey=UserDefaults.standard.string(forKey:"pendingJobKey"+storageScope)
            if let id=UserDefaults.standard.string(forKey:"activeJob"+storageScope) {
                job=try await client.request("v1/course-generation-jobs/"+id)
            }
        }
        UserDefaults.standard.set(baseURL,forKey:"backendURL")
        if !create, let id=UserDefaults.standard.string(forKey:"activeSession"+storageScope) {
            do {
                session=try await client.request("v1/sessions/"+id)
                if session?.view.phase=="abandoned" {session=nil;UserDefaults.standard.removeObject(forKey:"activeSession"+storageScope)}
                if let view=session?.view, view.phase == "learning" {
                    let completed=view.completedMaterialIndices ?? []
                    selectedMaterial=view.materials.indices.first { !completed.contains($0) } ?? max(0,view.materials.count-1)
                    answerVisible=true;personalText=""
                }
            } catch {session=nil}
        }
    }
    func restoreLogin() async {
        guard !busy else {return}
        defer {restoringLogin=false}
        guard CredentialStore.login(account:baseURL) != nil else {return}
        await perform {try await connect()}
    }
    func loginClient() throws -> API {API(base:try API.validatedURL(baseURL),token:nil)}
    func login(path:String,body:[String:JSONValue]) async throws {
        let url=try API.validatedURL(baseURL)
        let legacy=CredentialStore.login(account:url.absoluteString)==nil ? CredentialStore.read(account:url.absoluteString) : nil
        let client=API(base:url,token:nil)
        let response:LoginResponse=try await client.request(path,method:"POST",body:body,auth:false,legacyToken:legacy)
        try CredentialStore.save(SavedLogin(response),account:url.absoluteString)
        // Only the first adoption may move the old service-scoped resume keys.
        if response.adoptedAnonymous == true {
            let newScope=Self.accountStorageScope(baseURL:url.absoluteString,userID:response.userId)
            for key in ["activeSession","activeJob","pendingJobKey","pendingJobRequest","activeEntryKind"] {
                let old=key+"-"+url.absoluteString
                if let value=UserDefaults.standard.object(forKey:old) {
                    UserDefaults.standard.set(value,forKey:key+newScope)
                    UserDefaults.standard.removeObject(forKey:old)
                }
            }
        }
        try await connect()
    }
    func signOut() async throws {
        let url=try API.validatedURL(baseURL)
        if let login=CredentialStore.login(account:url.absoluteString) {
            let client=API(base:url,token:nil)
            let _:LogoutResponse=try await client.request("v1/auth/logout",method:"POST",
                body:["refresh_token":.string(login.refreshToken)],auth:false)
        }
        try CredentialStore.delete(account:url.absoluteString)
        clearAccountMemory();profile=nil;api=nil;apiScope=nil;health=nil;error=nil
    }
    func loginExpired() {
        clearAccountMemory();profile=nil;api=nil;apiScope=nil;health=nil
        error=APIError.loginExpired.localizedDescription
    }
    private func clearAccountMemory() {
        session=nil;job=nil;assessment=nil;recommendations=nil;pendingInput=nil;pendingUpload=nil;outgoingMessage=nil
        pendingLearningRequest=nil;pendingLearningAudio=nil;pendingShadowRequest=nil;pendingShadowAudio=nil;pendingRepeat=nil;activeJobKey=nil
        translations=[:];hintText=nil;hintResponse=nil;shadowFeedback=nil;personalText="";typedReply=""
        reviewEntry=false;selectedMaterial=0;answerVisible=true
    }
    func authenticatedClient() throws -> API {
        guard let api,hasAccount else {throw APIError.missingToken}
        return api
    }
    func refresh() async throws {
        guard let api else {return}
        profile=try await api.request("v1/profile")
        recommendations=try await api.request("v1/recommendations")
    }
    func generate(review:ReviewRecommendation?=nil) async throws {
        reviewEntry=review != nil
        try await refresh()
        guard let api,let profile else {throw APIError.missingToken}
        if job?.terminal != false {
            let key=activeJobKey ?? UUID().uuidString;activeJobKey=key
            UserDefaults.standard.set(key,forKey:"pendingJobKey"+storageScope)
            var request:[String:JSONValue]=["minutes":.number(10),"context":.string(context),"profile_version":.number(Double(profile.profileVersion))]
            if let review {request["target_id"] = .string(review.targetId);request["entry_kind"] = .string("review");request["minutes"] = .number(Double(review.minutes))}
            else if health?.mode == "fixture" {request["target_id"] = .string("ARRANGE.A2.s2")}
            if let saved=UserDefaults.standard.data(forKey:"pendingJobRequest"+storageScope), activeJobKey != nil {
                request=try JSONDecoder().decode([String:JSONValue].self,from:saved)
            } else {
                UserDefaults.standard.set(try JSONEncoder().encode(request),forKey:"pendingJobRequest"+storageScope)
            }
            reviewEntry=request["entry_kind"]?.text=="review"
            UserDefaults.standard.set(reviewEntry ? "review":"course",forKey:"activeEntryKind"+storageScope)
            job=try await api.request("v1/course-generation-jobs",method:"POST",body:request,key:key)
            UserDefaults.standard.set(job?.jobId,forKey:"activeJob"+storageScope)
        }
        try await poll()
    }
    func poll() async throws {
        guard let api,let first=job else {return}
        for _ in 0..<180 {
            try Task.checkCancellation()
            let current:Job=try await api.request("v1/course-generation-jobs/"+first.jobId);job=current
            if current.terminal {
                activeJobKey=nil
                UserDefaults.standard.removeObject(forKey:"pendingJobKey"+storageScope)
                UserDefaults.standard.removeObject(forKey:"pendingJobRequest"+storageScope)
                if let lesson=current.resultLessonId {
                    if session?.view.lessonId != lesson {
                        session=try await api.request("v1/sessions",method:"POST",body:["lesson_id":.string(lesson),"entry_kind":.string(reviewEntry ? "review":"course")])
                    }
                    if let session {UserDefaults.standard.set(session.view.sessionId,forKey:"activeSession"+storageScope)}
                    selectedMaterial=0;answerVisible=true;assessment=nil;shadowFeedback=nil;hintText=nil;hintResponse=nil;translations=[:];typedReply=""
                } else {throw APIError.server(current.state=="needs_review" ? "这份课程需要重新准备，请再次尝试。":"课程暂未就绪，请重试。")}
                return
            }
            try await Task.sleep(for:.seconds(2))
        }
        throw APIError.server("课程仍在生成，可稍后继续查看。")
    }
    func cancelJob() async throws {
        guard let api,let job else {return}
        self.job=try await api.request("v1/course-generation-jobs/"+job.jobId+"/cancel",method:"POST")
        if self.job?.state == "cancelled" {
            activeJobKey=nil
            UserDefaults.standard.removeObject(forKey:"pendingJobKey"+storageScope)
            UserDefaults.standard.removeObject(forKey:"pendingJobRequest"+storageScope)
        }
    }
    func learn() async throws {
        guard let api,let current=session else {return}
        session=try await api.request("v1/sessions/"+current.view.sessionId+"/learn",method:"POST",body:[
            "material_index":.number(Double(selectedMaterial)),"personal_text":.string(personalText)])
        if selectedMaterial+1<current.view.materials.count {selectedMaterial+=1;personalText="";answerVisible=true}
    }
    func next() async throws {
        guard let api,let current=session else {return}
        session=try await api.request("v1/sessions/"+current.view.sessionId+"/next",method:"POST",body:["expected_session_version":.number(Double(current.sessionVersion)),"advance_round":.bool(true)])
        hintText=nil;hintResponse=nil;shadowFeedback=nil
        personalText="";answerVisible=true;typedReply=""
    }
    private func watchInput(_ key:String,sessionID:String,api:API,learning:Bool=false) async {
        while !Task.isCancelled && outgoingMessage?.id==key {
            do {
                let progress:InputProgress=try await api.request("v1/sessions/"+sessionID+"/inputs/"+key)
                guard !Task.isCancelled,outgoingMessage?.id==key,session?.view.sessionId==sessionID else {return}
                outgoingMessage?.turnId=progress.turnId;outgoingMessage?.text=progress.transcript
                outgoingMessage?.audioRef=progress.audioRef
                outgoingMessage?.stage=learning ? (progress.status=="recognizing" ? "recognizing":"checking"):(progress.status=="completed" ? "responding":progress.status)
            } catch is CancellationError {return} catch {}
            do {try await Task.sleep(for:.milliseconds(500))} catch {return}
        }
    }
    func send(kind: String, audio: Data? = nil, hintLevel:String="intent",sourceTurnID:String?=nil) async throws {
        guard let api,let current=session else {return}
        if pendingInput == nil {
            var body:[String:JSONValue]=["schema_version":.string("1.0"),"session_id":.string(current.view.sessionId),
                "task_id":.string(current.view.taskId),"input_id":.string(outgoingMessage?.id ?? UUID().uuidString),"type":.string(kind),
                "recorded_at":.string(ISO8601DateFormatter().string(from:Date())),
                "expected_session_version":.number(Double(current.sessionVersion)),"hint_level":.string(hintLevel)]
            if kind=="speech" || kind=="text" {
                if outgoingMessage==nil {outgoingMessage=OutgoingMessage(id:body["input_id"]!.text,text:kind=="text" ? typedReply:nil,stage:audio==nil ? "responding":"uploading")}
                else {outgoingMessage?.stage=audio==nil ? "responding":"uploading"}
            }
            if let sourceTurnID {body["source_turn_id"] = .string(sourceTurnID)}
            if let audio {
                pendingUpload=audio;requestStatus="上传中"
                let uploaded=try await api.upload(audio);body["audio_ref"] = .string(uploaded.audioRef);pendingUpload=nil
            } else if kind == "text" {body["text"] = .string(typedReply)}
            pendingInput=body
        }
        requestStatus="等待回应"
        let receiptTask:Task<Void,Never>?
        if let draft=outgoingMessage {outgoingMessage?.stage="recognizing";receiptTask=Task {await self.watchInput(draft.id,sessionID:current.view.sessionId,api:api)}} else {receiptTask=nil}
        defer {receiptTask?.cancel()}
        let response:Dialogue=try await api.request("v1/sessions/"+current.view.sessionId+"/inputs",method:"POST",body:pendingInput)
        if response.kind=="hint" {hintText=response.text;hintResponse=response}
        if response.kind=="translation",let key=sourceTurnID ?? pendingInput?["source_turn_id"]?.text {translations[key]=response.text}
        session=try await api.request("v1/sessions/"+current.view.sessionId)
        pendingInput=nil;typedReply="";outgoingMessage=nil
        if response.continuation=="advanced",session?.view.phase=="finished" {try await refresh()}
        if response.continuation=="retry" {error="对话已结束，后续流程暂未完成，请点击继续流程。"}
    }
    func retryInput() async throws {try await send(kind:pendingUpload == nil ? "text" : "speech",audio:pendingUpload)}
    var hasPendingInput: Bool {pendingInput != nil || pendingUpload != nil}
    func finish() async throws {
        guard let api,let current=session else {return}
        requestStatus="正在整理本次表现"
        assessment=try await api.request("v1/sessions/"+current.view.sessionId+"/finish",method:"POST")
        session=try await api.request("v1/sessions/"+current.view.sessionId)
        try await refresh()
    }
    func sound(_ ref: String) async throws -> Data {
        guard let api else {throw APIError.missingToken}
        return try await api.audio(ref)
    }
    // Replay is logged as support, without replacing the page's action/status state.
    func recordRepeat(sourceTurnID:String) async throws {
        guard let api,let current=session,!busy,!repeatInFlight,!hasPendingInput else {throw APIError.server("请等待当前操作完成。")}
        repeatInFlight=true
        defer {repeatInFlight=false}
        if pendingRepeat?["session_id"]?.text != current.view.sessionId || pendingRepeat?["source_turn_id"]?.text != sourceTurnID {
            pendingRepeat=["schema_version":.string("1.0"),"session_id":.string(current.view.sessionId),
                "task_id":.string(current.view.taskId),"input_id":.string(UUID().uuidString),
                "type":.string("request_repeat"),"source_turn_id":.string(sourceTurnID),
                "recorded_at":.string(ISO8601DateFormatter().string(from:Date())),
                "expected_session_version":.number(Double(current.sessionVersion))]
        }
        let _:Dialogue=try await api.request("v1/sessions/"+current.view.sessionId+"/inputs",method:"POST",body:pendingRepeat)
        let refreshed:SessionState=try await api.request("v1/sessions/"+current.view.sessionId)
        if session?.view.sessionId==current.view.sessionId {session=refreshed}
        pendingRepeat=nil
    }
    func learningAction(_ action:String) async throws {
        guard let api,let current=session else {return}
        session=try await api.request("v1/sessions/"+current.view.sessionId+"/learning-practice",method:"POST",body:[
            "material_index":.number(Double(selectedMaterial)),"action":.string(action),
            "expected_session_version":.number(Double(current.sessionVersion))])
    }
    func learningAttempt(_ audio:Data,shadow:Bool=false) async throws {
        guard let api,let current=session else {return}
        if pendingLearningRequest==nil {
            pendingLearningAudio=audio;pendingLearningShadow=shadow;requestStatus="上传中"
            let inputID=UUID().uuidString
            outgoingMessage=OutgoingMessage(id:inputID,stage:"uploading")
            let uploaded=try await api.upload(audio)
            var body:[String:JSONValue]=["material_index":.number(Double(selectedMaterial)),
                "action":.string(shadow ? "shadow":"attempt"),"input_id":.string(inputID),
                "audio_ref":.string(uploaded.audioRef),"expected_session_version":.number(Double(current.sessionVersion))]
            if !shadow,let stage=current.view.learningPractice?.stage {body["stage"] = .string(stage)}
            pendingLearningRequest=body
        }
        outgoingMessage?.stage="recognizing"
        let receiptTask=Task {if let key=pendingLearningRequest?["input_id"]?.text {await watchInput(key,sessionID:current.view.sessionId,api:api,learning:true)}}
        defer {receiptTask.cancel()}
        requestStatus="正在确认表达"
        session=try await api.request("v1/sessions/"+current.view.sessionId+"/learning-practice",method:"POST",body:pendingLearningRequest)
        pendingLearningRequest=nil;pendingLearningAudio=nil;outgoingMessage=nil
    }
    func retryLearningAttempt() async throws {try await learningAttempt(pendingLearningAudio ?? Data(),shadow:pendingLearningShadow)}
    func recheckLearningRecognition(_ ref:String) async throws {
        guard let current=session else {return}
        let key=UUID().uuidString
        outgoingMessage=OutgoingMessage(id:key,stage:"recognizing")
        pendingLearningShadow=false;pendingLearningAudio=nil
        pendingLearningRequest=["material_index":.number(Double(selectedMaterial)),"action":.string("attempt"),
            "input_id":.string(key),"audio_ref":.string(ref),"stage":.string(current.view.learningPractice?.stage ?? "recall"),
            "recognition_retry":.bool(true),"expected_session_version":.number(Double(current.sessionVersion))]
        try await learningAttempt(Data())
    }
    func confirmLearningTranscript(_ text:String,feedback:LearningPracticeView.Feedback) async throws {
        guard let current=session else {return}
        let key=UUID().uuidString
        outgoingMessage=OutgoingMessage(id:key,text:text,stage:"checking")
        pendingLearningShadow=false;pendingLearningAudio=nil
        pendingLearningRequest=["material_index":.number(Double(selectedMaterial)),"action":.string("attempt"),
            "input_id":.string(key),"audio_ref":.string(feedback.audioRef),"stage":.string(current.view.learningPractice?.stage ?? "recall"),
            "confirmed_transcript":.string(text),"original_transcript":.string(feedback.transcript),
            "expected_session_version":.number(Double(current.sessionVersion))]
        try await learningAttempt(Data())
    }
    func discardLearningAttempt() {pendingLearningRequest=nil;pendingLearningAudio=nil;outgoingMessage=nil}
    func shadow(_ audio:Data) async throws {
        guard let api,let current=session else {return}
        if pendingShadowRequest==nil {
            pendingShadowAudio=audio;requestStatus="上传中"
            let uploaded=try await api.upload(audio)
            pendingShadowRequest=["material_index":.number(Double(selectedMaterial)),"audio_ref":.string(uploaded.audioRef),"input_id":.string(UUID().uuidString)]
        }
        requestStatus="正在确认跟读"
        let result:ShadowResponse=try await api.request("v1/sessions/"+current.view.sessionId+"/shadow",method:"POST",body:pendingShadowRequest)
        session=result.session;shadowFeedback=result.feedback;pendingShadowRequest=nil;pendingShadowAudio=nil
    }
    func retryShadow() async throws {if let audio=pendingShadowAudio {try await shadow(audio)}}
    func discardShadowRequest() {pendingShadowRequest=nil;pendingShadowAudio=nil}
    func advanceMaterial() async throws {
        guard let current=session else {return}
        if selectedMaterial+1<current.view.materials.count {
            selectedMaterial+=1;shadowFeedback=nil;answerVisible=true
        } else {try await next()}
    }
    func replyAdvice(_ turnID:String) async throws -> ReplyAdvice {
        guard let api,let current=session else {throw APIError.missingToken}
        let value:ReplyAdvice=try await api.request("v1/sessions/"+current.view.sessionId+"/turns/"+turnID+"/feedback",method:"POST")
        // Viewing a worked example changes support tracking and the session version.
        if session?.view.sessionId==current.view.sessionId {
            session=try await api.request("v1/sessions/"+current.view.sessionId)
        }
        return value
    }
    func transition(_ action:String) async throws {
        guard let api,let current=session else {return}
        session=try await api.request("v1/sessions/"+current.view.sessionId+"/transition",method:"POST",body:[
            "action":.string(action),"expected_session_version":.number(Double(current.sessionVersion))])
        pendingInput=nil;pendingUpload=nil;outgoingMessage=nil;pendingLearningRequest=nil;pendingLearningAudio=nil;pendingShadowRequest=nil;pendingShadowAudio=nil;hintText=nil;hintResponse=nil;assessment=nil;shadowFeedback=nil
        if action=="exit" {leave()}
    }
    func backToHome() {
        if session?.view.phase=="finished" {leave();return}
        session=nil;assessment=nil;hintText=nil;hintResponse=nil;shadowFeedback=nil
    }
    func continueCourse() async throws {
        guard let api else {return}
        if let id=UserDefaults.standard.string(forKey:"activeSession"+storageScope) {
            let restored:SessionState=try await api.request("v1/sessions/"+id)
            if !["finished","abandoned"].contains(restored.view.phase) {
                session=restored
                if restored.view.phase=="learning" {
                    selectedMaterial=restored.view.learningPractice?.materialIndex ?? restored.view.materials.indices.first { !(restored.view.completedMaterialIndices ?? []).contains($0) } ?? 0
                }
                let completed=restored.view.completedMaterialIndices ?? []
                selectedMaterial=restored.view.materials.indices.first { !completed.contains($0) } ?? max(0,restored.view.materials.count-1)
                return
            }
        }
        try await generate()
    }
    func leave() {
        session=nil;assessment=nil;pendingInput=nil;pendingUpload=nil;outgoingMessage=nil;pendingLearningRequest=nil;pendingLearningAudio=nil;pendingShadowRequest=nil;pendingShadowAudio=nil;hintText=nil;hintResponse=nil;translations=[:];shadowFeedback=nil;job=nil;activeJobKey=nil
        for key in ["activeSession","activeJob","pendingJobKey","pendingJobRequest","activeEntryKind"] {
            UserDefaults.standard.removeObject(forKey:key+storageScope)
        }
    }
}
