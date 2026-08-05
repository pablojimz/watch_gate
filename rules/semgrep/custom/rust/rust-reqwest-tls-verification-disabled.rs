fn bad1() {
    // ruleid: rust-reqwest-tls-verification-disabled
    let client = reqwest::Client::builder()
        .danger_accept_invalid_certs(true)
        .build()
        .unwrap();
}

fn bad2() {
    // ruleid: rust-reqwest-tls-verification-disabled
    let client = reqwest::Client::builder()
        .danger_accept_invalid_hostnames(true)
        .build()
        .unwrap();
}

fn ok1() {
    // ok: rust-reqwest-tls-verification-disabled
    let client = reqwest::Client::builder()
        .danger_accept_invalid_certs(false)
        .build()
        .unwrap();
}
