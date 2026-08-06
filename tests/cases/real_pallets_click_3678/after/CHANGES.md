  [discussion #3527](https://github.com/pallets/click/discussions/3527). {pr}`3581`
- `style()` and `secho()` no longer silently drop the 256-color index `0`
  (black) passed as `fg` or `bg`, and now validate color arguments. {pr}`3677`
- The automatic help option stores its value under the reserved name
  `_click_default_help` instead of `help`, so a parameter named `help` no
  longer breaks parsing. The new name is visible in
  {meth}`Command.to_info_dict` output. Parameters that overwrite each other's
  value trigger a warning: an argument sharing its name with another
  parameter, or any parameter claiming the reserved name. Options may still
  share a name to compete for the same value (feature switches).
  {issue}`2819` {pr}`3678`
- `unstyle` and the ANSI handling behind help-text wrapping now strip the full
  CSI escape-sequence grammar.

