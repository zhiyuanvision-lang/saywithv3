import XCTest
@testable import SayWithV3

private actor LoginTransport {
    var refreshCount=0
    var protectedCount=0
    let refreshStatus:Int
    let firstProtectedStatus:Int
    init(refreshStatus:Int=200,firstProtectedStatus:Int=200) {
        self.refreshStatus=refreshStatus;self.firstProtectedStatus=firstProtectedStatus
    }
    func send(_ request:URLRequest) async throws -> (Data,URLResponse) {
        let status:Int;let body:String
        if request.url!.path.hasSuffix("/token/refresh") {
            refreshCount+=1
            try await Task.sleep(for:.milliseconds(30))
            status=refreshStatus
            body=status == 200 ? #"{"user_id":"owner-a","display_name":"Tester","phone":"13800138000","access_token":"new-access","refresh_token":"new-refresh","expires_in":7200}"# : #"{"detail":"登录已失效"}"#
        } else {
            protectedCount+=1
            status=protectedCount == 1 ? firstProtectedStatus:200
            if status == 200 {
                guard request.value(forHTTPHeaderField:"Authorization") == "Bearer new-access" else {
                    throw APIError.server("Request used stale credentials")
                }
            }
            body=status == 200 ? #"{"status":"ok"}"# : #"{"detail":"登录已失效"}"#
        }
        return (Data(body.utf8),HTTPURLResponse(url:request.url!,statusCode:status,httpVersion:nil,headerFields:nil)!)
    }
}

final class AccountTests:XCTestCase {
    private func saved(expires:Int) throws -> SavedLogin {
        let decoder=JSONDecoder();decoder.keyDecodingStrategy = .convertFromSnakeCase
        let raw="""
        {"user_id":"owner-a","display_name":"Tester","phone":"13800138000","access_token":"old-access","refresh_token":"old-refresh","expires_in":\(expires)}
        """
        return SavedLogin(try decoder.decode(LoginResponse.self,from:Data(raw.utf8)))
    }
    func testKeychainRestoresBothTokensAndDeletesOnlyRequestedServiceAccount() throws {
        let a="https://keychain-a-\(UUID().uuidString).invalid"
        let b="https://keychain-b-\(UUID().uuidString).invalid"
        defer {try? CredentialStore.delete(account:a);try? CredentialStore.delete(account:b)}
        try CredentialStore.save(saved(expires:7200),account:a)
        try CredentialStore.save("anonymous-b",account:b)
        XCTAssertEqual(CredentialStore.read(account:a),"old-access")
        XCTAssertEqual(CredentialStore.login(account:a)?.refreshToken,"old-refresh")
        try CredentialStore.delete(account:a)
        XCTAssertNil(CredentialStore.read(account:a))
        XCTAssertEqual(CredentialStore.read(account:b),"anonymous-b")
        XCTAssertNil(CredentialStore.login(account:b))
    }
    @MainActor func testAccountResumeScopesAreDifferentOnSameServer() {
        XCTAssertNotEqual(LearningModel.accountStorageScope(baseURL:"https://example.invalid",userID:"a"),
                          LearningModel.accountStorageScope(baseURL:"https://example.invalid",userID:"b"))
    }
    func testConcurrentRequestsRefreshOnceAndPersistRotation() async throws {
        let base=URL(string:"https://refresh-\(UUID().uuidString).invalid")!
        defer {try? CredentialStore.delete(account:base.absoluteString)}
        try CredentialStore.save(saved(expires:-1),account:base.absoluteString)
        let transport=LoginTransport()
        let api=API(base:base,token:"old-access",transport:{try await transport.send($0)})
        async let a:LogoutResponse=api.request("v1/test-a")
        async let b:LogoutResponse=api.request("v1/test-b")
        let results=try await (a,b)
        XCTAssertEqual(results.0.status,"ok");XCTAssertEqual(results.1.status,"ok")
        let refreshCount=await transport.refreshCount
        XCTAssertEqual(refreshCount,1)
        XCTAssertEqual(CredentialStore.login(account:base.absoluteString)?.refreshToken,"new-refresh")
        // Simulates restarting the client on the same device.
        let restarted=API(base:base,token:CredentialStore.read(account:base.absoluteString),transport:{try await transport.send($0)})
        let _:LogoutResponse=try await restarted.request("v1/test-c")
        let afterRestart=await transport.refreshCount
        XCTAssertEqual(afterRestart,1)
    }
    func testUnauthorizedAccessRefreshesAndRetriesOriginalRequest() async throws {
        let base=URL(string:"https://retry-\(UUID().uuidString).invalid")!
        defer {try? CredentialStore.delete(account:base.absoluteString)}
        try CredentialStore.save(saved(expires:7200),account:base.absoluteString)
        let transport=LoginTransport(firstProtectedStatus:401)
        let api=API(base:base,token:"old-access",transport:{try await transport.send($0)})
        let response:LogoutResponse=try await api.request("v1/test")
        XCTAssertEqual(response.status,"ok")
        let count=await transport.protectedCount
        XCTAssertEqual(count,2)
    }
    func testNetworkFailureKeepsRefreshCredential() async throws {
        let base=URL(string:"https://offline-\(UUID().uuidString).invalid")!
        defer {try? CredentialStore.delete(account:base.absoluteString)}
        try CredentialStore.save(saved(expires:-1),account:base.absoluteString)
        let api=API(base:base,token:"old-access",transport:{_ in throw URLError(.notConnectedToInternet)})
        do {let _:LogoutResponse=try await api.request("v1/test");XCTFail("Must fail offline")}
        catch {XCTAssertEqual((error as? URLError)?.code,.notConnectedToInternet)}
        XCTAssertEqual(CredentialStore.login(account:base.absoluteString)?.refreshToken,"old-refresh")
    }
    func testRevokedRefreshDoesNotReachPrivateEndpoint() async throws {
        let base=URL(string:"https://revoked-\(UUID().uuidString).invalid")!
        defer {try? CredentialStore.delete(account:base.absoluteString)}
        try CredentialStore.save(saved(expires:-1),account:base.absoluteString)
        let transport=LoginTransport(refreshStatus:401)
        let api=API(base:base,token:"old-access",transport:{try await transport.send($0)})
        do {let _:LogoutResponse=try await api.request("v1/test");XCTFail("Revoked refresh must require login")}
        catch APIError.loginExpired {} catch {XCTFail("Unexpected error: \(error)")}
        let count=await transport.protectedCount
        XCTAssertEqual(count,0)
    }
}
