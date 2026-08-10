# Local workaround for meta-oe/wrynose keyutils 1.6.3 (no upstream fix yet).
# The Makefile:175 'cxx.stamp' target syntax-checks keyutils.h as C++ with
# $(CXX) $(CPPFLAGS) $(CXXFLAGS) -Werror, but does not inherit distro's -O2.
# Without -O2, _FORTIFY_SOURCE=2 triggers -Werror=cpp on features.h and fails
# do_compile. Force -O2 into CXXFLAGS (needed for cxx.stamp) and CFLAGS.
EXTRA_OEMAKE:append = " CFLAGS+=-O2 CXXFLAGS+=-O2"
