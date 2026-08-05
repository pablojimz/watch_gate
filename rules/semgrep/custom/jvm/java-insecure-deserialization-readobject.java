import java.io.ObjectInputStream;
import java.io.FileInputStream;
import java.io.ObjectInputFilter;

class Example {
    void inlineBad(FileInputStream fis) throws Exception {
        // ruleid: java-insecure-deserialization-readobject
        Object obj = new ObjectInputStream(fis).readObject();
    }

    void assignedBad(FileInputStream fis) throws Exception {
        ObjectInputStream ois = new ObjectInputStream(fis);
        // ruleid: java-insecure-deserialization-readobject
        Object obj = ois.readObject();
    }

    void paramBad(ObjectInputStream ois) throws Exception {
        // ruleid: java-insecure-deserialization-readobject
        Object obj = ois.readObject();
    }

    void filteredOk(FileInputStream fis) throws Exception {
        ObjectInputStream ois = new ObjectInputStream(fis);
        ois.setObjectInputFilter(filterInfo -> ObjectInputFilter.Status.ALLOWED);
        // ok: java-insecure-deserialization-readobject
        Object obj = ois.readObject();
    }
}
