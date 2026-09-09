# 给 Windows 智能体的一次性安装指令

把下面整段连同仓库链接交给 Windows 上的 Codex / 电脑智能体即可：

```text
请在这台 Windows NVIDIA 电脑上安装并启动 GPT Cleaner：
https://github.com/Luocatcat/gpt-cleaner

要求：
1. 克隆仓库到一个独立目录，不要污染我已有 Python / ComfyUI 环境。
2. 先完整阅读仓库根目录 AGENTS.md，并严格按它执行。
3. 运行 install.ps1，自动检查 NVIDIA GPU、显存、Python、Git 和依赖。
4. 允许安装脚本下载 ComfyUI、开源 CCSR 模型及必要依赖，但不要调用任何商业 AI API，也不要把我的图片上传到外部服务。
5. 遇到可以自动处理的依赖、PATH、CUDA、显存或启动问题，请自行诊断和修复，不要第一时间把步骤甩给我。
6. ComfyUI 8188 只能监听 127.0.0.1，不允许直接暴露公网。
7. 安装完成后运行 doctor.ps1，自检必须通过。
8. 启动 GPT Cleaner，确认 http://127.0.0.1:8787/api/health 正常，再自动打开 http://127.0.0.1:8787。
9. 如果环境允许，再运行 scripts/smoke_test.py 做一次端到端测试，并告诉我结果图保存位置。
10. 最后只向我汇报：是否安装成功、网页地址、GPU/显存识别结果、smoke test 是否通过，以及是否有仍需我确认的问题。
```

以后日常使用不需要智能体，双击：

```text
START_GPT_CLEANER.bat
```
