import Foundation

enum JSONValue: Codable, Sendable {
    case string(String), number(Double), bool(Bool), array([JSONValue]), object([String: JSONValue]), null
    init(from decoder: Decoder) throws {
        let c = try decoder.singleValueContainer()
        if c.decodeNil() { self = .null }
        else if let v = try? c.decode(String.self) { self = .string(v) }
        else if let v = try? c.decode(Bool.self) { self = .bool(v) }
        else if let v = try? c.decode(Double.self) { self = .number(v) }
        else if let v = try? c.decode([JSONValue].self) { self = .array(v) }
        else { self = .object(try c.decode([String: JSONValue].self)) }
    }
    func encode(to encoder: Encoder) throws {
        var c = encoder.singleValueContainer()
        switch self {
        case .string(let v): try c.encode(v)
        case .number(let v): try c.encode(v)
        case .bool(let v): try c.encode(v)
        case .array(let v): try c.encode(v)
        case .object(let v): try c.encode(v)
        case .null: try c.encodeNil()
        }
    }
    var text: String {
        switch self {
        case .string(let v): v
        case .number(let v): String(v)
        case .bool(let v): String(v)
        case .array(let v): v.map(\.text).joined(separator: "、")
        case .object(let v): v.sorted(by: {$0.key < $1.key}).map {"\($0.key)：\($0.value.text)"}.joined(separator: "\n")
        case .null: ""
        }
    }
}

struct Target: Codable, Identifiable, Sendable {
    let targetId: String; let outcome: String; let referenceStage: String
    var id: String { targetId }
}
struct TargetList: Decodable, Sendable { let mapVersion: String; let targets: [Target] }
struct Profile: Decodable, Sendable {
    let userId: String; let profileVersion: Int
    let targetStates: [[String: JSONValue]]; let resourceStates: [[String: JSONValue]]
    let preferences: [String: JSONValue]
}
struct Registration: Decodable, Sendable { let userId: String; let accessToken: String; let profile: Profile }
struct Health: Decodable, Sendable { let mode: String; let mapVersion: String }
struct Job: Decodable, Sendable {
    let jobId: String; let state: String; let rowVersion: Int
    let resultLessonId: String?; let reason: String?; let error: [String: JSONValue]?
    var terminal: Bool { ["approved", "preview_ready", "needs_review", "failed", "cancelled"].contains(state) }
    var label: String {
        ["queued":"等待生成", "planning":"选择学习目标", "generating_text":"生成学习内容", "checking_text":"检查任务与表达", "generating_audio":"生成声音", "checking_audio":"检查声音", "approved":"课程已就绪", "preview_ready":"测试课程已就绪", "needs_review":"课程需要审核", "failed":"生成暂未成功", "cancelled":"生成已取消"][state] ?? state
    }
}
struct Material: Decodable, Sendable {
    let intentZh: String; let expression: String; let audioRef: String?
    let explanationZh: String; let personalPromptZh: String
    let meaningZh: String?;let hintPattern: String?
}
struct LessonView: Decodable, Sendable {
    let entryKind:String?;let reviewMetadata:[String:JSONValue]?
    let sessionId: String; let lessonId: String; let lessonVersion: Int; let taskId: String
    let phase: String; let instruction: String; let learnerFacts: [String: JSONValue]
    let availableActions: [String]; let materials: [Material]; let fixture: Bool
    let lexicalPractices:[LexicalPracticeView]?
    let completedMaterialIndices: [Int]?
    let title:String?;let partnerName:String?;let demonstration:[DemoLine]?
    let guidedRound:Int?;let guidedRoundTitle:String?;let supportUsed:[String]?
    let shadowFeedback:ShadowFeedback?;let assessment:Assessment?
}
struct Turn: Decodable, Identifiable, Sendable {
    let turnId: String; let speaker: String; let text: String?; let transcript: String?; let audioRef: String?
    var id: String {turnId}; var content: String {text ?? transcript ?? ""}
}
struct SessionState: Decodable, Sendable { let view: LessonView; let sessionVersion: Int; let turns: [Turn] }
struct Dialogue: Decodable, Sendable { let text:String;let audioRef:String?;let kind:String?;let supportProvided:[String]? }
struct DemoLine:Decodable,Sendable {let speaker:String;let text:String;let meaningZh:String?;let audioRef:String?}
struct ShadowFeedback:Decodable,Sendable {let transcript:String;let canContinue:Bool;let message:String;let audioRef:String;let materialIndex:Int
    func materialIndexMatches(_ index:Int)->Bool {materialIndex==index}}
struct ShadowResponse:Decodable,Sendable {let feedback:ShadowFeedback;let session:SessionState}
struct AudioUpload: Decodable, Sendable { let audioRef: String }
struct Assessment: Decodable, Sendable {
    let assessmentId: String; let targetResults: [[String: JSONValue]]; let validation: [String: JSONValue]
    var failureExplanation:String {
        let reasons=validation["checks"]?.text ?? ""
        if reasons.contains("测试用例") {return "这是测试内容，本次不计入能力记录。"}
        if reasons.contains("模型评价结构") || reasons.contains("关键检查未全部评价") {return "系统未能完成本次评价。这不代表你不会表达，本次没有改动能力记录。"}
        if reasons.contains("音频") || reasons.contains("录音") {return "本次录音或识别结果不足以确认表现，请回听后再试。"}
        return "本次还无法可靠确认表现，能力记录保持不变。"
    }
    var summary: String {
        guard validation["status"]?.text == "accepted" else { return failureExplanation }
        switch targetResults.first?["result"]?.text {
        case "completed": return "本次任务已完成。后续还会检查保持与迁移。"
        case "partial": return "已完成部分目标，下一次继续补练。"
        case "failed": return "本次关键意义尚未表达清楚，将安排补练。"
        default: return "还需要更多表现证据。"
        }
    }
}

struct ReviewRecommendation:Decodable,Sendable,Identifiable {
    let targetId:String;let title:String;let minutes:Int;let reason:String;let taskCount:Int?
    var id:String {targetId}
}
struct Recommendations:Decodable,Sendable {let recommended:ReviewRecommendation?;let dueCount:Int;let learned:[ReviewRecommendation];let nextLearning:ReviewRecommendation?}

struct InputProgress:Decodable,Sendable {
    let inputId:String;let sessionId:String;let turnId:String;let status:String
    let transcript:String?;let audioRef:String?
}
struct OutgoingMessage:Identifiable,Sendable {
    let id:String
    var turnId:String?;var text:String?;var stage:String;var audioRef:String?
    var statusText:String {
        switch stage {
        case "uploading":return "正在发送录音"
        case "recognizing":return "正在识别语音"
        case "failed":return "发送未完成，可重试"
        default:return "正在等待对方回应"
        }
    }
}
