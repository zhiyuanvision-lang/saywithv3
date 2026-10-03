import AuthenticationServices
import UIKit

@MainActor
enum AppleAuth {
    struct Identity {let identityToken:String;let fullName:String}
    private static var retained:Proxy?
    static func requestIdentity() async throws -> Identity {
        guard retained == nil else {throw NSError(domain:"AppleAuth",code:1,userInfo:[NSLocalizedDescriptionKey:"正在等待 Apple 授权。"])}
        let request=ASAuthorizationAppleIDProvider().createRequest()
        request.requestedScopes=[.fullName]
        let controller=ASAuthorizationController(authorizationRequests:[request])
        let proxy=Proxy(controller:controller)
        retained=proxy;controller.delegate=proxy;controller.presentationContextProvider=proxy
        return try await withCheckedThrowingContinuation {continuation in
            proxy.finish={result in retained=nil;continuation.resume(with:result)}
            controller.performRequests()
        }
    }
    private final class Proxy:NSObject,ASAuthorizationControllerDelegate,ASAuthorizationControllerPresentationContextProviding {
        let controller:ASAuthorizationController
        var finish:((Result<Identity,Error>)->Void)?
        init(controller:ASAuthorizationController) {self.controller=controller}
        func presentationAnchor(for controller:ASAuthorizationController)->ASPresentationAnchor {
            UIApplication.shared.connectedScenes.compactMap {$0 as? UIWindowScene}.flatMap(\.windows).first(where:\.isKeyWindow) ?? ASPresentationAnchor()
        }
        func authorizationController(controller:ASAuthorizationController,didCompleteWithAuthorization authorization:ASAuthorization) {
            defer {finish=nil}
            guard let credential=authorization.credential as? ASAuthorizationAppleIDCredential,
                  let data=credential.identityToken,let token=String(data:data,encoding:.utf8),!token.isEmpty else {
                finish?(.failure(NSError(domain:"AppleAuth",code:2,userInfo:[NSLocalizedDescriptionKey:"Apple 未返回登录凭证，请重试。"])))
                return
            }
            finish?(.success(Identity(identityToken:token,fullName:[credential.fullName?.familyName,credential.fullName?.givenName].compactMap {$0}.joined())))
        }
        func authorizationController(controller:ASAuthorizationController,didCompleteWithError error:Error) {
            defer {finish=nil};finish?(.failure(error))
        }
    }
}

