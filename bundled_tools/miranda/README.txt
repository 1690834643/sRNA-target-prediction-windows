miRanda Win64 Static Binary
===========================

Version:       miRanda 3.3a (aug2010 release)
Build date:    2026-05-11T11:07:35+08:00
Toolchain:     x86_64-w64-mingw32-gcc-posix (GCC) 10-posix 20220113
Platform:      Windows x86-64 (PE32+ console executable, statically linked)

Source:
  URL:    http://ftp.genek.cn:8888/Share/linux_software/miRanda-aug2010.tar.gz
  SHA256 of source tarball:
          a671da562cf4636ef5085b27349df2df2f335774663fd423deb08f31212ec778
  (Verified against bioconda recipe: bioconda/bioconda-recipes)

Build flags applied:
  --host=x86_64-w64-mingw32
  CC=x86_64-w64-mingw32-gcc-posix  (posix thread model)
  CFLAGS='-O2 -U_FORTIFY_SOURCE -D_FORTIFY_SOURCE=0 -fcommon'
  LDFLAGS='-static -static-libgcc -static-libstdc++'
  config.h: HAVE_MALLOC=1, HAVE_REALLOC=1 (disabled rpl_malloc/rpl_realloc)

License:
  miRanda is distributed under the GNU General Public License (GPL).
  See https://www.gnu.org/licenses/gpl.html for details.
  Note: miRanda is intended for academic/research use. Users are responsible
  for verifying compliance with upstream license terms before any commercial
  or redistribution use.

SHA256 (miranda.exe):
  e83e13a55368c27672b967656692b9452ebe5b76b9fc7984ff6edb2a54f975cc

Basic usage:
  miranda mirna.fa targets.fa [options]
  miranda mirna.fa targets.fa -sc 140 -en -20
  miranda --help
