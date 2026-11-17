# NFC datasets with original-codepoint provenance

本增量扩展已有语料加工闭环；README.md 的正常 V1、全部原接口和原测试仍适用。
V1 没有 NFC、字符来源或非连续标注投影。本文件与 nfc_examples.py 是公开契约和有限夹具，不含目标实现。

## Entry and fixed inputs

新增 Corpus.build_nfc(request_id, document_revision, annotation_revision)，返回不可变数据集 ID；
processing.build_nfc 接受同样参数，产生同样结果。引用格式、身份合法性、异常类型和
固定文档绑定规则沿用 build_raw：比较完整 document_id 与 revision，不按相同内容或 head 替代。
原文、标注仍通过 put_document、put_annotations 提交；不会在构建时创建或改绑输入修订。

NFC 成果由现有 Corpus.read / datasets.read 和 Corpus.export / exports.export 读取，
两层入口结果分别相同。加工文本、来源及标注必须一起持久发布，不能仅返回一个临时规范化对象。
允许新增内部模块、全量重算及复用现有事务，不要求流式、索引、增量刷新或并发。

## Text, origins and projected annotations

text 是整个原文的 Unicode NFC，不是逐标注分别规范化。Unicode 语义取当前 Python
unicodedata 所对应版本。原文坐标与输出坐标均按 Python Unicode 码点计，不按字节或字素簇计。

origins 是与 text 等长的列表。每项为非空、升序、无重复的原文码点下标列表。
其含义由规范变换定义：规范分解产生的各码点继承该原码点来源，规范重排不改变来源，
规范组合后的码点来源为全部参与码点来源的并集；必须遵守组合阻塞、组合排除及 Hangul 规则。
这是实际变换的来源关系，不是相同字符任意匹配、长度差平移或文本 diff 的猜测。
一个原码点可属于多个输出码点，一个输出码点也可属于多个原码点。

对每个原标注 [start,end)，恰好选择 origins[j] 与该区间有交集的输出位置 j，
将所选位置压为升序、最大连续的半开片段 spans。片段之间至少空一个输出码点。
保留每个标注的原始 ID、start、end、完整标签和提交顺序，不合并同名标签或相同覆盖的标注。
不同标注可共享输出字符；投影不是包围区间。文本加工交出的同一来源关系须供标注加工和导出消费。

## Read shape and checksums

NFC 的 read 返回恰含：
- dataset_id：非空字符串；
- kind：固定为 "nfc_v1"；
- inputs：与 raw_v1 同形的完整 document / annotations 摘要及计数；
- text：规范文本字符串；
- origins：上述列表；
- annotations：按提交顺序的列表，每项恰含 annotation_id、start、end、label、spans；
  annotation_id 是原记录 id，spans 是 [[输出起点,输出终点], ...]；
- content_sha256：下述规范摘要。

NFC 内容摘要覆盖 {"kind":kind,"inputs":inputs,"text":text,"origins":origins,"annotations":annotations}，
不含请求 ID 或数据集 ID；编码和 SHA-256 规则沿用 README.md 的规范 UTF-8 JSON。
空原文产生 text=""、origins=[]、annotations=[] 的真实成果。
非空原文的空标注集仍须保留完整 text 和 origins。返回的所有容器和标签均与持久成果隔离。

## Export shape

NFC export 仍返回 {"jsonl":字符串,"manifest":字典}，只读取一次持久数据集快照。
jsonl 恰好一条文档记录，包括空文本和空标注集，末尾一个 LF。
记录按以下字段顺序编码：dataset_id、kind、inputs、text、origins、annotations。
记录中的值直接来自该快照；JSON 编码的 ensure_ascii=False、紧凑分隔符及有限数规则沿用 V1。
manifest 恰含 dataset_id、kind、inputs、row_count、content_sha256、jsonl_sha256；
row_count 为 1，jsonl_sha256 覆盖实际返回的 UTF-8 JSONL 字节。
raw_v1 的 read、JSONL 字段顺序、零行导出和全部摘要保持原样。

## Replay, failure and history

请求使用 V1 的统一请求命名空间，身份为 kind 与完整 inputs。
同请求、同身份返回原 ID；不同修订、不同输入身份或 raw_v1 / nfc_v1 混用同请求均抛 ValueError。
缺失修订抛 KeyError，引用非法或完整绑定冲突抛 ValueError，存储或实际提交异常原样传播。
输入解析、加工、写入或提交失败都不得留下本请求的成果或回执；已有成果不变，失败后可用同请求重试。
上游更新、修改 read 或 export 返回值、关闭重开均不得改变旧成果和原请求重放。
不要求跨 Unicode 版本升级或恢复损坏数据库。

## Finite examples and joint verification

nfc_examples.py 中所有坐标和来源均为明确夹具。其中：
- "A\u030A" 变成 Å，origins=[[0,1]]；两个原字符分别标注时都投影为 [[0,1]]。
- "a\u0315\u0300" 变成 "à\u0315"，origins=[[0,2],[1]]。
- "q\u0315\u0300" 变成 "q\u0300\u0315"，原标注 [0,2) 投影为 [[0,1],[2,3]]。
- "Å\u0323\u030A" 变成 "Ạ\u030A\u030A"，origins=[[0,1],[0],[2]]；
  最后两个同值圆圈不能互换来源。

python3.11 -B nfc_examples.py --fixtures 仅检查静态夹具，不调用新增接口，可用于初始树检查。
实现后 python3.11 -B nfc_examples.py --check 核对有限样例、组件入口、摘要、导出、
统一请求冲突、返回值隔离、写入拒绝后的重试、上游替换及文件数据库重开。
python3.11 -B nfc_examples.py --demo 展示真实发布后重开的非连续投影和来源清单。
这些夹具不是全部验收；交付独立于生产来源推导的核账及简短交接不变量说明，
核对重复标记、阻塞、排除和 Hangul，以及完整发布和受影响的旧行为。
保留全部原测试字节；原 examples.py 仍可运行。
修改现有 .pointwise-runtime.json，使 verify 执行全部原回归及新增业务核账并保留失败退出码，
demo 展示 NFC 成果、共享字符、重排及重开，命令参数数组格式沿用当前清单。
