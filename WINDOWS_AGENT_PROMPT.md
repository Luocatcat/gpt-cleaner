# 给 Windows 豆包 / 电脑智能体的指令

## A. 从 V0.2 增量升级到 V0.3

把下面整段交给 Windows 豆包：

```text
请把 D:\gpt-cleaner 从 V0.2 增量升级到 GitHub 最新 V0.3：
https://github.com/Luocatcat/gpt-cleaner

先完整阅读仓库最新 AGENTS.md，再执行下面命令：

Set-Location D:\gpt-cleaner
powershell -NoProfile -ExecutionPolicy Bypass -File .\update.ps1 -NoStart
powershell -NoProfile -ExecutionPolicy Bypass -File .\update.ps1 -NoStart -SkipDoctor
powershell -NoProfile -ExecutionPolicy Bypass -File .\doctor.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\start.ps1
.\runtime\venv\Scripts\python.exe .\scripts\smoke_test.py --safe
.\runtime\venv\Scripts\python.exe .\scripts\smoke_test.py --semantic
.\runtime\venv\Scripts\python.exe .\scripts\smoke_test.py --ccsr

必须遵守：
1. 连续运行两次 update.ps1。第一次让旧 V0.2 updater 取得 V0.3 脚本；第二次才执行 V0.3 SUPIR 增量安装。
2. 保留 D:\gpt-cleaner\runtime 下现有 venv、PyTorch、ComfyUI、CCSR 模型、其他模型、日志和输出，不删除重装。
3. 保留 config\local.json 原文件和显存设置。
4. 只补下载缺失的 juggernautXL_v9Rdphoto2Lightning.safetensors 与 SUPIR-v0Q_fp16.safetensors。不要下载 Qwen 自动描述模型。
5. 如果 ComfyUI Core 缺少 SUPIRApply，只更新 D:\gpt-cleaner\runtime\ComfyUI 的核心代码；保留 models、custom_nodes、input、output、temp、user 和 .git。
6. 保留旧 ComfyUI-CCSR 和 GPT_CLEANER_SYSPATH_COMPAT，作为第二级回退。
7. 不要改全局 Python，不要重装 PyTorch，不要操作用户其他 ComfyUI。
8. ComfyUI 8188 只能监听 127.0.0.1。
9. doctor 输出 PARTIAL 时继续看具体缺项，不要把 safe 可用说成全部失败，也不要把回退结果说成 SUPIR 成功。
10. 最后只汇报：版本、GPU/显存、doctor、safe smoke、semantic smoke 实际引擎、CCSR smoke、网页地址、仍缺什么。
```

升级会新增约 9.77 GB 模型文件。开始前建议 `D:` 至少有 12 GB 可用空间。

## B. 第一次安装 V0.3

```text
请在这台 Windows NVIDIA 电脑上安装 GPT Cleaner V0.3：
https://github.com/Luocatcat/gpt-cleaner

要求：
1. 安装到 D:\gpt-cleaner；若目录已存在，先判断是否旧版 GPT Cleaner，不覆盖无关文件。
2. 先完整阅读 AGENTS.md。
3. 运行：powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1
4. 使用项目自己的 runtime\venv 和 runtime\ComfyUI，不改全局 Python，不碰其他 ComfyUI。
5. 允许下载 ComfyUI、PyTorch、旧 CCSR、Juggernaut XL Lightning 和 SUPIR v0Q fp16；不调用商业 AI API，不上传用户图片。
6. GitHub 或 Hugging Face 直连失败时，按 AGENTS.md 使用 codeload 或 hf-mirror 回退。
7. 安装后运行 doctor.ps1，启动网页，再依次运行 --safe、--semantic、--ccsr smoke test。
8. 只有 --semantic 显示 engine=supir 才算语义主路线通过。CCSR 或 safe 回退只能报 PARTIAL。
9. 自动打开 http://127.0.0.1:8787。
10. 最后只汇报：安装状态、网页地址、GPU/显存、doctor、三条 smoke test、待确认问题。
```

## C. 真图验收

代码与 smoke test 通过后，再让豆包执行：

```text
使用现代魔女/BJD 三视图原图，在网页选择：
语义修复 / 标准 / 结构保护 94–98 / 原尺寸 1X。

确认结果信息写明“实际引擎：SUPIR 语义修复”。
与原图和研森 1K 对比：假发丝、塑料高光、皮肤脏纹、眼睛玻璃感、关节材质、中频光影、改脸、轮廓漂移、tile 接缝。

保存原图、SUPIR 结果和对比截图。没有研森参考图或没有完成局部对比时，视觉验收必须写 PARTIAL。
```
