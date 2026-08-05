import org.springframework.expression.ExpressionParser;
import org.springframework.expression.spel.standard.SpelExpressionParser;

class Example {
    void bad1(String userInput) {
        ExpressionParser parser = new SpelExpressionParser();
        // ruleid: spring-spel-injection
        Object result = parser.parseExpression(userInput).getValue();
    }

    void ok1() {
        ExpressionParser parser = new SpelExpressionParser();
        // ok: spring-spel-injection
        Object result = parser.parseExpression("1 + 1").getValue();
    }
}
