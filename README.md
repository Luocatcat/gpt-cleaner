# GPT Cleaner V0.3

本地处理 GPT / diffusion 生图中的假发丝、塑料高光、脏微纹理、重复材质和过度锐化。V0.3 不再把传统高频清理当主路线，而是先打散不稳定细节，再做受控语义修复。

## 默认工作流

```text
语义修复（默认，V0.3 只做 1X）
原图
  → 控制性缩小与微纹理清理
  → ComfyUI Core SUPIR
  → 多尺度 Laplacian 融合
  → 恢复原尺寸

自动回退
SUPIR → 旧 CCSR → safe 安全清理
```

网页会显示实际使用的引擎和回退原因，不会把 CCSR 或 safe 结果冒充 SUPIR。

`安全清理` 仍可独立使用，不经过生成模型，保留 1X、2X 和 4X 输出。旧 `ComfyUI-CCSR` 只作为兼容回退，不是官方 CCSR-v2。

## 为什么改路线

V0.2 只压高频，而且会把头发、眼睛、关节附近的大量假细节当作结构保护；旧 CCSR 路线又只允许很少生成信息参与，结果通常只是稍微软一点，无法重建头发块面、皮肤光影和 BJD 材质。

V0.3 改为：

1. 先把长边降至 768–1024 px，清掉不稳定微纹理；
2. 用 SUPIR 重建中频材质与细节；
3. 用五层 Laplacian 金字塔把原图轮廓、比例和低频结构压回；
4. 精确恢复原图尺寸。

技术与验收背景见 [Issue #1](https://github.com/Luocatcat/gpt-cleaner/issues/1)。SUPIR 节点和基础模型组合参考 [ComfyUI 官方工作流](https://github.com/Comfy-Org/workflow_templates/blob/main/templates/utility_image_upscale_supir.json)。

## Windows 首次安装

目标环境：Windows 64 位、NVIDIA 显卡，主要适配 RTX 5060 8GB。

```powershell
git clone https://github.com/Luocatcat/gpt-cleaner.git D:\gpt-cleaner
Set-Location D:\gpt-cleaner
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1
```

安装器使用独立 `runtime\venv` 和 `runtime\ComfyUI`，不会改用户已有 Python 或 ComfyUI。

V0.3 新增两个模型：

- `juggernautXL_v9Rdphoto2Lightning.safetensors`：约 7.11 GB；
- `SUPIR-v0Q_fp16.safetensors`：约 2.66 GB。

首次安装或从 V0.2 升级前，建议至少留出 12 GB 可用空间。旧 CCSR 模型继续保留。

## 从 V0.2 增量升级

V0.2 机器可能是 codeload zip 安装，没有 `.git`。第一次运行旧 updater 只负责取得 V0.3 脚本；第二次运行新版 updater 才会检查 SUPIR 并下载缺失模型。因此从 V0.2 升级时连续运行两次：

```powershell
Set-Location D:\gpt-cleaner
powershell -NoProfile -ExecutionPolicy Bypass -File .\update.ps1 -NoStart
powershell -NoProfile -ExecutionPolicy Bypass -File .\update.ps1 -NoStart -SkipDoctor
powershell -NoProfile -ExecutionPolicy Bypass -File .\doctor.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\start.ps1
```

升级会保留：

- `runtime\venv` 与已安装 PyTorch；
- `runtime\ComfyUI`、旧 CCSR 节点和模型；
- 所有模型、日志和临时输出；
- `config\local.json` 原始字节与显存配置。

它只更新应用代码、缺失的 ComfyUI Core 文件和依赖，并下载缺失的两个语义模型。日后已在 V0.3 时，双击 `UPDATE_GPT_CLEANER.bat` 一次即可。

## 启动与验证

双击：

```text
START_GPT_CLEANER.bat
```

或运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\start.ps1
```

网页地址：`http://127.0.0.1:8787`

验证命令：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\doctor.ps1
.\runtime\venv\Scripts\python.exe .\scripts\smoke_test.py --safe
.\runtime\venv\Scripts\python.exe .\scripts\smoke_test.py --semantic
.\runtime\venv\Scripts\python.exe .\scripts\smoke_test.py --ccsr
```

`--semantic` 只有实际运行 SUPIR 才输出 PASS。转到旧 CCSR 或 safe 会输出 PARTIAL，并带回退原因。

## 8GB 显存策略

- ComfyUI 使用 `--lowvram`；
- SUPIR 工作长边为 768–1024 px；
- V0.3 语义修复只输出 1X；
- VAE 使用 512 px 分块解码；
- 不下载或运行额外的 Qwen 自动看图描述模型；
- CCSR 保持 256/128 分块，并按本机显存继续使用旧配置。

## 隐私与端口

- 图片只在本机处理；
- 不调用商业 AI API，不需要 API key；
- ComfyUI 只监听 `127.0.0.1:8188`；
- 网页服务监听 `8787`。

## 当前验证状态

- 已完成：配置兼容、控制性降质、SUPIR API 图、多尺度融合、可见回退、Windows 增量升级合同、safe 本机 smoke test。
- 待 Windows 验证：RTX 5060 8GB 上真实 SUPIR 推理、`doctor.ps1`、`--semantic` smoke test。
- 待视觉验收：现代魔女/BJD 原图与研森 1K 的局部 A/B。

在 Windows 真机和目标图片验证前，V0.3 的代码状态可以通过，但最终视觉效果仍应标为 `partial`。
