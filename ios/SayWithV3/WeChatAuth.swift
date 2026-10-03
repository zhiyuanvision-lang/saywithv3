import Foundation
import UIKit
@preconcurrency import WechatOpenSDK

@MainActor
final class WeChatAuth: NSObject, WXApiDelegate {
    static let shared=WeChatAuth()
    static let appID="wxb9dff3017930c9ee"
    private var continuation:CheckedContinuation<String,Error>?
    private var timeout:Task<Void,Never>?
    private var state=""

    @discardableResult func registerIfConfigured()->Bool {
        WXApi.registerApp(Self.appID,universalLink:"https://saywith.zhiyuanv.com/app/")
    }
    var isAvailable:Bool {WXApi.isWXAppInstalled()}
    func requestCode() async throws -> String {
        guard isAvailable else {throw APIError.server("这台设备没有微信，请使用手机号或Apple登录。")}
        guard continuation == nil else {throw APIError.server("微信授权正在进行中。")}
        return try await withCheckedThrowingContinuation {continuation in
            self.continuation=continuation;state=UUID().uuidString
            timeout=Task { [weak self] in
                do {try await Task.sleep(for:.seconds(60))} catch {return}
                self?.finish(.failure(APIError.server("微信授权超时，请重试。")))
            }
            let req=SendAuthReq();req.scope="snsapi_userinfo";req.state=state
            let scenes=UIApplication.shared.connectedScenes.compactMap {$0 as? UIWindowScene}
            guard var controller=scenes.flatMap(\.windows).first(where:\.isKeyWindow)?.rootViewController else {
                finish(.failure(APIError.server("无法打开微信授权。")));return
            }
            while let presented=controller.presentedViewController {controller=presented}
            WXApi.sendAuthReq(req,viewController:controller,delegate:self) { [weak self] ok in
                Task { @MainActor in if !ok {self?.finish(.failure(APIError.server("无法拉起微信，请重试。")))}}
            }
        }
    }
    @discardableResult func handleOpen(url:URL)->Bool {WXApi.handleOpen(url,delegate:self)}
    @discardableResult func handleUniversalLink(_ activity:NSUserActivity)->Bool {
        WXApi.handleOpenUniversalLink(activity,delegate:self)
    }
    private func finish(_ result:Result<String,Error>) {
        timeout?.cancel();timeout=nil
        guard let continuation else {return}
        self.continuation=nil;state="";continuation.resume(with:result)
    }
    nonisolated func onReq(_ req:BaseReq) {}
    nonisolated func onResp(_ resp:BaseResp) {
        guard let auth=resp as? SendAuthResp else {return}
        let errorCode=auth.errCode;let returnedState=auth.state;let code=auth.code
        Task { @MainActor [weak self] in
            guard let self,!state.isEmpty else {return}
            if let returnedState,returnedState != state {return}
            if errorCode == 0 {
                guard returnedState == state,let code,!code.isEmpty else {return}
                finish(.success(code))
            } else if errorCode == -2 {finish(.failure(CancellationError()))}
            else {finish(.failure(APIError.server("微信授权失败，请重试。")))}
        }
    }
    nonisolated func onNeedGrantReadPasteBoardPermission(with openURL:URL,completion:@escaping WXGrantReadPasteBoardPermissionCompletion) {_ = completion()}
}
