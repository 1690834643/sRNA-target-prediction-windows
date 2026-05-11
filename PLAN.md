# Maintenance Plan (PLAN.md)

下一个接手本项目的人请先读这份，再去读 `README.md`、`docs/architecture.md`、`src/`。

本文档 = 当前状态 + 已知技术债 + 下一版本路线图 + Release 操作手册 + 上游变更应对。

---

## 0. 当前状态（v1.0.0 release · 2026-05-11）

**功能完整度**

- 三工具集成：miRanda 3.3a / RNAhybrid 2.1.2 / PITA (patched Vienna-1.6) — 已交叉编译为 Win64 二进制，全部 bundled
- PITA ΔG / ddG 与 Linux 上游 bit-exact（2 和 11 hits 两份 benchmark 验证）
- 双击即用：FastAPI + 浏览器 UI + Windows 原生 tkinter 文件对话框
- 自动发现 bundled_tools，免配置
- HTML 报告 + alignment SVG（Arial+Courier 出版风格）
- FASTA 输入校验（中文报错原因）

**测试**：81 passed / 2 skipped（matplotlib_venn 老 skip + PITA Windows-only skip）

**Release artifact**：`srna-win-target-portable.zip` 77 MB / 解压 ~135 MB / SHA256 见 `.sha256` sidecar

**端到端验证**：在 ASCII 路径与中文用户名路径都跑通过；ΔG 在两条路径下逐位一致

---

## 1. 已知技术债（v1.0.0 留下来的）

来源：10-slice 代码审核（7 个真做了，3 个 Codex 阵亡）。完整内容在 `tmp/reviews/SUMMARY.md`（内部）；下面只摘录 v1.0.0 没修、需要后续处理的项。

### 安全 / 防御性（MED，要修，但不阻塞发布）

| 编号 | 位置 | 问题 | 建议改法 |
|---|---|---|---|
| S-1 | `web/server.py` `_build_job` | 工具参数从请求 body 不做 schema 校验直接进 `ToolConfig.parameters` | 用 pydantic per-tool schema，未知键拒绝 |
| S-2 | `/api/jobs/{id}/download` 和 `/report` | 没做 output-root containment 检查；如果 merged.parent 是 symlink 出去就泄 | 存储 canonical job out_dir，每次 GET 时 `Path.resolve()` 校验包含关系 |
| S-3 | `web/server.py` `_TK_LOCK` | 单全局锁卡所有并发 `/api/pick-file` 请求 | 加超时 + 拒绝 409，或把 Tk 跑在专门的 UI 线程 |
| S-4 | `web/server.py` `_broadcast` | 遍历 `state.subscribers` 没加锁；订阅者增删也没加锁 | 加锁，或把 dispatch 搬到 event loop |

### 可观察性 / UX（MED）

| 编号 | 位置 | 问题 | 建议改法 |
|---|---|---|---|
| U-1 | `data/format_check.py` | 校验只在 web 路径生效，CLI 和直接调用 `core/pipeline.run_pipeline` 都绕过 | 把 `validate_input_fasta` 调用挪进 `run_pipeline` 入口 |
| U-2 | `data/format_check.py` 5 GB 上限 | 单条 4.9 GB 大 record 仍能过校验然后 OOM | 在循环里早退：累计 sequence 长度 > 阈值就 fail |
| U-3 | `data/format_check.py` 200 record 采样 | 第 201+ 条全空 / 全蛋白时静默通过 | 全文件扫描；或抽样 200 + 文件末尾 50 |
| U-4 | `web/__init__.py` port 耗尽 | 5173-5193 全占时抛裸 RuntimeError | 在 `scripts/srna_win_target_web.py` 入口 catch，弹 tkinter 错误框 |
| U-5 | `web/__init__.py` `webbrowser.open` | 在无默认浏览器的 Windows Server 上静默 no-op | 检查返回值，fallback 打印 URL + 写 `srna-win-target.log` |
| U-6 | `static/style.css` `#888` | 在白底上 WCAG AA 对比度不够 | 改 `#666` 或 `#555` |
| U-7 | `static/app.js` 启动竞态 | `/api/discover` 还没回来用户就点"一键跑示例"会报 "未找到示例数据" | 按钮在 init 完成前禁用 |

