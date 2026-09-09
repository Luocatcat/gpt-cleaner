# 给 Windows 智能体的指令

## A. 第一次安装

把下面整段连同仓库链接交给 Windows 上的 Codex / 豆包 / 电脑智能体即可：

```text
请在这台 Windows NVIDIA 电脑上安装并启动 GPT Cleaner：
https://github.com/Luocatcat/gpt-cleaner

要求：
1. 优先安装到 D:\gpt-cleaner；如果目录已被占用，先检查是否是旧版 GPT Cleaner，不要覆盖无关文件。
2. 不要污染我已有 Python / ComfyUI 环境。
3. 先完整阅读仓库根目录 AGENTS.md，并严格按它执行。
4. 运行 install.ps1，自动检查 NVIDIA GPU、显存、Python、Git 和依赖。
5. 允许安装脚本下载 ComfyUI、开源 CCSR 模型及必要依赖，但不要调用任何商业 AI API，也不要把我的图片上传到外部服务。
6. 遇到可以自动处理的依赖、PATH、CUDA、显存、GitHub/Hugging Face 网络或启动问题，请自行诊断和修复，不要第一时间把步骤甩给我。
7. ComfyUI 8188 只能监听 127.0.0.1，不允许直接暴露公网。
8. 安装完成后运行 doctor.ps1。
9. 启动 GPT Cleaner，确认 http://127.0.0.1:8787/api/health 正常，再自动打开 http://127.0.0.1:8787。
10. 运行 scripts/smoke_test.py 验证安全清理；如果 ComfyUI/CCSR 可用，再运行 scripts/smoke_test.py --refine 验证 AI 重建。
11. 最后只向我汇报：是否安装成功、网页地址、GPU/显存识别结果、安全清理 smoke test、AI 重建 smoke test，以及是否有仍需我确认的问题。
```

## B. 已经装过旧版，现在升级到 V0.2+

如果 `D:\gpt-cleaner` 已经存在，并且里面已经下载了几 GB 的 PyTorch / ComfyUI / CCSR 模型，不要删掉重装。让智能体执行：

```text
请把 D:\gpt-cleaner 升级到 GitHub 最新版：
https://github.com/Luocatcat/gpt-cleaner

要求：
1. 先阅读最新 AGENTS.md。
2. 保留 D:\gpt-cleaner\runtime 下现有 PyTorch、ComfyUI、模型和日志，不要重新下载大模型，除非缺失或损坏。
3. 保留 config\local.json 的显存配置。
4. 由于这台机器之前可能是通过 codeload zip 安装、没有 .git 元数据，优先使用最新仓库里的 update.ps1 / UPDATE_GPT_CLEANER.bat 逻辑更新源代码。
5. 确认以下已知修复存在：
   - nvidia-smi 不再直接管道到 Select-Object -First 1；
   - Python Store 存根会被识别并忽略；
   - huggingface_hub >=1.5,<2；
   - GitHub codeload fallback；
   - Hugging Face hf-mirror fallback；
   - ComfyUI-CCSR __init__.py 含 GPT_CLEANER_SYSPATH_COMPAT。
6. 更新后重启 GPT Cleaner。
7. 运行 doctor.ps1。
8. 运行 scripts/smoke_test.py。
9. 再运行 scripts/smoke_test.py --refine；如果 AI 重建失败，保留安全清理可用状态并继续诊断，不要删除 runtime 重装。
10. 自动打开 http://127.0.0.1:8787。
11. 告诉我新版网页是否出现「安全清理 / AI 重建」两个处理方式，并汇报两条 smoke test 结果。
```

以后日常使用：

```text
START_GPT_CLEANER.bat
```

以后更新：

```text
UPDATE_GPT_CLEANER.bat
```
