import javax.xml.parsers.DocumentBuilderFactory;

class Example {
    void bad1() throws Exception {
        // ruleid: java-xxe-documentbuilderfactory
        DocumentBuilderFactory dbf = DocumentBuilderFactory.newInstance();
        dbf.newDocumentBuilder();
    }

    void ok1() throws Exception {
        DocumentBuilderFactory dbf = DocumentBuilderFactory.newInstance();
        dbf.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
        // ok: java-xxe-documentbuilderfactory
        dbf.newDocumentBuilder();
    }
}
