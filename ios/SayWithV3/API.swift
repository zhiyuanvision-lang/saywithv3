import Foundation
import Security

enum APIError: LocalizedError {
    case invalidURL, server(String), missingToken, loginExpired
    var errorDescription: String? {
        switch self {
        case .invalidURL: "请设置有效的后端服务地址。"
        case .server(let text): text
        case .missingToken: "请先登录。"
        case .loginExpired: "登录已失效，请重新登录。"
        }
    }
}

enum CredentialStore {
    private static func readRaw(account: String) -> String? {
        let query: [String: Any] = [kSecClass as String:kSecClassGenericPassword,
            kSecAttrService as String:"com.saywith.v3",kSecAttrAccount as String:account,
            kSecReturnData as String:true,kSecMatchLimit as String:kSecMatchLimitOne]
        var item: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &item) == errSecSuccess,
              let data = item as? Data else {return nil}
        return String(data:data,encoding:.utf8)
    }
    static func login(account: String) -> SavedLogin? {
        guard let raw=readRaw(account:account) else {return nil}
        return try? JSONDecoder().decode(SavedLogin.self,from:Data(raw.utf8))
    }
    static func read(account: String) -> String? {
        login(account:account)?.accessToken ?? readRaw(account:account)
    }
    static func save(_ login: SavedLogin, account: String) throws {
        let data=try JSONEncoder().encode(login)
        try save(String(decoding:data,as:UTF8.self),account:account)
    }
    static func delete(account: String) throws {
        let query:[String:Any]=[kSecClass as String:kSecClassGenericPassword,
            kSecAttrService as String:"com.saywith.v3",kSecAttrAccount as String:account]
        let status=SecItemDelete(query as CFDictionary)
        guard status == errSecSuccess || status == errSecItemNotFound else {
            throw APIError.server("无法清除登录凭据（\(status)）")
        }
    }
    static func save(_ token: String, account: String) throws {
        let query: [String: Any] = [kSecClass as String:kSecClassGenericPassword,
            kSecAttrService as String:"com.saywith.v3",kSecAttrAccount as String:account]
        var values = query
        values[kSecValueData as String] = Data(token.utf8)
        values[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        var status=SecItemUpdate(query as CFDictionary,[kSecValueData as String:Data(token.utf8),
            kSecAttrAccessible as String:kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly] as CFDictionary)
        if status == errSecItemNotFound {status=SecItemAdd(values as CFDictionary,nil)}
        guard status == errSecSuccess else {throw APIError.server("无法保存登录凭据（\(status)）")}
    }
}

