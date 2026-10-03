import Foundation

struct LoginResponse: Decodable, Sendable {
    let userId: String
    let displayName: String
    let phone: String
    let accessToken: String
    let refreshToken: String
    let expiresIn: Int
    let adoptedAnonymous: Bool?
}

struct SavedLogin: Codable, Sendable {
    let userId: String
    let displayName: String
    let phone: String
    let accessToken: String
    let refreshToken: String
    let expiresAt: Date

    init(_ response: LoginResponse) {
        userId=response.userId;displayName=response.displayName;phone=response.phone
        accessToken=response.accessToken;refreshToken=response.refreshToken
        expiresAt=Date().addingTimeInterval(TimeInterval(response.expiresIn))
    }
    var needsRefresh: Bool {expiresAt.timeIntervalSinceNow < 60}
}

struct AccountStatus: Decodable, Sendable {let userId:String;let verified:Bool}
struct LoginMethods: Decodable, Sendable {let sms:Bool;let wechat:Bool;let apple:Bool}
struct SMSDelivery: Decodable, Sendable {let retryAfter:Int}
struct LogoutResponse: Decodable, Sendable {let status:String}

extension Notification.Name {
    static let loginExpired=Notification.Name("SayWithLoginExpired")
}
