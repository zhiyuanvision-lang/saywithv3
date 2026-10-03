import Foundation
import Observation

@MainActor @Observable
final class LearningModel {
    static var defaultBackendURL: String {
        #if targetEnvironment(simulator)
        return "http://localhost:8083"
        #else
        let configured=Bundle.main.object(forInfoDictionaryKey:"SayWithBackendURL") as? String ?? ""
        return configured.hasPrefix("http://") || configured.hasPrefix("https://") ? configured : ""
        #endif
    }
    var baseURL = UserDefaults.standard.string(forKey:"backendURL") ?? LearningModel.defaultBackendURL
    var stage = "A2"
    var context = "校园与日常生活"
    var targets: [Target] = []
    var profile: Profile?
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
    private var api: API?
    private var activeJobKey: String?
    private var storageScope: String { "-" + (apiScope ?? baseURL) }
    private var apiScope: String?
    private var pendingInput: [String: JSONValue]?
    var hasAccount: Bool {profile != nil}

    func perform(_ operation: () async throws -> Void) async {
        guard !busy else {return}
        busy=true;error=nil
        defer {busy=false}
        do {try await operation()}
        catch is CancellationError {}
        catch {self.error=error.localizedDescription}
    }
    func connect(create: Bool = false, savePreferences: Bool = false) async throws {
        let url=try API.validatedURL(baseURL)
        let client=API(base:url,token:CredentialStore.read(account:url.absoluteString))
        let loadedHealth: Health=try await client.request("health",auth:false)
        if create {
            let registration: Registration=try await client.request("v1/users",method:"POST",body:[
                "context":.string(context),"reference_stage":.string(stage),"interests":.array([])],auth:false)
            try CredentialStore.save(registration.accessToken,account:url.absoluteString)
            await client.authenticate(registration.accessToken)
        }
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
        let list: TargetList=try await client.request("v1/curriculum/targets?stage="+stage)
        if apiScope != url.absoluteString {session=nil;job=nil;assessment=nil;pendingInput=nil}
        targets=list.targets;api=client;profile=connected;health=loadedHealth;apiScope=url.absoluteString
        if create {session=nil;job=nil;assessment=nil;pendingInput=nil;activeJobKey=nil}
        else {
            activeJobKey=UserDefaults.standard.string(forKey:"pendingJobKey"+storageScope)
            if let id=UserDefaults.standard.string(forKey:"activeJob"+storageScope) {
                job=try await client.request("v1/course-generation-jobs/"+id)
            }
        }
        UserDefaults.standard.set(baseURL,forKey:"backendURL")
        if !create, let id=UserDefaults.standard.string(forKey:"activeSession"+storageScope) {
            do {
                session=try await client.request("v1/sessions/"+id)
                if let view=session?.view, view.phase == "learning" {
                    let completed=view.completedMaterialIndices ?? []
                    selectedMaterial=view.materials.indices.first { !completed.contains($0) } ?? max(0,view.materials.count-1)
                    answerVisible=true;personalText=""
                }
            } catch {session=nil}
        }
    }
    func refresh() async throws {
        guard let api else {return}
        profile=try await api.request("v1/profile")
        let list:TargetList=try await api.request("v1/curriculum/targets?stage="+stage);targets=list.targets
    }
    func generate(target: Target? = nil) async throws {
        guard let api,let profile else {throw APIError.missingToken}
        if job?.terminal != false {
            let key=activeJobKey ?? UUID().uuidString;activeJobKey=key
            UserDefaults.standard.set(key,forKey:"pendingJobKey"+storageScope)
            var request:[String:JSONValue]=["minutes":.number(10),"context":.string(context),"profile_version":.number(Double(profile.profileVersion))]
            if let target {request["target_id"] = .string(target.targetId)}
            else if health?.mode == "fixture" {request["target_id"] = .string("ARRANGE.A2.s2")}
            if let saved=UserDefaults.standard.data(forKey:"pendingJobRequest"+storageScope), activeJobKey != nil {
                request=try JSONDecoder().decode([String:JSONValue].self,from:saved)
            } else {
                UserDefaults.standard.set(try JSONEncoder().encode(request),forKey:"pendingJobRequest"+storageScope)
            }
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
                        session=try await api.request("v1/sessions",method:"POST",body:["lesson_id":.string(lesson)])
                    }
                    if let session {UserDefaults.standard.set(session.view.sessionId,forKey:"activeSession"+storageScope)}
                    selectedMaterial=0;answerVisible=true;assessment=nil
                } else {throw APIError.server(current.error?["message"]?.text ?? "课程暂未就绪，请重试。")}
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
        session=try await api.request("v1/sessions/"+current.view.sessionId+"/next",method:"POST",body:["expected_session_version":.number(Double(current.sessionVersion))])
        personalText="";answerVisible=true;typedReply=""
    }
    func send(kind: String, audio: Data? = nil) async throws {
        guard let api,let current=session else {return}
        if pendingInput == nil {
            var body:[String:JSONValue]=["schema_version":.string("1.0"),"session_id":.string(current.view.sessionId),
                "task_id":.string(current.view.taskId),"input_id":.string(UUID().uuidString),"type":.string(kind),
                "recorded_at":.string(ISO8601DateFormatter().string(from:Date())),
                "expected_session_version":.number(Double(current.sessionVersion))]
            if let audio {
                let uploaded=try await api.upload(audio);body["audio_ref"] = .string(uploaded.audioRef)
            } else if kind == "text" {body["text"] = .string(typedReply)}
            pendingInput=body
        }
        let _:Dialogue=try await api.request("v1/sessions/"+current.view.sessionId+"/inputs",method:"POST",body:pendingInput)
        pendingInput=nil;typedReply=""
        session=try await api.request("v1/sessions/"+current.view.sessionId)
    }
    func retryInput() async throws {try await send(kind:"text")}
    var hasPendingInput: Bool {pendingInput != nil}
    func finish() async throws {
        guard let api,let current=session else {return}
        assessment=try await api.request("v1/sessions/"+current.view.sessionId+"/finish",method:"POST")
        session=try await api.request("v1/sessions/"+current.view.sessionId)
        try await refresh()
    }
    func sound(_ ref: String) async throws -> Data {
        guard let api else {throw APIError.missingToken}
        return try await api.audio(ref)
    }
    func leave() {
        session=nil;assessment=nil;pendingInput=nil;job=nil;activeJobKey=nil
        for key in ["activeSession","activeJob","pendingJobKey","pendingJobRequest"] {
            UserDefaults.standard.removeObject(forKey:key+storageScope)
        }
    }
}
