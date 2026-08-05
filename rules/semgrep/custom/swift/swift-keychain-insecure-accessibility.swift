import Security

func bad1() {
    let query: [String: Any] = [
        kSecClass as String: kSecClassGenericPassword,
        // ruleid: swift-keychain-insecure-accessibility
        kSecAttrAccessible as String: kSecAttrAccessibleAlways
    ]
}

func ok1() {
    let query: [String: Any] = [
        kSecClass as String: kSecClassGenericPassword,
        // ok: swift-keychain-insecure-accessibility
        kSecAttrAccessible as String: kSecAttrAccessibleWhenUnlockedThisDeviceOnly
    ]
}
