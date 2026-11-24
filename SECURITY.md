# 安全演示说明

## 默认行为

- 生成 PPT 只写入本地工作区 `outputs/`。
- 默认在生成完成后调用 GitHub API，按本地真实文件名强制替换公开仓库中的同名 PPT。
- 设置 `PPT_AUTO_PUBLISH=0` 或传入 `--no-publish` 可关闭发布。
- 强制替换保留 Git 提交历史，不会执行改写远端历史的 `git push --force`。

## 目标仓库

- 固定仓库：`https://github.com/wushuangtian/results`
- 当前可见性：Public
- 文件命名：`ppt-results/<本地真实文件名>`
- 文件类型：仅 `.pptx`
- 文件大小上限：50 MiB

上传到 Public 仓库后，任何人都可能下载和查看文件。演示时只应使用可公开的样例内容。

## 凭据

使用环境变量 `PPT_GITHUB_TOKEN` 提供 GitHub fine-grained PAT。令牌只应授权 `wushuangtian/results` 的 `Contents: Read and write` 权限。

- 不要把令牌写入源码、`SKILL.md`、配置文件或演示文稿。
- 不要在命令行参数、日志或截图中展示令牌。
- 演示结束后撤销临时令牌或缩短其有效期。

## 发布开关

默认开启自动发布，需要配置：

```text
PPT_GITHUB_TOKEN=<有限权限令牌>
```

关闭发布：

```text
PPT_AUTO_PUBLISH=0
```

Token 应由演示管理员在受控环境中配置，不随 Skill ZIP 分发。

## 失败处理

- 上传失败时，本地 PPT 保留。
- 进程返回非零退出码。
- 不会回退到其他仓库或匿名上传服务。
- 每次成功上传都会输出公开链接、Commit SHA、文件 SHA-256 和仓库可见性。
