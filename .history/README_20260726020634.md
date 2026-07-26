# 合并转发查重提醒插件 (DuplicateForwardReminder)

一个用于 [AstrBot](https://github.com/Soulter/AstrBot) 的插件，自动检测群聊中**重复发送的合并转发消息**，并对重复发送的用户发出 `@` 提醒，附带自定义警告图片。

## 📌 功能特性

- **自动检测**：监听所有群消息，自动识别合并转发消息（即 QQ 的“聊天记录”合并转发）。
- **生成指纹**：根据合并转发中的每条子消息的发送者 ID、时间戳和内容生成唯一的 MD5 哈希指纹。
- **全局查重**：每个群独立记录已经出现过的指纹，当同一指纹再次出现时判定为重复。
- **智能提醒**：检测到重复后，自动 `@` 原发送者，发送预设的文本警告 + 自定义图片。
- **数据持久化**：使用 `context.persist` 存储指纹数据，AstrBot 重启后不会丢失。

## 🚀 安装方法

1. **下载插件文件**  
   将插件代码保存为 `duplicate_forward_reminder.py`。

2. **放入 addons 目录**  
   将 `duplicate_forward_reminder.py` 复制到 AstrBot 根目录下的 `addons` 文件夹中。

3. **准备警告图片**  
   准备一张警告图片（例如 PNG 或 JPG 格式），将其放在 AstrBot 可访问的位置（例如 `data/warning.png`）。  
   > 注意：图片路径需要在插件代码中配置（见下一节）。

4. **重启 AstrBot**  
   重启 AstrBot 或通过 Web 管理面板重新加载插件。插件会自动加载并开始工作。

## ⚙️ 配置说明

打开 `duplicate_forward_reminder.py` 文件，找到 `__init__` 方法中的以下行：

```python
self.warning_image_path = "data/warning.png"