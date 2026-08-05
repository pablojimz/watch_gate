let bad1 user_input =
  (* ruleid: ocaml-unix-system-command-injection *)
  Unix.system user_input

let bad2 user_input =
  (* ruleid: ocaml-unix-system-command-injection *)
  Unix.open_process user_input

let ok1 () =
  (* ok: ocaml-unix-system-command-injection *)
  Unix.system "uptime"
