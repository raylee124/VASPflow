# 调研与取舍

核查日期：2026-09-08。以下是设计参考，不是已安装依赖；没有执行这些仓库的安装器，也没有复制其实现。链接跟随上游，未来采用代码时需重新核实 commit、许可证和依赖。

| 项目 | 核实的相关能力 | 本技能的取舍 |
|---|---|---|
| [lql341/scnet-hpc](https://github.com/lql341/scnet-hpc) | 面向 SCNet 的 SSH 档案和 Slurm 工作流 | 借鉴档案复用概念；不导入该站点的集群配置 |
| [the-matter-lab/ssh-skill](https://github.com/the-matter-lab/ssh-skill/blob/main/SKILL.md) | 特定实验室及 Alliance 集群的 SSH、首次配置和队列操作 | 借鉴首次连接与运行分离；不沿用站点账号或 agent forwarding 设置 |
| [JCLiuGroup/AI-Computational-Chemist VASPKIT](https://github.com/JCLiuGroup/AI-Computational-Chemist/blob/main/tools/vaspkit/SKILL.md) | VASPKIT 输入辅助和结果分析 | 纳入版本/输入/输出核验；不要求安装完整技能库 |
| [同项目 VASP 技能](https://github.com/JCLiuGroup/AI-Computational-Chemist/blob/main/tools/vasp/SKILL.md) | VASP 输入、运行与验证 | 保留科学验证环节；其局部计算默认值不作为本站默认值 |

原生 OpenSSH 已覆盖连接与传输，因此不实现保存密码的 SSH 客户端或常驻 MCP 服务。Python 标准库向导串联原生建钥/公钥登记/agent/验证，另有状态探测和个人 PC 的直接运行模板；不实现通用调度平台。

2026-09-09 安全与流程复核依据：[OpenSSH 配置](https://man.openbsd.org/ssh_config)、[authorized_keys 限制](https://man.openbsd.org/sshd)、[Microsoft 密钥/agent](https://learn.microsoft.com/en-us/windows-server/administration/openssh/openssh_keymanagement)、[VASPKIT 输入任务教程](https://vaspkit.com/tutorials.html)、[Open MPI mpirun](https://docs.open-mpi.org/en/v5.0.10/man-openmpi/man1/mpirun.1.html)。接口需按服务器实际版本验证；通用设计审查不代表真实服务器验收。

实现依据：[技能格式](https://learn.chatgpt.com/docs/build-skills)、[Codex Rules](https://learn.chatgpt.com/docs/agent-configuration/rules)、[Windows 密钥管理](https://learn.microsoft.com/en-us/windows-server/administration/openssh/openssh_keymanagement)、[OpenSSH 配置](https://man.openbsd.org/ssh_config)、[VASP 输入](https://vasp.at/wiki/index.php/Input)、[Slurm sbatch](https://slurm.schedmd.com/sbatch.html)。

工具安装与配置参考 [VASPKIT 官方安装说明](https://vaspkit.com/installation.html)；许可、依赖和版本要求在实际安装前重新核实。流程中的两类输入/脚本模式、计划预览审阅和私人偏好复用属于本技能设计。

四态部分只保留周期镜像审计要求，不从通用技能推断具体材料的耦合常数或镜像数。

## 公开发布范围

只发布 `vaspflow` 技能目录。实际服务器档案、私人搭建记录、SSH 配置、密钥、known_hosts、日志和计算数据不属于技能包。模板中的连接字段为 `null`，首次使用时由使用者提供，确认后在其本机私有配置中复用。文档中的大写占位符必须替换，不能直接执行。
