class Example
{
    void Bad1()
    {
        // ruleid: csharp-insecure-random-token
        int resetToken = new Random().Next(100000, 999999);
    }

    void Bad2()
    {
        // ruleid: csharp-insecure-random-token
        var rand = new Random();
        int apiKeySeed = rand.Next();
    }

    void Ok1()
    {
        // ok: csharp-insecure-random-token
        int count = new Random().Next(1, 10);
    }
}
