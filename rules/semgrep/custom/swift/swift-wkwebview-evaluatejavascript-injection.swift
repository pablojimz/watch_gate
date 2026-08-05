import WebKit

class Example {
    func bad1(webView: WKWebView, username: String) {
        // ruleid: swift-wkwebview-evaluatejavascript-injection
        webView.evaluateJavaScript("showUser('\(username)')")
    }

    func bad2(webView: WKWebView, script: String) {
        // ruleid: swift-wkwebview-evaluatejavascript-injection
        webView.evaluateJavaScript(script, completionHandler: nil)
    }

    func ok1(webView: WKWebView) {
        // ok: swift-wkwebview-evaluatejavascript-injection
        webView.evaluateJavaScript("document.title")
    }
}
