# Changelog

## v0.0.2 (2026-07-26)

### Bug Fixes
- **修复 Windows 下 PDF 页面重复**：仅使用小写扩展名匹配图片，并增加 `set` 去重，避免大小写不敏感导致的重复。
- **修复文件删除时被占用**：增加 `_delete_with_retry` 异步重试机制，并在发送后等待 1 秒释放句柄。

### Improvements
- 新增 `delete_pdf_after_send` 配置项，支持发送后自动删除 PDF（保留图片），节省存储空间。
- 调整 `auto_delete` 默认值为 `false`（保留图片，删除 PDF 为默认行为）。

## v0.0.1 (2026-07-26)

### New Features
- 初始版本，支持下载本子并合成 PDF 发送到群聊。
- 使用 `reportlab` 合成 PDF，避免 `pikepdf` 依赖冲突。
- 支持自然语言触发和纯数字识别。
- 提供基础配置项（存储路径、自动删除、白名单）。