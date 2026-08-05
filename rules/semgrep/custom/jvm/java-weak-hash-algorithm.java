import java.security.MessageDigest;

class Example {
    void bad1() throws Exception {
        // ruleid: java-weak-hash-algorithm
        MessageDigest md = MessageDigest.getInstance("MD5");
    }

    void bad2() throws Exception {
        // ruleid: java-weak-hash-algorithm
        MessageDigest md = MessageDigest.getInstance("SHA-1");
    }

    void ok1() throws Exception {
        // ok: java-weak-hash-algorithm
        MessageDigest md = MessageDigest.getInstance("SHA-256");
    }
}
