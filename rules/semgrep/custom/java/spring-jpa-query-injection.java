import javax.persistence.EntityManager;

class Example {
    void bad1(EntityManager em, String username) {
        // ruleid: spring-jpa-query-injection
        em.createQuery("SELECT u FROM User u WHERE u.name = '" + username + "'");
    }

    void bad2(EntityManager em, String tableSuffix) {
        // ruleid: spring-jpa-query-injection
        em.createNativeQuery("SELECT * FROM users_" + tableSuffix);
    }

    void ok1(EntityManager em, String username) {
        // ok: spring-jpa-query-injection
        em.createQuery("SELECT u FROM User u WHERE u.name = :name").setParameter("name", username);
    }
}
