# GPT Cleaner

**洗掉 GPT 味**：一个本地优先的 AI 生图清理工具，专门处理 GPT / diffusion 生图里常见的垃圾高频信息，例如假发丝、塑料高光、脏纹理、随机细碎材质和过度锐化，同时尽量锁住原始角色结构。

> 核心目标不是“把错误高清化”，而是：**先删掉坏细节，再只补需要的细节。**

## 当前推荐工作流

V0.2 开始分成两条路线：

```text
安全清理（默认）
原图 → 高频抑制 → 强边缘保护 → 精确尺寸输出

AI 重建（实验）
原图 → 高频预清洗 → CCSR 少量重建 → 原图低频结构回灌 → 精确尺寸输出
```

`安全清理` 不让生成模型接管整张图，适合角色设定、三视图、UI/视觉稿和已经基本定稿的图。

`AI 重建` 只用于需要重新长一点材质的图片。V0.2 已加入结构回灌，但当前 CCSR-v1 ComfyUI wrapper 仍属于过渡引擎，后续会继续 benchmark 官方 CCSR-v2 / 其他 restoration 模型。

## Windows 第一次安装

```powershell
git clone https://github.com/Luocatcat/gpt-cleaner.git
cd gpt-cleaner
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

如果 GitHub 直连不稳定，智能体可以直接下载仓库 zip。`install.ps1` 对 ComfyUI / CCSR 依赖本身也带 codeload zip fallback。

以后双击：

```text
START_GPT_CLEANER.bat
```

浏览器会自动打开 `http://127.0.0.1:8787`。

更新代码但保留本机已下载的模型和 runtime：

```text
UPDATE_GPT_CLEANER.bat
```

## 网页参数

- 处理方式：安全清理 / AI 重建
- GPT 味：轻微 / 标准 / 严重
- 结构保护：自由 → 严格
- 输出：原尺寸 / 2X / 4X

角色设定图建议：**安全清理 + 标准 + 结构保护 94–100**。

## 架构

```text
Mac / 浏览器
      ↓
GPT Cleaner Web :8787
      ↓
高频清理（OpenCV，确定性）
      ├────────────→ 安全清理直接输出
      │
      └→ ComfyUI :8188（可选）
             ↓
          CCSR 重建
             ↓
      原图低频结构回灌
             ↓
          结果返回网页
```

不调用商业 AI API。用户图片只在自己的 Windows 机器上处理。

## 已验证的 Windows 安装问题

V0.2 已把第一次真机安装踩到的问题收回仓库：

- PowerShell 5.1 下 `nvidia-smi | Select-Object -First 1` 可能导致退出码异常，现改为完整收集后再取第一行。
- Windows Store `python.exe` 存根可能被误判为真实 Python，现会校验版本、退出码和实际可执行路径。
- 当前 ComfyUI / transformers 需要较新的 `huggingface_hub`，依赖已调整到 `>=1.5,<2`。
- GitHub clone 不稳定时自动 fallback 到 `codeload.github.com` zip。
- Hugging Face 模型直连失败时自动 fallback 到 `hf-mirror.com`。
- 新版 ComfyUI 不再保证 `custom_nodes/` 在 `sys.path`，安装器会给 ComfyUI-CCSR 自动加入兼容补丁。

## V0.1 为什么效果差

第一次真实角色三视图测试暴露出：旧 CCSR wrapper 在已较清晰的 GPT 图上会过度生成，出现改脸、发束重画、关节/轮廓异常、色彩漂移、背景 tile 纹理等问题。

V0.2 因此做了三件关键调整：

1. 默认不再整张交给生成模型，而是先走确定性的安全清理。
2. AI 重建大幅缩小采样窗口和 steps，并改用 wavelet 色彩修复与 Gaussian tile blending。
3. AI 结果不直接输出，先把原图的低频结构压回去，只借少量生成高频细节。

## 当前硬件目标

- Windows 64-bit
- NVIDIA RTX 5060 8GB
- 32GB RAM
- Ryzen 9 7900X

安装器会自动检查 NVIDIA GPU / VRAM，并按显存选择 tile 配置。

## 智能体安装

Windows 上由 Codex / 豆包 / 其他智能体安装时，请让它先完整阅读根目录 `AGENTS.md`，然后执行 `install.ps1`。安装失败时按 `AGENTS.md` 的自修复规则处理，不要污染用户已有 Python 环境。

## 当前状态

- [x] GitHub 仓库
- [x] Windows 真机安装跑通
- [x] 极简 Web UI
- [x] 确定性高频安全清理
- [x] ComfyUI bridge
- [x] 8GB VRAM preset
- [x] 真机 smoke test
- [x] 首次角色图实测并发现 V0.1 过度生成问题
- [x] V0.2 结构保护重构
- [ ] 用同一张现代魔女原图重新跑 V0.2 安全清理 / AI 重建
- [ ] 与研森 1K 做局部 A/B 对比
- [ ] 官方 CCSR-v2 / 其他 restoration 引擎 benchmark
