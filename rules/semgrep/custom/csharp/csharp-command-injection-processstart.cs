using System.Diagnostics;

class Example
{
    void Bad1(string userInput)
    {
        // ruleid: csharp-command-injection-processstart
        Process.Start("cmd.exe", userInput);
    }

    void Bad2(string program, string userArgs)
    {
        // ruleid: csharp-command-injection-processstart
        Process.Start(program, userArgs);
    }

    void Ok1()
    {
        // ok: csharp-command-injection-processstart
        Process.Start("cmd.exe", "/C dir");
    }
}
