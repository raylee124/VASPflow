# VASPFlow

面向 Codex 的 VASP 工作流技能：通过本机 OpenSSH 配置访问，在用户授权目录内准备和核验输入，使用站点调度器或个人 Linux 工作站的 `mpirun` 执行计算，并检查收敛、整理后处理结果。

这是独立的 **Skill**，入口是 [SKILL.md](SKILL.md)。不包含插件服务、作者服务器配置、凭据、计算数据、VASP 程序或受许可势文件。

## 功能与前提

- 中文/英文独立终端 SSH 向导；密码和密钥口令由原生 OpenSSH 接收。
- 复用 SSH 别名及使用者自己的私人档案，支持已有输入和提交脚本。
- 优先使用服务器已有 VASPKIT；审阅具体文件和资源预算后才提交。
- 区分程序结束与科学收敛，支持计算状态记录和后处理。

本机需要 Python 3 和 OpenSSH 客户端。计算端需要已配置的 Linux 环境、合法可用的 VASP/势文件及站点要求的软件。技能不会替用户取得软件许可或绕过服务器权限。首次实机使用仍需验证连接、目录权限和代表性作业。

## 安装

下载仓库并解压，将包含 `SKILL.md` 的整个目录命名为 `vaspflow`，放到以下任一位置：

- 仅当前项目：`<项目目录>/.agents/skills/vaspflow/`
- 当前用户：`~/.agents/skills/vaspflow/`

确保入口路径是 `vaspflow/SKILL.md`，不要多套一层同名目录。已有同名技能时先备份并比较，避免覆盖私人修改或重复安装。Codex 未显示时重启。目录位置见 [官方技能文档](https://learn.chatgpt.com/docs/build-skills)。

在对话中调用：

```text
使用 $vaspflow 帮我配置 SSH，并准备一套 VASP 计算输入，先展示文件供我审阅。
```

服务器地址、用户名和认证信息在使用者本机的独立终端输入，不粘贴到公开 Issue、PR 或聊天中。详细流程见 [SSH 设置](references/setup.md) 和 [计算工作流](references/workflow.md)。

## 私人信息存放位置

真实 SSH 配置保存在使用者自己的 OpenSSH 目录；授权后的私人档案放在公开仓库之外。示例 JSON 的连接字段保持 `null`，授权默认关闭。不要把实际配置填回 `assets/*.example.json`，也不要在技能目录内运行真实计算。

`.gitignore` 采用逐文件白名单；新增公开文件时需明确更新白名单。白名单不能阻止在已允许文件中写入秘密，网页上传也不能依赖它筛选文件。发布前必须检查文件内容和 Git 待提交内容。

## 离线验证

在仓库根目录运行，任一命令失败都应停止发布：

```sh
python -B TEST/test_probe.py
python -B TEST/test_onboard.py
python -B TEST/test_distribution.py
```

测试使用合成配置、模拟调用及临时目录，不连接真实服务器。Shell 集成测试需要 Bash 和对应 POSIX 工具；缺少时会显示跳过，不能当成已完成实机验收。`test_distribution.py` 检查文件白名单、空白模板、常见敏感信息模式及换行，不保证识别所有秘密，也不清理 Git 历史。

发布方法见 [GitHub 发布教程](PUBLISH.zh-CN.md)。设计参考见 [sources.md](references/sources.md)。
