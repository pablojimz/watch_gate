(defn bad1 [user-input]
// ruleid: clojure-eval-dynamic-code
  (eval (read-string user-input)))

(defn ok1 []
// ok: clojure-eval-dynamic-code
  (eval '(+ 1 2)))
