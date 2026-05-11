PITA bundle — Windows portable
================================

Files:
- pita_prediction.pl    PITA driver script (from biotrainee.cn:/home/data/t150541/mirna/)
- lib/                  PITA helper Perl scripts (28 files: load_args.pl, libfile.pl, ...)
- RNAduplex.exe         ViennaRNA 2.6.4 cross-compiled (PE32+, x86_64-mingw)
- perl/                 Strawberry Perl 5.42.2.1 portable (stripped: removed c/ and vendor/)

Built: 2026-05-11
Strawberry Perl source: https://github.com/StrawberryPerl/Perl-Dist-Strawberry/releases/download/SP_54221_64bit/strawberry-perl-5.42.2.1-64bit-portable.zip
RNAduplex.exe source:  ViennaRNA 2.6.4 cross-compiled (see HANDOVER.md)
PITA upstream:         http://genie.weizmann.ac.il/pubs/mir07/

Windows-portability patch:
The upstream pita_prediction.pl + lib/*.pl scripts hardcoded the Linux path
"/home/data/t150541/mirna/lib/" in both `require` statements and `system()`
shell pipes. This bundle rewrites those to relative "lib/" paths, and the
wrapper sets cwd to this directory when invoking perl so `require "lib/X.pl"`
resolves correctly.

Status:
EXPERIMENTAL on Windows native. The hardcoded shell-pipeline style of
pita_run.pl ("cat $f | lib/foo.pl | lib/bar.pl > out") may not run cleanly
under cmd.exe even with paths patched; if the predictor errors at runtime,
switch the wrapper's backend to "wsl" — that bypasses cmd.exe by invoking
perl through WSL where the original Linux assumptions hold.

License:
- pita_prediction.pl + lib/: Weizmann Institute (see upstream site)
- Strawberry Perl: Artistic / GPL (see perl/licenses/ in upstream release)
- ViennaRNA: TBI Vienna license (see /tmp/vienna_xcompile source tree)

SHA256:
  RNAduplex.exe       0596a5eb9c6c9c4ad5d09ceeaffb77eefc220690318113b4b3161db9a60e988e
  perl/bin/perl.exe   (set by upstream; verify via `sha256sum perl/bin/perl.exe`)
