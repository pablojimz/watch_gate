
<!-- Changes that affect Black's stable style -->

- Fix unparseable output for a t-string whose replacement field contains a quote (for
  example `t'\'{a["b"]}\''`). The guards that keep quote normalisation away from the
  inside of an f-string replacement field were never reached for t-strings, so the
