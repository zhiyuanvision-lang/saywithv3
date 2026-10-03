import Foundation
import Security

enum APIError: LocalizedError {
    case invalidURL, server(String), missingToken
    var errorDescription: String? {
        switch self {
        case .invalidURL: "请设置有效的后端服务地址。"
        case .server(let text): text
        case .missingToken: "请先建立学习账号。"
        }
    }
}

enum CredentialStore {
    static func read(account: String) -> String? {
        let query: [String: Any] = [kSecClass as String:kSecClassGenericPassword,
            kSecAttrService as String:"com.saywith.v3",kSecAttrAccount as String:account,
            kSecReturnData as String:true,kSecMatchLimit as String:kSecMatchLimitOne]
        var item: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &item) == errSecSuccess,
              let data = item as? Data else {return nil}
        return String(data:data,encoding:.utf8)
    }
    static func save(_ token: String, account: String) throws {
        let query: [String: Any] = [kSecClass as String:kSecClassGenericPassword,
            kSecAttrService as String:"com.saywith.v3",kSecAttrAccount as String:account]
        var values = query
        values[kSecValueData as String] = Data(token.utf8)
        values[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        var status=SecItemUpdate(query as CFDictionary,[kSecValueData as String:Data(token.utf8)] as CFDictionary)
        if status == errSecItemNotFound {status=SecItemAdd(values as CFDictionary,nil)}
        guard status == errSecSuccess else {throw APIError.server("无法保存登录凭据（\(status)）")}
    }
}

actor API {
    let base: URL
    private var token: String?
    private let session: URLSession
    init(base: URL, token: String?) {
        self.base = base; self.token = token
        let config = URLSessionConfiguration.default
        config.waitsForConnectivity = true; config.timeoutIntervalForRequest = 120
        config.timeoutIntervalForResource = 180
        session = URLSession(configuration:config)
    }
    func authenticate(_ token: String) {self.token = token}
    func endpoint(_ path: String) throws -> URL {
        guard let relative = URLComponents(string:path), relative.host == nil, relative.scheme == nil,
              !relative.path.split(separator:"/").contains(".."),
              var result = URLComponents(url:base,resolvingAgainstBaseURL:false) else {throw APIError.invalidURL}
        result.path = base.path.trimmingCharacters(in:CharacterSet(charactersIn:"/"))
        result.path = "/" + ([result.path,relative.path.trimmingCharacters(in:CharacterSet(charactersIn:"/"))].filter {!$0.isEmpty}.joined(separator:"/"))
        result.query = relative.query
        guard let url = result.url else {throw APIError.invalidURL}
        return url
    }
    static func validatedURL(_ raw: String) throws -> URL {
        guard let url = URL(string: raw.trimmingCharacters(in:.whitespacesAndNewlines)),
              let host = url.host, url.user == nil, url.password == nil,
              ["","/","/learning","/learning/"].contains(url.path), url.query == nil, url.fragment == nil else {throw APIError.invalidURL}
        if url.scheme == "https" {return url}
        #if DEBUG
        if url.scheme == "http", ["localhost","127.0.0.1"].contains(host) || host.hasSuffix(".local") {return url}
        #endif
        throw APIError.invalidURL
    }
    func request<T: Decodable & Sendable>(_ path: String, method: String = "GET", body: [String: JSONValue]? = nil,
        key: String? = nil, auth: Bool = true) async throws -> T {
        var req = URLRequest(url:try endpoint(path)); req.httpMethod = method
        req.setValue("application/json",forHTTPHeaderField:"Content-Type")
        if auth {
            guard let token else {throw APIError.missingToken}
            req.setValue("Bearer " + token,forHTTPHeaderField:"Authorization")
        }
        if let key {req.setValue(key,forHTTPHeaderField:"Idempotency-Key")}
        if let body {req.httpBody = try JSONEncoder().encode(body)}
        let (data,response) = try await session.data(for:req)
        try validate(response,data:data)
        let decoder = JSONDecoder(); decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(T.self,from:data)
    }
    private func validate(_ response: URLResponse, data: Data) throws {
        guard let r = response as? HTTPURLResponse, (200..<300).contains(r.statusCode) else {
            let detail = (try? JSONSerialization.jsonObject(with:data)) as? [String:Any]
            throw APIError.server(detail?["detail"] as? String ?? "请求未成功，请稍后重试。")
        }
    }
    func upload(_ data: Data) async throws -> AudioUpload {
        guard let token else {throw APIError.missingToken}
        let boundary = UUID().uuidString
        var body = Data("--\(boundary)\r\nContent-Disposition: form-data; name=\"audio\"; filename=\"recording.wav\"\r\nContent-Type: audio/wav\r\n\r\n".utf8)
        body.append(data); body.append(Data("\r\n--\(boundary)--\r\n".utf8))
        var req = URLRequest(url:try endpoint("v1/media")); req.httpMethod = "POST"
        req.setValue("Bearer " + token,forHTTPHeaderField:"Authorization")
        req.setValue("multipart/form-data; boundary=\(boundary)",forHTTPHeaderField:"Content-Type")
        let (result,response) = try await session.upload(for:req,from:body)
        try validate(response,data:result)
        let decoder=JSONDecoder();decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(AudioUpload.self,from:result)
    }
    func feedbackImage(_ data:Data) async throws -> FeedbackUpload {
        guard let token else {throw APIError.missingToken}
        let boundary=UUID().uuidString
        var body=Data("--\(boundary)\r\nContent-Disposition: form-data; name=\"file\"; filename=\"feedback.jpg\"\r\nContent-Type: image/jpeg\r\n\r\n".utf8)
        body.append(data);body.append(Data("\r\n--\(boundary)--\r\n".utf8))
        var req=URLRequest(url:try endpoint("v1/feedback/images"));req.httpMethod="POST"
        req.setValue("Bearer "+token,forHTTPHeaderField:"Authorization")
        req.setValue("multipart/form-data; boundary=\(boundary)",forHTTPHeaderField:"Content-Type")
        let (result,response)=try await session.upload(for:req,from:body);try validate(response,data:result)
        return try JSONDecoder().decode(FeedbackUpload.self,from:result)
    }
    func audio(_ ref: String) async throws -> Data {
        guard ref.hasPrefix("/v1/media/"), let token else {throw APIError.missingToken}
        var req=URLRequest(url:try endpoint(ref));req.setValue("Bearer "+token,forHTTPHeaderField:"Authorization")
        let (data,response)=try await session.data(for:req);try validate(response,data:data);return data
    }
}
