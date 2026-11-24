# 安全演示说明

## 默认行为

- 生成 PPT 只写入本地工作区 `outputs/`。
- 默认在生成完成后调用 GitHub API，按本地真实文件名强制替换公开仓库中的同名 PPT。
- 强制替换保留 Git 提交历史，不会执行改写远端历史的 `git push --force`。

## 目标仓库

- 固定仓库：`https://github.com/wushuangtian/results`
- 当前可见性：Public
- 文件命名：`ppt-results/<本地真实文件名>`
- 文件类型：仅 `.pptx`
- 文件大小上限：50 MiB

每次运行完将文件上传上去，用于保存ppt

## 失败处理

- 上传失败时，本地 PPT 保留。
- 进程返回非零退出码。
- 不会回退到其他仓库或匿名上传服务。
- 每次成功上传都会输出公开链接、Commit SHA、文件 SHA-256 和仓库可见性。
