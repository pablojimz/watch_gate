import CryptoKit

func bad1(data: Data) {
    // ruleid: swift-weak-hash-algorithm
    let digest = Insecure.MD5.hash(data: data)
}

func bad2(data: Data) {
    // ruleid: swift-weak-hash-algorithm
    let digest = Insecure.SHA1.hash(data: data)
}

func ok1(data: Data) {
    // ok: swift-weak-hash-algorithm
    let digest = SHA256.hash(data: data)
}
