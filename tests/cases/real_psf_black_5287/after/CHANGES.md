
<!-- Changes that affect Black's stable style -->

- Stop treating a t-string in docstring position as a docstring (for example
  `t"  spam  "` as the first statement of a module, class or function). t-strings
  evaluate to `Template`, never `str`, so stripping and reindenting one changed the
  value of the template and tripped Black's AST safety check (#5287)
- Fix unparseable output for a t-string whose replacement field contains a quote (for
  example `t'\'{a["b"]}\''`). The guards that keep quote normalisation away from the
  inside of an f-string replacement field were never reached for t-strings, so the
