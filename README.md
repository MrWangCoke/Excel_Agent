# Excel Agent

本项目用于读取原始 Excel 群聊记录，提取问题并输出按日期归档的 Markdown 问题列表。

当前实现进度：步骤 6 单块 LLM 提取已接入主流程；步骤 7-10 待完成。

## 默认目录

```text
excel-agent/
├── data/    # 默认放原始 Excel 文件
├── output/  # 默认输出 Markdown 问题列表
└── .cache/  # 默认保存中间缓存
```

平时使用时，把原始 `.xlsx` 文件放到 `data/` 目录，然后直接运行：

```bash
python main.py --mock
```

步骤 6 的真实模型验证可以只选少量群聊切片，不需要一次处理全部缓存：

```bash
python scripts/run_step6.py --group-dir .cache/groups/<群目录> --max-chunks 1
```

也可以用 `--chunk-id` 精确验证一个切片；正式主流程运行时会按群和 chunk 显示进度，并支持 `--resume` 复用指纹未变化的结果。

如果后期想临时指定其他输入/输出目录，也可以通过命令行参数覆盖默认目录：

```bash
python main.py --input <Excel文件或文件夹> --output <输出目录> --config config/default.json --mock
```

## 安装依赖

```bash
pip install -r requirements.txt
```

## CLI 参数

- `--input`：Excel 文件或文件夹路径，默认 `data/`。
- `--output`：Markdown 输出根目录，默认 `output/`。
- `--config`：配置文件路径，默认 `config/default.json`。
- `--resume`：断点续跑。
- `--mock`：不调用模型，后续用于规则占位跑通流程。

## 配置

- `config/template.json`：Excel 表头映射。
- `config/default.json`：消息类型、切分窗口、候选问题库、上下文预算、模型环境变量名等配置。
- `.env.example`：OpenAI 兼容模型配置示例。
"# Excel_Agent" 