### 测试覆盖空白（MED）

| 编号 | 位置 | 缺什么 |
|---|---|---|
| T-1 | `tests/test_web.py` | `/api/jobs/{id}/report` 无测试（404/410/200 三个路径） |
| T-2 | `tests/test_web.py` | `/api/open-folder` 无测试 |
| T-3 | `tests/test_web.py` | FASTA 422 端到端无测试（POST 蛋白序列 → 422 + 中文 detail） |
| T-4 | `tests/test_web.py` | WS 中途断开 / 重连 / 后订阅 backlog 无测试 |
| T-5 | `tests/` | Resume 集成测试空白：写 manifest → 中途 kill → 重跑 → 断言跳过已完成 chunk |
| T-6 | `tests/test_real_backend_integration.py` | 已加 3 个测试，但只在 dev box 有 bundled binary 时跑；CI 无人值守跑不到 |

### 没审到的 3 块（Codex 阵亡，潜在风险未知）

- **#1 PITA bundle**：构建脚本可重现性、busybox vs GNU coreutils 语义漂移、license compatibility、`default.par` 参数表配错风险
- **#5 Pipeline/scheduler/manifest**：resume 边角（output 删后 / mark_running race / failed chunk 重试），`LocalBackend` vs `WSLBackend` argv 翻译，v2 swap 后 cache_key 应该是 stale 的（要么换 key，要么清 manifest）
- **#7 Alignment SVG viz**：parser 在 miRanda Forward 块多版本 / RNAhybrid `-c` 的 corner case 上没系统测

可以再派一次 Kimi（或者本地手做），都不算紧急。

---

## 2. Release 操作手册

下次发 v1.x.y 严格按这个跑：

```bash
# === 0) 代码改完，testing 全绿 ===
PYTHONPATH=src QT_QPA_PLATFORM=offscreen python -m pytest tests -q
# 必须 81 passed / 2 skipped 起步（要加测试就抬这个数字）

# === 1) bit-exact 回归（PITA 任何改动都要做） ===
# 在 /mnt/c 下面解压 zip，用 cmd.exe 跑 examples/input/，
# 输出 ddG 必须与 Linux 服务器参考的 -24.28 / -28.07 完全一致。
# 详见 docs/architecture.md 的 "PITA bit-exact 验证步骤" 章节。

# === 2) 重 freeze exe ===
# 必须在 Windows Python (3.12.10) 上跑；WSL 跑不出真 PE32+。
# 建议路径：C:\srna-build\（不要在 %TEMP%，PyInstaller 主动拒绝那里）
cd /mnt/c/srna-build
"%USERPROFILE%\AppData\Local\Programs\Python\Python312\python.exe" scripts\build_windows_exe.py web
# 产物：dist\srna-win-target-web.exe (~46 MB)

# === 3) 重打 zip ===
cd /home/nee/srna-win-target  # 或本仓库 clone 出来的位置
cp /mnt/c/srna-build/dist/srna-win-target-web.exe dist/
BUILD_ROOT=. bash scripts/assemble_portable_zip.sh
# 产物：srna-win-target-portable.zip + .zip.sha256（默认 ~77 MB）

# === 4) 解压 smoke 测试 ===
# 解到全新 ASCII 路径，双击 exe，:5173 应该弹出 UI；
# 点 一键示例，必须出 7 行 hits + PITA ddG 不是 -1
# 浏览器看 HTML 报告，必须能展开 alignment SVG

# === 5) tag + release ===
git tag -a v1.x.y -m "..."
git push origin v1.x.y
gh release create v1.x.y \
  --repo 1690834643/sRNA-target-prediction-windows \
  --title "v1.x.y — ..." \
  --notes-file RELEASE_NOTES.md \
  srna-win-target-portable.zip srna-win-target-portable.zip.sha256
```

