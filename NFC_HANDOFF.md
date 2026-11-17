# NFC 交接说明与归属不变量

本文件是 nfc_v1 增量的交接说明。公开契约以 NFC.md 与 nfc_examples.py 为准；
本文件说明实现位置、推导规则、核账方法与不变量，便于后续维护者复核。

## 1. 交付物与入口

- 新入口：`Corpus.build_nfc(request_id, document_revision, annotation_revision)`
  与 `corpus.processing.build_nfc(...)`，参数、引用校验、异常类型、固定文档绑定
  规则与 `build_raw` 完全一致（`processing/api.py`、`processing/bindings.py`）。
- 读取与导出复用既有入口：`Corpus.read` / `datasets.read` 与
  `Corpus.export` / `exports.export`；按快照 `kind` 分流，raw_v1 的字段顺序、
  零行导出与全部摘要保持原样。
- 新增内部模块：
  - `processing/normalize.py`：UAX #15 三阶段变换与逐输出码点来源；
  - `processing/nfc_runner.py`：固定输入快照、来源计算与标注投影、发布；
  - `datasets/integrity.py` 增加 `make_nfc_payload` / `copy_nfc_snapshot`；
  - `datasets/publication.py`、`datasets/storage.py`、`datasets/api.py`、
    `datasets/catalog.py` 增加 nfc_v1 发布/装载分支（复用同一套表与事务）；
  - `exports/{reader,jsonl,manifest}.py` 按 kind 编码 nfc_v1 单条 JSONL。
- 持久化形态：nfc_v1 在 `datasets` 中记 `row_count=1`，其 text/origins/
  annotations 作为 `dataset_rows` 中 ordinal=0 的一个 JSON 快照；请求回执仍写
  `request_receipts`，与 raw_v1 共用统一请求命名空间。
- 核账：`nfc_audit.py`（独立实现，见第 4 节）；回归：`tests/test_nfc.py`；
  联合核验：`nfc_examples.py --check/--demo/--fixtures`。

## 2. 来源推导规则（processing/normalize.py）

变换严格按 UAX #15 的规范分解（R1）、规范排序（R2）、规范组合（R3）执行，
字符语义全部取自运行环境的 `unicodedata`（当前为 Unicode 14.0.0）。

1. 分解：每个原码点递归展开规范分解（`<compat>` 兼容分解不参与 NFC，天然忽略）；
   Hangul 音节按算术公式分解为 L、V、可选 T。每个分解产物初始来源为
   `(原码点下标,)`——规范分解继承来源。
2. 排序：按 canonical combining class 做稳定冒泡交换；仅当后项 ccc 非零且
   前项 ccc 更大才交换。ccc=0 的字符（含 Hangul jamo）永不跨越，这与 CPython
   对 `unicodedata.normalize("NFC", ...)` 的行为一致。重排不改变来源绑定。
3. 组合：维护 starter 锚点与候选位置，按 R3 的阻塞规则判定
   （starter 场景要求前一字符 ccc=0；非 starter 场景按 ccc 比较）。
   - Hangul L+V、LV+T 仅在相邻时算术组合，被标记隔开的 T jamo 不组合；
   - 主组合对（首字符为 starter）与次组合对（首字符为非 starter，如 U+0344）
     从 unicodedata 分解表构建，并以 `unicodedata.normalize("NFC", 对)` 过滤
     Full_Composition_Exclusion（环境表中实际被排除的 81 个主对、0 个次对）；
   - 每次组合把两个参与码点的来源列表取并集、升序去重后挂到输出码点。
4. 每次调用末尾用 `unicodedata.normalize("NFC", 原文)` 比对文本，不一致即
   抛 RuntimeError，防止环境 UCD 与推导偏差静默产出。

`project_spans(origins, start, end)` 选出 origins 与原区间 `[start, end)`
有交集的全部输出位置，再压成升序、最大连续的半开片段；允许不连续片段，
不同标注可投影到同一输出字符，标注本身永不合并。

