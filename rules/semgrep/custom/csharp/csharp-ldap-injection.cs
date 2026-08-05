using System.DirectoryServices;

class Example
{
    void Bad1(DirectorySearcher searcher, string username)
    {
        // ruleid: csharp-ldap-injection
        searcher.Filter = "(uid=" + username + ")";
    }

    void Ok1(DirectorySearcher searcher)
    {
        // ok: csharp-ldap-injection
        searcher.Filter = "(objectClass=user)";
    }
}
