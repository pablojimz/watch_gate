use std::ffi::CString;

fn bad1(user_input: &str) {
    // ruleid: rust-libc-system-command-injection
    let cmd = CString::new(user_input).unwrap();
    unsafe {
        libc::system(cmd.as_ptr());
    }
}

fn ok1() {
    // ok: rust-libc-system-command-injection
    let cmd = CString::new("uptime").unwrap();
    unsafe {
        libc::system(cmd.as_ptr());
    }
}
