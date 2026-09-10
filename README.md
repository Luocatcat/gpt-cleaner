# GPT Cleaner V0.3

**洗掉 GPT 味**：本地优先的 AI 生图清理工具。目标不是把原图简单锐化，而是：

> **先压掉 GPT / diffusion 图里错误的微纹理和乱光，再用语义修复重新长回合理细节，同时尽量锁住人物/角色结构。**

当前主目标是现代魔女 / BJD / CGI 这类已经定稿的角色图：减少假发丝、塑料高光、脏纹、随机块状光影和重复 AI 纹理，同时保住脸型、五官位置、发型轮廓和关节结构。

## V0.3 为什么重做

V0.1 的旧 CCSR 路线过度生成，会改脸并产生新的脏纹；V0.2 的传统频率清理虽然能把 GPT 乱光和纹路磨掉，但会把有效细节一起洗没，结果过于模糊。

V0.3 改成三段式：

```text
GPT 原图
  ↓
控制性降质 / 缩小
去掉不稳定 GPT 微纹理
  ↓
SUPIR 语义修复
重新生成材质层次、眼睛、头发块面内部细节
  ↓
多尺度结构融合
大轮廓几乎来自原图
中频材质和高频细节更多来自 restoration
  ↓
1X 成品
```

关键变化：**结构保护不再等于“把所有生成效果关掉”**。它主要保护宏观轮廓和五官位置，而不是把假发丝、脏纹和错误高光也一起锁死。

## 当前引擎

V0.3 benchmark 使用：

- ComfyUI
- `kijai/ComfyUI-SUPIR` 的 SUPIR wrapper，作为快速验证语义修复效果的第一候选
- `SUPIR-v0Q_fp16.safetensors`
- `sd_xl_base_1.0.safetensors`
- 8GB 显存默认开启 tiled sampling / tiled VAE / fp8 UNet
- OpenCV 只负责轻量预清洗，不再承担最终“修图”职责
- 自研多尺度频率融合负责把原图结构压回结果

> `ComfyUI-SUPIR` README 已说明 SUPIR 也已经进入 ComfyUI core。当前仓库仍暂用 Kijai wrapper，是因为它的单节点接口和 8GB 显存选项更方便做 V0.3 benchmark。效果参数锁定后再决定是否迁移到 core。

SUPIR 项目包含非商业使用限制。这个仓库当前按**个人自用 / benchmark**定位；如果未来要商业化，需要重新检查 SUPIR 授权或替换模型。

## Windows 已安装旧版的升级方式

已有 `D:\gpt-cleaner` 的机器不要重装整个环境，也不要删除 `runtime/`。

双击：

```text
UPDATE_GPT_CLEANER.bat
```

升级器会：

1. 停止 8787 / 8188 当前本地服务；
2. 下载最新仓库程序代码；
3. 保留 `runtime/`、旧 PyTorch、ComfyUI、旧 CCSR 模型和日志；
4. 安装 `ComfyUI-SUPIR`；
5. 下载 SUPIR-v0Q fp16（约 2.7 GB）；
6. 下载 SDXL base checkpoint（约 6.9 GB）；
7. 自动生成 RTX 5060 8GB 对应 tile 配置；
8. 运行 `doctor.ps1`；
9. 启动网页。

首次升级 V0.3 会新增约 9.6 GB 模型下载，之后日常升级不会重复下载。

## 新机器安装

```powershell
git clone https://github.com/Luocatcat/gpt-cleaner.git
cd gpt-cleaner
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

以后双击：

```text
START_GPT_CLEANER.bat
```

浏览器打开：

```text
http://127.0.0.1:8787
```

## 网页 V0.3

日常界面仍然保持极简：

- `语义精修`：默认主模式，SUPIR + 多尺度结构融合
- `安全清理`：传统非生成式备用，不会新增细节
- GPT 味 / 重建力度：轻 / 标准 / 强
- 结构保护：70–100
- 当前固定 **1X**，先把“洗 GPT 味”的质感做到正确，再恢复 2X / 4X

另有一个临时调参入口：

### 四版 Benchmark

一次输入自动生成：

```text
A_clean-base.png
B_semantic-low.png
C_semantic-mid.png
D_structure-safe.png
```

含义：

- A：只看控制性降质后是否成功压掉 GPT 垃圾；它模糊是正常的，不是成品
- B：低强度语义重建
- C：当前主候选，目标接近研森的“干净 + 有细节”
- D：使用与 C 相同的 SUPIR 结果，但加强结构融合，用来观察角色一致性上限

Benchmark 中间图会留在：

```text
runtime/benchmarks/
```

普通语义处理的调试中间图会留在：

```text
runtime/debug/
```

里面能看到 `degraded`、`supir_raw` 和最终 `semantic_fused`，方便判断到底是哪一步导致变糊 / 改脸 / 出现纹理。

## 自检

```powershell
powershell -ExecutionPolicy Bypass -File .\doctor.ps1
```

基础安全测试：

```powershell
.\runtime\venv\Scripts\python.exe .\scripts\smoke_test.py --safe
```

SUPIR 语义链路测试：

```powershell
.\runtime\venv\Scripts\python.exe .\scripts\smoke_test.py --semantic
```

四版测试：

```powershell
.\runtime\venv\Scripts\python.exe .\scripts\smoke_test.py --benchmark
```

## 本地与远程

- ComfyUI 永远只监听 `127.0.0.1:8188`
- GPT Cleaner Web 默认监听 `0.0.0.0:8787`
- Mac 远程使用时建议通过 Tailscale /可信局域网访问 Windows 的 8787
- 不调用商业 AI API
- 图片处理发生在自己的 Windows 算力机

## 当前目标机

- Windows 64-bit
- Ryzen 9 7900X
- 32 GB RAM
- NVIDIA RTX 5060 8 GB

## 当前开发状态

- [x] V0.1 旧 CCSR 闭环验证
- [x] V0.2 传统高频清理验证，确认“干净但过糊”
- [x] V0.3 控制性降质代码
- [x] V0.3 SUPIR semantic workflow 接口
- [x] 多尺度结构融合
- [x] 8GB tiled / fp8 配置
- [x] 四版 Benchmark 接口与网页
- [x] 增量升级脚本
- [ ] RTX 5060 真机 V0.3 semantic smoke test
- [ ] 现代魔女 Test 001 四版结果
- [ ] 与研森 1K 做逐区域 AB 对比
- [ ] 根据 Test 001 锁定最终权重
