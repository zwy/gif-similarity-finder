# GIF Similarity Finder

一个针对大规模 GIF 库（10 万量级）的相似度聚类工具，分两个阶段解决两类需求：

| 需求 | 阶段 | 技术 |
|---|---|---|
| 找来自同一视频截取的 GIF | Stage 1 | 感知哈希（pHash）+ 汉明距离 |
| 找动作/场景相似的 GIF | Stage 2 | CLIP 多帧均值向量 + FAISS + HDBSCAN |

---

## 安装

### 1. Python 环境

建议 Python 3.10+，推荐使用虚拟环境：

```bash
python -m venv .venv
source .venv/bin/activate   # macOS / Linux
# .venv\Scripts\activate    # Windows
```

### 2. 安装 PyTorch（先于其他依赖）

根据你的平台选择命令，详见 [https://pytorch.org/get-started/locally/](https://pytorch.org/get-started/locally/)

```bash
# macOS (Apple Silicon MPS)
pip install torch torchvision

# CPU only
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
```

### 3. 安装 CLIP

```bash
pip install git+https://github.com/openai/CLIP.git
```

### 4. 安装其余依赖

```bash
pip install -r requirements.txt
```

---

## 使用

### 基本用法

```bash
python gif_similarity.py --input /path/to/your/gif/folder
```

结果默认输出到 `./output/`。

### 完整参数

```bash
python gif_similarity.py \
  --input   /path/to/gifs \       # GIF 文件夹（必填）
  --output  ./output \            # 输出目录（默认 ./output）
  --frames  8 \                   # 每个 GIF 采样帧数，供 CLIP 使用（默认 8）
  --hash_thresh 10 \              # 同源判定的汉明距离阈值（默认 10，越小越严格）
  --min_cluster 3 \               # HDBSCAN 最小簇大小（默认 3）
  --batch_size  32 \              # CLIP 推理批大小（默认 32）
  --device  auto                  # 计算设备：auto / cpu / cuda / mps（默认 auto）
```

只跑某一阶段：

```bash
python gif_similarity.py --input /path/to/gifs --skip_stage1   # 只跑 CLIP 聚类
python gif_similarity.py --input /path/to/gifs --skip_stage2   # 只跑同源检测
```

---

## 输出文件说明

```
output/
├── stage1_same_source_groups.json    # Stage 1：同源 GIF 分组（JSON）
├── stage2_action_clusters.json       # Stage 2：动作/场景聚类（JSON）
├── clip_embeddings_cache.npz         # CLIP 向量缓存（增量复用，无需重算）
├── hnsw.index                        # HNSW 索引（可用于后续查询）
├── dashboard_manifest.js             # Dashboard 清单（阶段摘要 + 分片索引）
├── dashboard_stage1_000.js           # Stage 1 数据分片（按需加载，可能有多个）
├── dashboard_stage2_000.js           # Stage 2 数据分片（按需加载，可能有多个）
├── previews/                         # GIF 预览图（webp）
│   └── <stable_id>.webp
├── umap_clusters.png                 # UMAP 2D 聚类散点图（可选）
└── ...

dashboard/
├── index.html                        # Dashboard 唯一入口（浏览器打开）
└── dashboard.js                      # Dashboard 运行时脚本
```

### Dashboard 输出说明

- 浏览器打开 `dashboard/index.html` 即可访问统一仪表盘入口。
- `output/dashboard_manifest.js` 记录每个阶段的 summary 与 shard 列表，供页面按需加载。
- `output/dashboard_stage*.js` 是阶段数据分片，滚动和切换阶段时增量加载，避免一次性加载全部结果。
- `output/previews/*.webp` 是离线预览图；悬停卡片时会回切到原 GIF，加载失败会回退预览图。
- 当前提供的交互控件包括：`search`（按文件名搜索）和 `hide-noise`（隐藏噪声项）。
- 噪声簇（`-1`）默认隐藏；取消 `hide-noise` 后才会显示。

### JSON 格式示例

```json
{
  "0": ["/path/a.gif", "/path/b.gif", "/path/c.gif"],
  "1": ["/path/d.gif", "/path/e.gif"],
  "-1": ["/path/noise1.gif"]
}
```

- **key** 为聚类 ID（`-1` 表示未归入任何聚类的 GIF）
- **value** 为该聚类内的 GIF 路径列表

---

## 性能参考（10 万 GIF，Mac mini M1）

| 阶段 | 预计耗时 | 备注 |
|---|---|---|
| Stage 1 pHash | ~30 分钟 | CPU，O(n²) 比较，可并行优化 |
| Stage 2 CLIP 提取 | ~2–4 小时 | MPS 加速约 30–60 分钟 |
| FAISS 建索引 | ~2 分钟 | CPU |
| HDBSCAN 聚类 | ~5–10 分钟 | CPU |

> **Tip**：CLIP embedding 结果会缓存到 `output/clip_embeddings_cache.npz`，  
> 二次运行直接复用，只处理新增 GIF。

---

## 调参建议

- `--hash_thresh`：值越小越严格。建议先用 10，若误判同源太多则调低到 6。
- `--min_cluster`：HDBSCAN 最小簇大小。GIF 库很大时可调高到 5–10 避免过多小簇。
- `--frames`：采样帧越多，动作特征越准，但速度越慢。推荐 6–12。

---

## Technical Architecture

```text
gif_similarity.py
    -> CLI argument parsing
    -> PipelineConfig construction
    -> run_pipeline(...)

gif_similarity_finder/
    io.py          # GIF collection and frame sampling
    stage1.py      # pHash-based same-source grouping
    stage2.py      # CLIP embedding extraction and clustering
    artifacts.py   # cache, json, index, visualization outputs
    dashboard_*.py # dashboard data and output artifact generation
    pipeline.py    # orchestration
    types.py       # shared result models
```

---

## License

MIT
