import java.sql.Statement;
import java.sql.ResultSet;

class Example {
    void bad1(Statement stmt, String userId) throws Exception {
        // ruleid: java-sql-injection-statement
        ResultSet rs = stmt.executeQuery("SELECT * FROM users WHERE id = " + userId);
    }

    void bad2(Statement stmt, String name) throws Exception {
        // ruleid: java-sql-injection-statement
        stmt.executeUpdate("DELETE FROM users WHERE name = '" + name + "'");
    }

    void ok1(Statement stmt) throws Exception {
        // ok: java-sql-injection-statement
        ResultSet rs = stmt.executeQuery("SELECT * FROM users");
    }
}
