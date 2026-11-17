# Zotero PDF to Markdown

将 Zotero 文献库中的 PDF 批量转换为 Markdown（`.md`），用于 Cherry Studio Knowledge Base 和本地 RAG 文献检索。

## 1. 项目简介

本项目用于递归扫描 Zotero PDF 文件夹，将 PDF 转换为 Markdown 文档。

主要特点：

- **批量转换**：递归扫描输入目录及其所有子目录。
- **双级解析**：优先使用 PyMuPDF 快速提取文本，复杂 PDF 使用 Docling 进行结构化解析。
- **保留目录结构**：输出 Markdown 保留原 PDF 的相对目录结构。
- **记录原始路径**：每个 Markdown 文件开头记录对应 PDF 的完整路径，方便定位原文。
- **跳过已转换文件**：通过文件大小和修改时间判断 PDF 是否发生变化，避免重复转换。
- **自动重试失败文件**：转换失败的文件不会被标记为成功，下次运行时会重新尝试。
- **不导出图片**：不保存 PDF 中的图片，节省存储空间。
- **保留图注信息**：尽可能保留 Figure 标题、图注和正文中的相关文字，方便通过 Markdown 检索后回到原始 PDF 查看图片。

原始 PDF 不会被修改、移动或删除。

## 2. 项目结构

```text
pdf2md/
├── .venv/                      # Python 虚拟环境
├── pdf2md.py                   # PDF 转 Markdown 主程序
├── run.sh                      # 一键运行脚本
└── README.md                   # 项目说明

输入目录：
~/Zotero/storage/

输出目录：
~/AI/zotero_markdown/
```

输出目录会自动保留输入目录中的相对路径，例如：

```text
Zotero/storage/
├── A1B2C3D4/
│   └── paper_A.pdf
├── E5F6G7H8/
│   └── paper_B.pdf
└── I9J0K1L2/
    └── paper_C.pdf

zotero_markdown/
├── A1B2C3D4/
│   └── paper_A.md
├── E5F6G7H8/
│   └── paper_B.md
└── I9J0K1L2/
    └── paper_C.md
```

## 3. 环境配置

