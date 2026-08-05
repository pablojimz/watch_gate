using System.IO;

class Example
{
    void Bad1(string baseDir, string userFile)
    {
        // ruleid: csharp-path-traversal-pathcombine
        var content = File.ReadAllText(Path.Combine(baseDir, userFile));
    }

    void Bad2(string baseDir, string userFile, string data)
    {
        // ruleid: csharp-path-traversal-pathcombine
        File.WriteAllText(Path.Combine(baseDir, userFile), data);
    }

    void Ok1(string baseDir)
    {
        // ok: csharp-path-traversal-pathcombine
        var content = File.ReadAllText(Path.Combine(baseDir, "config.json"));
    }
}
