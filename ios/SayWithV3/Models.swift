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
}
struct LessonView: Decodable, Sendable {
    let sessionId: String; let lessonId: String; let lessonVersion: Int; let taskId: String
    let phase: String; let instruction: String; let learnerFacts: [String: JSONValue]
    let availableActions: [String]; let materials: [Material]; let fixture: Bool
    let completedMaterialIndices: [Int]?
}
struct Turn: Decodable, Identifiable, Sendable {
    let turnId: String; let speaker: String; let text: String?; let transcript: String?; let audioRef: String?
    var id: String {turnId}; var content: String {text ?? transcript ?? ""}
}
struct SessionState: Decodable, Sendable { let view: LessonView; let sessionVersion: Int; let turns: [Turn] }
struct Dialogue: Decodable, Sendable { let text: String; let audioRef: String? }
struct AudioUpload: Decodable, Sendable { let audioRef: String }
struct Assessment: Decodable, Sendable {
    let assessmentId: String; let targetResults: [[String: JSONValue]]; let validation: [String: JSONValue]
    var summary: String {
        guard validation["status"]?.text == "accepted" else { return "本次证据不足，暂不更新能力。" }
        switch targetResults.first?["result"]?.text {
        case "completed": return "本次任务已完成。后续还会检查保持与迁移。"
        case "partial": return "已完成部分目标，下一次继续补练。"
        case "failed": return "本次关键意义尚未表达清楚，将安排补练。"
        default: return "还需要更多表现证据。"
        }
    }
}
