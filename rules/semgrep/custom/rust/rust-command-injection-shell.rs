use std::process::Command;

fn bad1(user_input: &str) {
    // ruleid: rust-command-injection-shell
    Command::new("sh").arg("-c").arg(user_input).output().unwrap();
}

fn bad2(user_input: String) {
    // ruleid: rust-command-injection-shell
    Command::new("bash").arg("-c").arg(user_input).output().unwrap();
}

fn ok1() {
    // ok: rust-command-injection-shell
    Command::new("sh").arg("-c").arg("uptime").output().unwrap();
}

fn ok2(user_dir: &str) {
    // ok: rust-command-injection-shell
    Command::new("ls").arg(user_dir).output().unwrap();
}
