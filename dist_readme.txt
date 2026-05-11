sRNA Windows Target Predictor — bundled web UI
================================================

What you got
------------
- srna-win-target-web.exe   single-file Windows binary, ~60 MB
- examples\                 sample miRNA + targets FASTA + tools.toml

How to use
----------
1. Double-click  srna-win-target-web.exe
2. A console window appears and the server starts at http://127.0.0.1:5173
3. Your default browser opens automatically. If it doesn't, paste the URL.
4. In the page:
     - Set miRNA FASTA, Targets FASTA, Output folder
     - Tick the tools you have installed; point each at its executable / script
     - Pick the backend:
         local  - native Windows binaries
         wsl    - drive Linux binaries inside WSL2
     - Press Run
   Progress streams live; the Download merged CSV button appears at the end.
5. Close the console window when you are done — the server stops.

Where the tools live
--------------------
miRanda and RNAhybrid have no official Windows builds. You need one of:
  - WSL2 with a conda env like the bio server's `miRNA` env, then set
    backend=wsl and point each path at the Linux binary (POSIX style).
  - A precompiled or self-built native miRanda/RNAhybrid in bundled_tools\.

PITA (pita_prediction.pl + Vienna-1.6 patched RNAduplex / RNAddG4 + Strawberry
Perl 5.42 portable) is now bundled in the portable zip; ΔG values are
bit-exact with the upstream Linux reference (verified on examples/input/
and a 3 miRNA × 3 UTR benchmark). If your output folder path contains
non-ASCII characters or spaces, the wrapper refuses early — pick an ASCII
path or switch Backend to "wsl" instead.

Smoke test without installing any real tool
-------------------------------------------
Open a command prompt where the exe lives and run:

    srna-win-target-web.exe --help

(Or use the CLI executable: srna-win-target.exe selftest)

Files produced under each run's output folder:
    work\normalized\    cleaned FASTA inputs
    work\chunks\        split target FASTA
    work\raw\<tool>\    per-chunk raw tool outputs
    work\logs\          per-chunk subprocess logs
    work\manifest.json  cache for resumable runs
    results\merged_predictions.csv

Re-runs with the same inputs / params / tool versions skip cached chunks.
