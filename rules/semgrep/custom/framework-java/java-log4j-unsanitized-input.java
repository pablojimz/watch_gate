import org.apache.logging.log4j.Logger;
import javax.servlet.http.HttpServletRequest;

class Example {
    Logger logger;

    void bad1(HttpServletRequest request) {
        // ruleid: java-log4j-unsanitized-input
        logger.info(request.getHeader("User-Agent"));
    }

    void bad2(HttpServletRequest request) {
        // ruleid: java-log4j-unsanitized-input
        logger.error(request.getHeader("X-Forwarded-For"));
    }

    void ok1() {
        // ok: java-log4j-unsanitized-input
        logger.info("Application started");
    }
}
