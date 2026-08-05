using System.Xml;

class Example
{
    void Bad1()
    {
        var settings = new XmlReaderSettings();
        // ruleid: csharp-xxe-dtd-processing-enabled
        settings.DtdProcessing = DtdProcessing.Parse;
    }

    void Ok1()
    {
        var settings = new XmlReaderSettings();
        // ok: csharp-xxe-dtd-processing-enabled
        settings.DtdProcessing = DtdProcessing.Prohibit;
    }
}
