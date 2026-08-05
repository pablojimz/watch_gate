import Foundation

class Bad: NSObject, URLSessionDelegate {
    func urlSession(_ session: URLSession, didReceive challenge: URLAuthenticationChallenge, completionHandler: @escaping (URLSession.AuthChallengeDisposition, URLCredential?) -> Void) {
        let credential = URLCredential(trust: challenge.protectionSpace.serverTrust!)
        // ruleid: swift-urlsession-certificate-pinning-bypass
        completionHandler(.useCredential, URLCredential(trust: challenge.protectionSpace.serverTrust!))
    }
}

class Good: NSObject, URLSessionDelegate {
    func urlSession(_ session: URLSession, didReceive challenge: URLAuthenticationChallenge, completionHandler: @escaping (URLSession.AuthChallengeDisposition, URLCredential?) -> Void) {
        guard let pinnedCredential = self.validatePinning(challenge) else {
            completionHandler(.cancelAuthenticationChallenge, nil)
            return
        }
        // ok: swift-urlsession-certificate-pinning-bypass
        completionHandler(.useCredential, pinnedCredential)
    }
}