本项目使用 [uv](https://docs.astral.sh/uv/) 管理 Python 虚拟环境和依赖。

### 3.1 安装 uv

macOS 使用 Homebrew：

```bash
brew install uv
```

### 3.2 创建项目目录

```bash
mkdir -p ~/AI/pdf2md
cd ~/AI/pdf2md
```

### 3.3 创建虚拟环境

```bash
uv venv
```

这会在项目目录下创建 `.venv/`。

### 3.4 安装依赖

```bash
uv pip install pymupdf docling
```

主要依赖：

| Package | 用途 |
|---|---|
| PyMuPDF | 快速提取 PDF 文本 |
| Docling | 复杂 PDF 的结构化解析，包括版面和表格识别 |

建议在依赖安装完成后保留 `uv.lock` 或记录依赖版本，方便以后复现环境。

## 4. 路径配置

打开 `pdf2md.py`，在脚本顶部设置输入和输出目录：

```python
from pathlib import Path

PDF_INPUT = Path("~/Zotero/storage").expanduser()
MD_OUTPUT = Path("~/AI/zotero_markdown").expanduser()
```

根据自己的实际目录修改即可。

其他重要参数：

```python
SKIP_EXISTING = True

ENABLE_DOCLING = True
ENABLE_OCR = True
```

| 参数 | 说明 |
|---|---|
| `SKIP_EXISTING = True` | 跳过已经成功转换且 PDF 未发生变化的文件 |
| `SKIP_EXISTING = False` | 重新转换所有 PDF |
| `ENABLE_DOCLING = True` | 启用 Docling 复杂 PDF 解析 |
| `ENABLE_OCR = True` | 启用 OCR，以处理扫描版或文本提取困难的 PDF |

如果不需要 OCR，可以将 `ENABLE_OCR` 设置为 `False`，但扫描版 PDF 可能无法正确提取文字。

## 5. 一键运行

项目中已经准备了 `run.sh`：

```bash
#!/bin/bash

source .venv/bin/activate
python pdf2md.py
```

第一次需要赋予执行权限：

```bash
chmod +x run.sh
```

之后进入项目目录，直接运行：

```bash
./run.sh
```

不需要每次手动激活 Python 虚拟环境。

如果希望从其他目录运行，也可以使用：

```bash
cd ~/AI/pdf2md && ./run.sh
```

## 6. 转换流程

程序按照以下流程处理 PDF：

1. 递归扫描输入目录，寻找所有 PDF 文件。
2. 检查转换记录，判断文件是否已经成功转换。
3. 如果 PDF 没有发生变化，且对应 Markdown 文件存在，则跳过。
4. 优先使用 PyMuPDF 提取文本。
5. 如果检测到复杂版面、双栏结构、表格或文本提取异常，则尝试使用 Docling。
6. 将提取结果写入 Markdown。
7. 更新转换记录。

### PDF 解析策略

**PyMuPDF**

适用于普通文本型 PDF，解析速度快，适合快速批量提取。

**Docling**

适用于版面复杂的论文，例如双栏排版、复杂表格和扫描版 PDF。它可以提供更好的结构化解析结果，但通常需要更多计算时间。

需要注意：双栏和复杂版面的自动检测是启发式判断，并不能保证识别所有复杂 PDF。对于特别重要的文献，建议抽查 Markdown 的阅读顺序和表格内容。

## 7. Markdown 输出格式

每篇 PDF 对应一个独立的 Markdown 文件。

文件开头包含原始 PDF 路径等信息：

```yaml
---
source_pdf: "/Users/username/Zotero/storage/A1B2C3D4/paper.pdf"
source_filename: "paper.pdf"
parser: "PyMuPDF"
---
```

正文包含提取的论文文本。

如果使用 PyMuPDF 快速解析，正文可能按 PDF 页码组织；如果使用 Docling，则尽可能保留章节、标题、表格和图注等结构。

图片不会单独导出。Figure 相关文字和图注会尽可能保留，阅读时可以通过 `source_pdf` 路径回到原始 PDF 查看图片。

## 8. 转换记录与增量更新

输出目录中会生成转换记录：

```text
zotero_markdown/
├── _conversion_manifest.json
├── _conversion_failures.txt
├── _conversion_times.tsv
├── A1B2C3D4/
│   └── paper_A.md
└── ...
```

### `_conversion_manifest.json`

记录每个 PDF 的：

- 文件大小
- 最后修改时间
- 转换状态
- 使用的解析器
- Markdown 输出路径
- 转换时间

程序通过文件大小和修改时间判断 PDF 是否发生变化。

### `_conversion_failures.txt`

记录转换失败的 PDF，方便检查。

### `_conversion_times.tsv`

记录转换耗时，方便评估不同 PDF 的解析速度。

### 增量更新机制

每次运行 `./run.sh` 时，程序都会重新扫描 Zotero 文件夹。

| 情况 | 处理方式 |
|---|---|
| 新增 PDF | 自动转换 |
| PDF 未变化 | 跳过 |
| PDF 内容更新且文件大小或修改时间变化 | 重新转换 |
| 上次转换失败 | 再次尝试 |
| Markdown 文件被删除 | 重新转换 |
| 强制全量转换 | 设置 `SKIP_EXISTING = False` |

注意：这里的变化检测基于文件大小和修改时间，并不是文件内容哈希。极少数情况下，如果文件内容改变但这两个属性没有变化，可能无法检测到。

## 9. 与 Cherry Studio 配合

建议采用以下流程：

```text
Zotero
  │
  │ PDF storage
  ▼
pdf2md.py
  │
  │ PDF → Markdown
  ▼
zotero_markdown/
  │
  │ Cherry Studio Knowledge Base
  ▼
Embedding
  │
  ▼
Vector Database
  │
  ▼
Literature RAG
```

推荐工作方式：

1. 正常使用 Zotero 管理和添加文献。
2. 需要更新文献库时，运行 `./run.sh`。
3. 程序自动识别新增或发生变化的 PDF。
4. 在 Cherry Studio 中更新 Knowledge Base 的文档索引。
5. 通过 Agent 检索文献内容。

建议让 Cherry Studio 读取 Markdown 输出目录，而不是直接读取 Zotero 原始 PDF 目录。

这样可以避免重复解析 PDF，也方便统一管理 RAG 文本。

## 10. 注意事项

- 不要直接修改 Zotero 的原始 PDF 文件。
- 不要将 `.venv` 文件夹添加到 Cherry Studio Knowledge Base。
- 建议将 `_conversion_manifest.json`、`_conversion_failures.txt` 和 `_conversion_times.tsv` 排除在知识库索引之外。
- 不建议把图片批量导出到 Markdown 目录，以免占用大量磁盘空间。
- Docling 首次运行可能需要下载模型文件，首次解析速度可能明显慢于后续运行。
- OCR 会增加计算开销，建议仅在确实需要扫描版 PDF 识别时启用。
- Markdown 转换完成后，仍建议抽查部分复杂论文，尤其是双栏正文、表格和特殊符号。

---

**日常使用只需要一条命令：**

```bash
./run.sh
```

新增的 Zotero 文献会在下一次运行时自动被扫描和转换。
