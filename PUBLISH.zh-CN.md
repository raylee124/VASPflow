# 将 VASPFlow 发布到 GitHub

只上传本发布目录的内容。不要上传上一级工作区，也不要复用含有私人文件提交记录的旧仓库。公开仓库会显示 GitHub 账号身份；文件脱敏并不等于 GitHub 账号匿名。

## 1. 先保护提交身份

在 GitHub 的 Settings → Emails 中启用 **Keep my email addresses private**，并考虑启用 **Block command line pushes that expose my email**。如果使用命令行提交，从该页面复制 GitHub 提供的完整 `noreply` 邮箱，不填私人邮箱。还应检查个人主页的公开姓名、简介和联系方式。

网页操作在启用邮箱隐私后使用隐藏邮箱；命令行 Git 需要单独设置提交邮箱，已有提交的邮箱不会自动变化。参见 [GitHub 提交邮箱说明](https://docs.github.com/en/account-and-profile/how-tos/email-preferences/setting-your-commit-email-address)。

## 2. 创建新仓库

打开 [创建仓库页面](https://github.com/new)，命名为 `vaspflow`。可先选 Private，检查完再公开；准备好直接发布时选 Public。不要自动生成 README、`.gitignore` 或许可证，本发布目录已有前两项。点击 Create repository。参见 [官方创建步骤](https://docs.github.com/en/repositories/creating-and-managing-repositories/creating-a-new-repository)。

本包没有代替作者选择许可证。公开可见不等于授予任意使用和再分发的许可；如果要明确开放复用，请另行选择适合的许可证，并将 `LICENSE` 加入白名单。它不改变 VASP 和势文件各自的许可。

## 3. 网页上传：最少步骤

1. 解压发布压缩包，进入其中的 `vaspflow` 目录；应能直接看到 `SKILL.md` 和 `README.md`。
2. 在新仓库点击 **uploading an existing file**，或 **Add file → Upload files**。
3. 将该目录内的文件与子目录拖入，保持目录结构。不要上传外层 `vaspflow` 文件夹造成额外嵌套，也不要只上传 ZIP。
4. 确认 `.gitignore` 和 `.gitattributes` 也在待上传列表；系统隐藏点文件时打开显示隐藏文件。
5. 检查完整上传清单及内容，填写提交说明，例如 `Publish VASPFlow skill`，确认提交邮箱使用隐私设置后点击 **Commit changes**。
6. 确认仓库根目录有 `SKILL.md`、`README.md`、`agents/`、`assets/`、`references/`、`scripts/` 和 `TEST/`。若先建为 Private，最终检查后再按仓库设置的可见性流程改成 Public。

网页上传不会替你执行本地 `.gitignore` 白名单；只能拖入已经检查过的发布副本。GitHub 的秘密检测也不能识别所有服务器地址和私人信息。参见 [官方上传说明](https://docs.github.com/en/repositories/working-with-files/managing-files/adding-a-file-to-a-repository)。

## 4. 命令行上传：与网页方法二选一

下面用于一个全新的空 GitHub 仓库。先在发布目录中打开 PowerShell，填写参数区；不要在原始计算工作区运行。若网页已经提交文件，不要照此重新初始化或强制推送，改用网页继续更新。

```powershell
# 用户参数区：这里只填写希望公开的 GitHub 身份及仓库地址。
$PublicName = 'YOUR_PUBLIC_DISPLAY_NAME'
$NoReplyEmail = 'YOUR_GITHUB_NOREPLY_EMAIL'
$RepositoryUrl = 'https://github.com/YOUR_GITHUB_USERNAME/vaspflow.git'

# 确认当前目录就是发布副本，且没有旧 Git 历史。
if (!(Test-Path -LiteralPath 'SKILL.md')) { throw '请先进入发布目录' }
if (Test-Path -LiteralPath '.git') { throw '存在 Git 元数据，请检查历史后再操作' }

python -B TEST/test_probe.py
if ($LASTEXITCODE -ne 0) { throw 'probe 检查失败' }
python -B TEST/test_onboard.py
if ($LASTEXITCODE -ne 0) { throw 'onboard 检查失败' }
python -B TEST/test_distribution.py
if ($LASTEXITCODE -ne 0) { throw '发布检查失败' }

git init -b main
git config --local user.name "$PublicName"
git config --local user.email "$NoReplyEmail"
git add -- .
git diff --cached --name-only
git diff --cached
```

在本机查看上面显示的暂存文件和内容；不要把检查输出上传到公开 Issue。确认只有准备公开的技能文件后，再执行：

```powershell
git commit -m "Publish VASPFlow skill"
git log -1 --format=fuller
```

检查最后一条输出中的 Author、Commit 姓名和邮箱确实是愿意公开的身份，再执行：

```powershell
git remote add origin "$RepositoryUrl"
git push -u origin main
```

按 GitHub 的正常认证流程登录；不要把令牌写入仓库 URL、脚本或 README，不要用 `git add -f` 绕过白名单。任一步报错时先解决，不继续推送。

## 5. 以后更新

只编辑公开副本中的技能文件，私人服务器设置继续放在仓库之外。依次运行三个离线检查，检查 `git diff` 与暂存内容，再提交更新。新增公开文件时，在 `.gitignore` 追加 `!/相对路径`；先检查新文件再放行。

如果某项秘密已经被推送，仅删除文件或补 `.gitignore` 不能清除旧提交；需要另行处理 Git 历史，并按泄露内容撤销或更换相关凭据。
