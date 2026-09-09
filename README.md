# GPT Cleaner

**洗掉 GPT 味**：一个本地优先的 AI 生图清理工具，专门处理 GPT / diffusion 生图里常见的垃圾高频信息，例如假发丝、塑料高光、脏纹理、随机细碎材质和过度锐化，同时尽量锁住原始角色结构。

> 目标不是“把错误高清化”，而是：**先清掉坏细节，再重建更自然的材质。**

## 你最终怎么用

Windows 算力机第一次安装：

```powershell
git clone https://github.com/Luocatcat/gpt-cleaner.git
cd gpt-cleaner
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

以后双击：

```text
START_GPT_CLEANER.bat
```

浏览器会自动打开 `http://127.0.0.1:8787`。

界面只暴露三个设计师需要的参数：

- GPT 味：轻微 / 标准 / 严重
- 结构保护：严格 → 自由
- 输出：原尺寸 / 2X / 4X

底层参数、tile、显存配置都隐藏。

## 架构

```text
Mac / 浏览器
      ↓
GPT Cleaner Web :8787
      ↓
高频预清洗（本机 OpenCV）
      ↓
ComfyUI :8188（只绑定 localhost）
      ↓
CCSR 生成式修复
      ↓
结果返回网页
```

不调用商业 AI API。用户图片只在自己的 Windows 机器上处理。

## V0 引擎说明

为了先把“一键安装 + 极简网页 + 8GB 显存可运行”的完整闭环跑通，V0 使用 `kijai/ComfyUI-CCSR` 的 real-world CCSR fp16 模型作为 ComfyUI 引擎。模型由 Hugging Face 的 `Kijai/ccsr-safetensors` 自动下载。

官方 CCSR-v2 是下一阶段 benchmark 路线。它支持 1–2 step 和 tile diffusion，但目前没有一个同样成熟、低维护成本的原生 ComfyUI v2 节点，因此 V0 不冒充 CCSR-v2。等 Test 001 与研森结果完成对比后，再决定是否替换后端，网页不用重做。

## 推荐硬件

当前目标机：

- Windows 64-bit
- NVIDIA RTX 5060 8GB
- 32GB RAM
- Ryzen 9 7900X

安装器会自动检查 NVIDIA GPU / VRAM，并对 8GB 显存使用保守 tile 配置。

## 智能体安装

如果在 Windows 上由 Codex / 其他智能体安装，请让它先完整阅读根目录 `AGENTS.md`，然后执行 `install.ps1`。安装失败时按 `AGENTS.md` 的自修复规则处理，不要手工污染用户已有 Python 环境。

## 当前状态

- [x] GitHub 仓库
- [x] Windows 安装/启动骨架
- [x] 极简 Web UI
- [x] ComfyUI bridge
- [x] 高频预清洗
- [x] 8GB VRAM preset
- [ ] Windows 真机安装 smoke test
- [ ] Test 001：现代魔女原图 vs 研森 1K
- [ ] 参数 benchmark
- [ ] CCSR-v2 / 其他 restoration 引擎 AB test