### 容易踩的坑

1. **中文用户名 `自动挡赛车手` 经过 cmd.exe 嵌套引号会被 GBK 编码搞烂** —— 写 `.bat` 文件用 `%USERPROFILE%` 避免，不要把绝对路径直接拼进单条 cmd 字符串
2. **PyInstaller 主动拒绝在 `%TEMP%` 下跑** —— 必须放 `C:\Users\...` 之外（推荐 `C:\srna-build\`）
3. **`/mnt/c/Users/自动挡赛车手/Desktop/srna-win-target-build` 是旧默认 BUILD_ROOT**，新版 `assemble_portable_zip.sh` 已经改成 `$ROOT`（即仓库根的 `dist/`），不要再去找老路径
4. **解压前要 kill 旧的 srna-win-target-web.exe 进程**，否则 unzip 跳过被锁文件，新 zip 解出来缺 exe
5. **rebuild 后的 zip sha 会变**，因为 zip header 含时间戳；内容相同但 hash 不同。这是正常的，写进 `.sha256` 的就是新的 hash

---

## 3. 路线图（v1.1+）

按优先级排：

### 高（修了用户最有感）

- [ ] **取消按钮真正生效**：现在 `cancelRun()` 只关 WS，服务器端 job 还在跑。需要 `/api/jobs/{id}/cancel` POST + scheduler 里轮询 cancel flag
- [ ] **IntaRNA 适配器**：`src/srna_win_target/tools/intarna.py` 占位文件已经在了；交叉编译加打包 + parser + golden 走 PITA 的路子
- [ ] **代码签名证书**：避免杀软警告"未知发布者"。淘宝/沃通 ~1500 元/年。签 `srna-win-target-web.exe` 之后释放疑虑
- [ ] **frontend 同步空格检测**：现在路径含空格 PITA 才报错。前端在用户填 output folder 的时候就标红警告

### 中（debt 还款）

- [ ] 修上面"已知技术债"列表里的 MED 项（特别是 S-1/S-2 路径安全、T-1~T-5 测试缺口）
- [ ] CI / GitHub Actions：
  - matrix Ubuntu + Windows
  - Ubuntu 跑 `pytest tests -q`
  - Windows 跑 PyInstaller smoke build（不一定每次发 release，只验证打得出）
- [ ] 不带 PITA 的最小版本：~30 MB 的 zip，给只关心 miRanda+RNAhybrid 的人
- [ ] macOS / Linux 桌面版：源码已经跨平台，缺的是各平台的 PyInstaller + 三工具二进制

### 低 / 长期

- [ ] Venn / UpSet 图集成进 HTML 报告（matplotlib_venn 已经有依赖）
- [ ] Rust 重写调度器（如果分发体积成为主要痛点的话）
- [ ] 自动更新机制（exe 自检版本，提示用户去 Releases 页下载）

---

## 4. 上游变更应对

### 如果 miRanda 出新版

miRanda 自 2010 年没更新（GitHub: hacktrick/miranda）。如果真出 3.4：
1. 把 `bundled_tools/miranda/miranda.exe` 换成新版（用相同的 mingw-posix recipe 编）
2. 重跑 `pytest tests/test_parsers_real.py`，如果 hit 数字变了，更新 `tests/golden/real/miranda/`
3. README 里 "miRanda 3.3a" → "miRanda 3.4"
4. 重打 zip + release v1.x.y

### 如果 RNAhybrid 出新版

同上。RNAhybrid 上游来源：`mirrors.tuna.tsinghua.edu.cn/ubuntu/pool/universe/r/rnahybrid/`。

### 如果 PITA 出新版

PITA 上游来自 Weizmann (genie.weizmann.ac.il)，**已下线**。我们用的源是 lab server `stark08:/home/data/t150541/mirna/Bin/ViennaRNA/ViennaRNA-1.6/`。如果上游再次复活：
1. 备份 `bundled_tools/pita/pita_prediction.pl` + `lib/*.pl` 当前的"路径已改相对"版本
2. 拉上游新版 diff 我们当前的，把上游变更 merge 进 wrapper-compatible 版本
3. 重跑 bit-exact 测试，确认输出仍一致

如果"我们当前手里的源就是地球上唯一一份了"也别意外。

### 如果 ViennaRNA 出新大版本

PITA bundle 用的是它**私有**修补的 Vienna-1.6（带 `-5 N` flag 与 4-line `force_binding` 输入），不是 stock Vienna。**不要**把 `bundled_tools/pita/RNAduplex.exe` 替换成新版 Vienna 的 RNAduplex —— 数值会变、`-5` flag 会消失、PITA 立刻挂。

如果实在要升级，参考 `docs/architecture.md` 里的 patch 描述，把 PITA 那几个 `.c` 改动 port 到新版 Vienna 源 —— 这是真的得有人坐下来读 C 代码。

---

## 5. 架构速查（找代码用）

```
src/srna_win_target/
├── core/
│   ├── pipeline.py            ← run_pipeline() 入口；normalize → split → schedule → write
│   └── models.py              ← PredictionJob / ToolConfig / ProgressEvent dataclasses
├── data/
│   ├── format_check.py        ← validate_input_fasta + normalize_input_fasta
│   └── fasta_split.py         ← split_fasta(records_per_chunk=N)
├── tools/
│   ├── base.py                ← LogicalCommand + ToolRunner ABC
│   ├── miranda.py             ← cmd builder + Forward block parser
│   ├── rnahybrid.py           ← cmd builder + -c compact parser
│   ├── pita.py                ← cmd builder + PITA result parser (UTR/RefSeq dual support)
│   └── registry.py            ← build_runner(ToolConfig) factory
├── backends/
│   ├── base.py                ← Backend.run(LogicalCommand) ABC
│   ├── local.py               ← subprocess.run, Windows-native
│   └── wsl.py                 ← WSL2 interop, path translation C:\* ↔ /mnt/c/*
├── parallel/
│   ├── scheduler.py           ← ThreadPoolExecutor + per-chunk dispatch
│   ├── manifest.py            ← RunManifest (sha256-keyed cache for resume-skip)
│   └── cache.py               ← cache_key() + file_sha256()
├── results/
│   ├── merge.py               ← per-pair intersection table
│   ├── streaming_writer.py    ← appends to merged_predictions.csv as chunks finish
│   ├── visualize.py           ← Venn/UpSet plots (needs [plots] extra)
│   ├── visualize_alignment.py ← parse_miranda/parse_rnahybrid + render_svg (locked N2 style)
│   └── html_report.py         ← build_report(merged_csv, work_dir, out_html)
├── web/
│   ├── __init__.py            ← uvicorn launcher + port finder + browser open
│   ├── server.py              ← FastAPI app, all /api/* endpoints
│   ├── discover.py            ← scan bundled_tools/<tool>/ for binaries
│   └── static/                ← index.html + style.css + app.js (vanilla JS)
├── gui/                       ← PySide6 desktop GUI (NOT bundled in portable zip; dev-only)
└── cli/
    ├── app.py                 ← typer app: predict / selftest / validate-tools / gui / web
    └── _selftest.py           ← FakeBackend + run_selftest (smoke test sans real tools)

bundled_tools/pita/
├── pita_prediction.pl         ← PITA driver (Linux paths → relative; win_system() shim)
├── lib/                       ← 28 helper .pl scripts; load_args / format_number / ...
│                                 注意：lib/RNAddG_compute.pl 调 RNAduplex.exe -5 0
│                                 和 RNAddG4，对应 v2 二进制；找不到时返回 -1 fallback
├── sort_wrapper.pl + bin/sort.bat   ← Windows POSIX sort wrapper
└── (.exe + perl/ + bin/ 由 release zip 提供，git 不存)
```

---

## 6. 常见维护操作

### 重新生成 golden fixtures

```bash
# 服务器 stark08 上 (sshpass; 见 connect-server skill)
bash scripts/probe_server_tools.sh   # 看上游版本
bash scripts/build_real_goldens.sh   # 跑出新 golden tab/txt
# 拉到本地 tests/golden/real/{miranda,rnahybrid,pita}/
# 跑 pytest tests/test_parsers_real.py -v
```

### 重新交叉编译 PITA Vienna-1.6

完整 recipe：

```bash
# 服务器上的源：/home/data/t150541/mirna/Bin/ViennaRNA/ViennaRNA-1.6/
# 本地交叉编译关键 flag：
env -i HOME=$HOME PATH=/usr/bin:/bin \
  CC=x86_64-w64-mingw32-gcc-posix \
  CFLAGS="-O2 -U_FORTIFY_SOURCE -D_FORTIFY_SOURCE=0 -fcommon -fgnu89-inline -Wno-error" \
  ./configure --host=x86_64-w64-mingw32 --build=x86_64-pc-linux-gnu \
    --disable-shared --enable-static --without-perl

# 关键技巧：
# - posix-thread mingw（不是 win32），dlib 需要 std::mutex
# - -fgnu89-inline 修 lib/cofold.c lib/fold.c 老式 `inline int Foo(){}` 链接
# - -fcommon 修 GCC 10+ 的 -fno-common 默认
# - -U_FORTIFY_SOURCE -D_FORTIFY_SOURCE=0 修 glibc 限定的 __strcat_chk
# - LDFLAGS=""  必须清空，否则 conda 注入的 -L/home/nee/miniconda3/lib 会破链
# - Cluster/Kinfold/RNAforester/Perl 子目录 Makefile.in stub 掉，跳过编译
# - config.h 删 #define malloc rpl_malloc 一行（gnulib 没装）
```

直接编 `Progs/RNAduplex.c`、`Progs/RNAddG.c`、`Progs/RNAddG4.c`：

```bash
x86_64-w64-mingw32-gcc-posix -DHAVE_CONFIG_H -I. -I.. -I../H \
  -O2 -U_FORTIFY_SOURCE -D_FORTIFY_SOURCE=0 -fcommon -fgnu89-inline -Wno-error \
  -o RNAddG4.exe RNAddG4.c ../lib/libRNA.a -lm
```

### 验证一份新 zip "真的是开箱即用"

最低标准（不通过就别发 release）：

1. 解压到全新 ASCII 路径
2. 双击 exe，浏览器自动开
3. 顶上"已就绪 · 3/3"
4. 点"一键跑示例数据"，2 秒内出 7 行 hits
5. PITA 那两行 score 不是 -1（不是 fallback）
6. 点"打开预测报告"，浏览器开新页
7. 报告里点 RNAhybrid 那行，下面冒出 SVG alignment

最好再加一个：8. 把输出文件夹改成 `C:\Users\<中文用户名>\Desktop\...`，再点一次示例，结果与步骤 4 完全一致

---

## 7. 重要文件清单（不要丢）

- `bundled_tools/pita/pita_prediction.pl` —— 我们的 wrapper-friendly fork（原版来自 Weizmann，**已下线**）
- `bundled_tools/pita/lib/*.pl` —— 28 个 helper，所有 `require "lib/X.pl"` 已改成相对路径
- `bundled_tools/pita/lib/RNAddG_compute.pl` —— 调 `RNAduplex.exe -5 0` 与 `RNAddG4 -u N -s N -f N -t N`，含 `$$` pid 后缀的 tmp 文件隔离
- `srna-win-target-web.spec` —— PyInstaller 模板；hiddenimports 不全会在 frozen exe 上炸
- `tests/golden/real/` —— 服务器原始输出快照，是数值回归的最后防线
- `LICENSES/NOTICE.txt` —— 上游许可证，分发前必看

---

## 8. 联系

- Issues：https://github.com/1690834643/sRNA-target-prediction-windows/issues
- 作者：ksjhunau@gmail.com
