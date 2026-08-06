  [discussion #3527](https://github.com/pallets/click/discussions/3527). {pr}`3581`
- `style()` and `secho()` no longer silently drop the 256-color index `0`
  (black) passed as `fg` or `bg`, and now validate color arguments. {pr}`3677`
- `unstyle` and the ANSI handling behind help-text wrapping now strip the full
  CSI escape-sequence grammar.

## Version 8.4.2