actor API {
    let base: URL
    private var token: String?
    private var savedLogin: SavedLogin?
    private var refreshTask: Task<SavedLogin,Error>?
    private let session: URLSession
    private let transport:(@Sendable (URLRequest) async throws -> (Data,URLResponse))?
    init(base: URL, token: String?, transport:(@Sendable (URLRequest) async throws -> (Data,URLResponse))? = nil) {
        self.base = base; self.token = token
        self.transport=transport
        let stored=CredentialStore.login(account:base.absoluteString)
        if stored?.accessToken == token {savedLogin=stored}
        let config = URLSessionConfiguration.default
        config.waitsForConnectivity = true; config.timeoutIntervalForRequest = 120
        config.timeoutIntervalForResource = 180
        session = URLSession(configuration:config)
    }
    func authenticate(_ token: String) {self.token = token}
    func authenticate(_ login: SavedLogin) {savedLogin=login;token=login.accessToken}
    private func refreshLogin() async throws {
        if let refreshTask {let login=try await refreshTask.value;savedLogin=login;token=login.accessToken;return}
        guard let savedLogin else {throw APIError.loginExpired}
        let task=Task { () throws -> SavedLogin in
            let response:LoginResponse=try await self.request("v1/auth/token/refresh",method:"POST",
                body:["refresh_token":.string(savedLogin.refreshToken)],auth:false)
            guard response.userId == savedLogin.userId else {throw APIError.loginExpired}
            let login=SavedLogin(response)
            guard CredentialStore.login(account:self.base.absoluteString)?.refreshToken == savedLogin.refreshToken else {
                throw CancellationError()
            }
            try CredentialStore.save(login,account:self.base.absoluteString)
            return login
        }
        refreshTask=task
        defer {refreshTask=nil}
        do {let login=try await task.value;self.savedLogin=login;token=login.accessToken}
        catch APIError.loginExpired {expireLogin();throw APIError.loginExpired}
    }
    private func expireLogin() {
        let expired=savedLogin
        token=nil;savedLogin=nil
        // Keep the expired record in Keychain until explicit login/logout; it
        // remains distinguishable from an anonymous token and preserves scope.
        let account=base.absoluteString
        Task { @MainActor in
            if CredentialStore.login(account:account)?.refreshToken == expired?.refreshToken {
                NotificationCenter.default.post(name:.loginExpired,object:nil,userInfo:["baseURL":account])
            }
        }
    }
    private func execute(_ request:URLRequest) async throws -> (Data,URLResponse) {
        if let transport {return try await transport(request)}
        return try await session.data(for:request)
    }
    private func response(for request:URLRequest, auth:Bool) async throws -> (Data,URLResponse) {
        var req=request
        var sentToken:String?
        if auth {
            if savedLogin?.needsRefresh == true {try await refreshLogin()}
            guard let token else {throw APIError.missingToken}
            sentToken=token
            req.setValue("Bearer "+token,forHTTPHeaderField:"Authorization")
        }
        var result=try await execute(req)
        if auth, (result.1 as? HTTPURLResponse)?.statusCode == 401 {
            guard savedLogin != nil else {throw APIError.loginExpired}
            if token == sentToken {try await refreshLogin()}
            guard let token else {throw APIError.loginExpired}
            req.setValue("Bearer "+token,forHTTPHeaderField:"Authorization")
            result=try await execute(req)
            if (result.1 as? HTTPURLResponse)?.statusCode == 401 {expireLogin();throw APIError.loginExpired}
        }
        return result
    }
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
        key: String? = nil, auth: Bool = true, legacyToken:String? = nil) async throws -> T {
        var req = URLRequest(url:try endpoint(path)); req.httpMethod = method
        req.setValue("application/json",forHTTPHeaderField:"Content-Type")
        if let legacyToken {req.setValue(legacyToken,forHTTPHeaderField:"X-Learning-Token")}
        if let key {req.setValue(key,forHTTPHeaderField:"Idempotency-Key")}
        if let body {req.httpBody = try JSONEncoder().encode(body)}
        let (data,response) = try await response(for:req,auth:auth)
        if !auth,path != "v1/auth/token/refresh",(response as? HTTPURLResponse)?.statusCode == 401 {
            let detail=(try? JSONSerialization.jsonObject(with:data)) as? [String:Any]
            throw APIError.server(detail?["detail"] as? String ?? "验证码或授权凭证无效，请重试。")
        }
        try validate(response,data:data)
        let decoder = JSONDecoder(); decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(T.self,from:data)
    }
    private func validate(_ response: URLResponse, data: Data) throws {
        if (response as? HTTPURLResponse)?.statusCode == 401 {throw APIError.loginExpired}
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
        req.httpBody=body
        let (result,response) = try await response(for:req,auth:true)
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
        req.httpBody=body
        let (result,response)=try await response(for:req,auth:true);try validate(response,data:result)
        return try JSONDecoder().decode(FeedbackUpload.self,from:result)
    }
    func audio(_ ref: String) async throws -> Data {
        guard ref.hasPrefix("/v1/media/"), let token else {throw APIError.missingToken}
        var req=URLRequest(url:try endpoint(ref));req.setValue("Bearer "+token,forHTTPHeaderField:"Authorization")
        let (data,response)=try await response(for:req,auth:true);try validate(response,data:data);return data
    }
}
