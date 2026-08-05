import org.springframework.web.multipart.MultipartFile;
import java.io.File;

class Example {
    void bad1(MultipartFile file, String uploadDir) throws Exception {
        // ruleid: spring-file-upload-no-validation
        String dest = uploadDir + file.getOriginalFilename();
        file.transferTo(new File(dest));
    }

    void ok1(MultipartFile file, String uploadDir) throws Exception {
        String safeName = java.util.UUID.randomUUID().toString() + ".dat";
        // ok: spring-file-upload-no-validation
        String dest = uploadDir + safeName;
        file.transferTo(new File(dest));
    }
}
