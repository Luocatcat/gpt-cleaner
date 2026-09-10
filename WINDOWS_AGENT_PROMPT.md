# 给 Windows 豆包 / Codex 智能体的指令

## 当前这台已经安装过旧版的 Windows 机器

直接把下面整段复制给 Windows 智能体：

```text
请把现有 D:\gpt-cleaner 升级到 GitHub 最新 GPT Cleaner V0.3：
https://github.com/Luocatcat/gpt-cleaner

这是增量升级，不允许删除或重装现有 runtime。

先完整阅读仓库最新 AGENTS.md，再执行。

必须保留：
- D:\gpt-cleaner\runtime\venv
- D:\gpt-cleaner\runtime\ComfyUI
- 已下载的 PyTorch / ComfyUI
- 现有 CCSR 节点与 3.4GB CCSR 模型
- runtime 下日志和历史测试图

执行顺序：
1. 进入 D:\gpt-cleaner。
2. 获取 GitHub 最新源码；如果 git pull / clone 网络不稳定，按 AGENTS.md 使用 codeload zip，不要反复卡在 GitHub clone。
3. 运行：powershell -ExecutionPolicy Bypass -File .\update.ps1 -NoStart
4. 允许升级器新增 ComfyUI-SUPIR 节点。
5. 允许下载两个 V0.3 新模型：
   - SUPIR-v0Q_fp16.safetensors，约 2.7GB
   - sd_xl_base_1.0.safetensors，约 6.9GB
   首次 V0.3 新增下载约 9.6GB。优先 Hugging Face，失败自动改用 hf-mirror.com。
6. 不要调用任何商业 AI API，不上传我的图片到外部 AI 服务。
7. ComfyUI 8188 必须只监听 127.0.0.1。
8. 升级后确认 config\local.json 的 default_mode=semantic，并针对 RTX 5060 8GB 使用 SUPIR tiled sampling / tiled VAE / fp8 UNet。
9. 运行：powershell -ExecutionPolicy Bypass -File .\doctor.ps1
10. doctor 必须 PASS；如果失败，按照 AGENTS.md 自动排查修复，不要先把常规问题丢给我。
11. 启动：powershell -ExecutionPolicy Bypass -File .\start.ps1
12. 检查 http://127.0.0.1:8787/api/health，必须看到 comfy=true 且 supir=true。
13. 运行安全 smoke test：
    .\runtime\venv\Scripts\python.exe .\scripts\smoke_test.py --safe
14. 再运行 SUPIR 语义 smoke test：
    .\runtime\venv\Scripts\python.exe .\scripts\smoke_test.py --semantic
15. semantic smoke test 通过后自动打开 http://127.0.0.1:8787。

不要替我自动运行真实魔女图的四版 benchmark。我会在网页手动上传真实图并点「生成四版对比」。

如果出现 CUDA OOM：
- SUPIR sampler tile 512 -> 384
- stride 256 -> 192
- VAE tile 512 -> 384
- 重启 ComfyUI 后重试一次
不要用简单锐化来掩盖问题，也不要降低最终 1X 输出尺寸。

最后只汇报：
- V0.3 是否升级成功
- GPU / 显存识别结果
- SUPIR 节点是否加载
- SUPIR-v0Q 和 SDXL 模型是否完整
- doctor 是否 PASS
- safe smoke test 是否 PASS
- semantic smoke test 是否 PASS，以及输出路径
- 网页地址
- 是否还有需要我确认的问题
```

## V0.3 升级完成后用户怎么测试

网页打开后：

1. 上传同一张现代魔女 / BJD 原图；
2. 不要先用 2X / 4X，V0.3 当前固定 1X；
3. 先直接跑 `语义精修 / 标准 / 结构保护94`；
4. 再点 `生成四版对比`；
5. 网页会返回：
   - A Clean Base
   - B Semantic Low
   - C Semantic Mid
   - D Structure Safe
6. 用户把 B/C/D 和研森 1K 一起发回 ChatGPT 做逐区域对比。

A 发软是预期行为，它只是“洗掉 GPT 垃圾后的底图”，不是最终成品。

## 新机器第一次安装

如果机器上完全没有 GPT Cleaner：

```text
请安装并启动这个项目：
https://github.com/Luocatcat/gpt-cleaner

优先安装到 D:\gpt-cleaner。
完整阅读 AGENTS.md 后运行 install.ps1。
不要污染已有全局 Python / ComfyUI。
安装结束必须 doctor PASS、supir=true、semantic smoke test PASS 后才算成功。
```

之后日常使用只需要双击：

```text
START_GPT_CLEANER.bat
```
