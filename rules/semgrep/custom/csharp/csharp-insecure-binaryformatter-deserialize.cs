using System.IO;
using System.Runtime.Serialization.Formatters.Binary;

class Example
{
    void Bad1(Stream s)
    {
        // ruleid: csharp-insecure-binaryformatter-deserialize
        var obj = new BinaryFormatter().Deserialize(s);
    }

    void Bad2(Stream s)
    {
        // ruleid: csharp-insecure-binaryformatter-deserialize
        var bf = new BinaryFormatter();
        var obj = bf.Deserialize(s);
    }

    void Ok1(Stream s)
    {
        // ok: csharp-insecure-binaryformatter-deserialize
        var obj = System.Text.Json.JsonSerializer.Deserialize<object>(s);
    }
}