## 3. 不变量清单

- 文本：`read(...).text == unicodedata.normalize("NFC", 完整原文)`，空原文得到
  `text=""`、`origins=[]`、`annotations=[]` 的真实成果。
- 来源：origins 与 text 等长；每项非空、升序、无重复且下标在原文范围内；
  全部来源列表的并集恰好覆盖原文每个下标 0..n-1（每个原码点至少流向一个
  输出码点）；一个原码点可属于多个输出码点，一个输出码点也可汇聚多个原码点。
- 投影：片段覆盖且仅覆盖所有与原区间相交的输出位置；片段两两不相邻
  （最大连续）；保留 annotation_id、原 start/end、完整 label 与提交顺序；
  空标注集仍持久化完整 text 与 origins。
- 摘要：nfc 内容摘要覆盖
  `{"kind","inputs","text","origins","annotations"}`，编码规则与 V1 相同，
  不含请求/数据集 ID；jsonl 恰一条记录、末尾一个 LF，字段顺序为
  dataset_id、kind、inputs、text、origins、annotations；manifest 的
  row_count 恒为 1，jsonl_sha256 覆盖实际返回字节。
- 请求与历史：同请求同身份返回原 ID；异身份、异修订或 raw/nfc 混用同请求
  抛 ValueError；缺失修订抛 KeyError；非法引用/绑定冲突抛 ValueError。
  解析、加工、写入或提交失败均在同一事务内回滚，不留数据集、行或回执，
  失败后同请求可重试。上游更新、改动 read/export 返回值、关闭重开均不改变
  旧成果与重放结果。
- 隔离：read/export 返回的容器与标签均经 JSON 往返深拷贝，与持久状态隔离。
- 兼容：raw_v1 全部行为、原测试字节与 examples.py 不变。

## 4. 独立核账（nfc_audit.py）

核账脚本不 import 任何生产规范化代码，而是用不同的数据结构（记录字典、
独立的 NFD/排序/组合过程与独立的组合对构建）重新实现同一 UAX #15 变换，再：

1. 核对 nfc_examples 全部静态夹具（含重复标记、阻塞、Hangul、空文档）；
2. 1500 组随机字符串对照 `unicodedata.normalize` 文本、来源形状与分区覆盖；
3. 专项规则：Devanagari 组合排除（U+0915+U+093C 不合成 U+0958）、
   A+U+0305+U+030A 同 ccc 阻塞、Hangul LV+T 合成与 T jamo 被标记阻塞时
   不重排、次组合路径等价；
4. 端到端发布：read 形状、内容摘要、JSONL 字段顺序与 framing、manifest、
   重放与 kind 冲突、返回值隔离；
5. query_only 写入拒绝后无回执、无残留事务且可重试；
6. 文件库重开后旧成果、导出与重放完全不变。

运行：`python3.11 -B nfc_audit.py`，失败以断言与非零退出码暴露。

## 5. 运行清单

- 全量核验：`.pointwise-runtime.json` 的 verify 依次执行原 unittest 全套
  （含新增 tests/test_nfc.py）、`nfc_examples.py --check` 与 `nfc_audit.py`，
  任一失败即非零退出；demo 执行 `nfc_examples.py --demo`，展示发布后重开的
  组合、重排、共享字符与非连续投影。
- 手动命令：
  - `python3.11 -B -m unittest discover -s tests -v`
  - `python3.11 -B nfc_examples.py --fixtures|--check|--demo`
  - `python3.11 -B nfc_audit.py`
  - `python3.11 -B examples.py`（V1 原演示）

## 6. 已知边界

- 不处理跨 Unicode 版本升级与损坏数据库恢复（契约明确不要求）；
- 组合对表在模块导入时遍历一次码位空间构建（约 0.1 秒量级），之后纯内存
  计算；全量重算、单事务发布，无流式/增量/并发需求；
- 坐标均按 Python Unicode 码点计，不按字节或字素簇计。
