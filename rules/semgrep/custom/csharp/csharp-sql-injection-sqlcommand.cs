using System.Data.SqlClient;

class Example
{
    void Bad1(string userId, SqlConnection conn)
    {
        // ruleid: csharp-sql-injection-sqlcommand
        var cmd = new SqlCommand($"SELECT * FROM Users WHERE Id = {userId}", conn);
    }

    void Bad2(string userId, SqlCommand cmd)
    {
        // ruleid: csharp-sql-injection-sqlcommand
        cmd.CommandText = "SELECT * FROM Users WHERE Id = " + userId;
    }

    void Ok1(string userId, SqlConnection conn)
    {
        // ok: csharp-sql-injection-sqlcommand
        var cmd = new SqlCommand("SELECT * FROM Users WHERE Id = @id", conn);
        cmd.Parameters.AddWithValue("@id", userId);
    }
}
