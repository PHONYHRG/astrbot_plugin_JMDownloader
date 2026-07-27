# -*- coding: utf-8 -*-
import re
import asyncio
import shutil
from pathlib import Path
from astrbot.api.star import Context, Star, register
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.message_components import Plain, File
from astrbot.api import logger
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

@register(
    "astrbot_plugin_JMDownloader",
    "Phony",
    "通过 JM ID 下载禁漫本子并导出为 PDF 发送到群聊，支持多章节和查询",
    "0.0.3"
)
class JmDownloaderPlugin(Star):
    def __init__(self, context: Context, config: dict = None):
        super().__init__(context)
        self.config = config or {}
        storage_path = self.config.get("storage_path", "")
        if not storage_path:
            storage_path = Path(get_astrbot_data_path()) / "plugin_data" / "jm_downloader" / "downloads"
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.auto_delete = self.config.get("auto_delete", False)
        self.delete_pdf = self.config.get("delete_pdf_after_send", True)
        self._downloader = None

    def _get_downloader(self):
        if self._downloader is None:
            try:
                from .jm_downloader import JmDownloader
                self._downloader = JmDownloader(self.storage_path, self.config.get("option_file", ""))
            except ImportError as e:
                logger.error(f"无法加载 JmDownloader: {e}")
                raise
        return self._downloader

    def _is_group_allowed(self, event):
        group_id = event.get_group_id()
        if not group_id:
            return False
        allowed = self.config.get("allowed_groups", [])
        if not allowed:
            return True
        return group_id in allowed

    def _parse_jm_command(self, text: str):
        """解析 jm 命令，返回 (id, chapter_param)"""
        # 匹配 jm123 或 jm123 full 或 jm123 2
        pattern = r'^(?:jm|JM|本子)\s*(\d+)(?:\s+(full|\d+))?$'
        match = re.match(pattern, text)
        if match:
            album_id = match.group(1)
            param = match.group(2)
            if param is None:
                return album_id, None
            elif param == 'full':
                return album_id, 'full'
            else:
                try:
                    return album_id, int(param)
                except ValueError:
                    return album_id, None
        return None, None

    async def _delete_with_retry(self, path: Path, max_retries: int = 5, delay: float = 0.5):
        for i in range(max_retries):
            try:
                path.unlink()
                logger.debug(f"已删除文件: {path}")
                return
            except PermissionError as e:
                if i == max_retries - 1:
                    logger.warning(f"删除文件失败（已达最大重试次数）: {e}")
                else:
                    await asyncio.sleep(delay * (i + 1))
            except Exception as e:
                logger.warning(f"删除文件失败: {e}")
                break

    async def initialize(self):
        logger.info("JM下载器插件已加载")

    # ---------- 查询命令 ----------
    @filter.regex(r"^查询jm\d+$")
    async def on_query_jm(self, event: AstrMessageEvent):
        if not self._is_group_allowed(event):
            return
        text = event.message_str.strip()
        # 提取数字
        match = re.search(r'(\d+)', text)
        if not match:
            yield event.plain_result("无法提取本子 ID。")
            return
        album_id = match.group(1)
        yield event.plain_result(f"⏳ 正在查询本子 {album_id} 的详情...")
        try:
            downloader = self._get_downloader()
            info = await asyncio.to_thread(downloader.get_album_info, album_id)
            if not info:
                yield event.plain_result(f"❌ 未找到本子 {album_id} 或获取详情失败。")
                return
            # 格式化输出
            lines = [
                f"📖 标题：{info['title']}",
                f"✍️ 作者：{info['author']}",
                f"📝 简介：{info['description'][:200]}{'...' if len(info['description']) > 200 else ''}",
                f"🏷️ 标签：{', '.join(info['tags'])}",
                f"📄 章节数：{len(info['photos'])}",
            ]
            # 添加章节列表（最多显示10个）
            photo_list = info['photos']
            if photo_list:
                lines.append("📑 章节列表：")
                for i, p in enumerate(photo_list[:10], 1):
                    lines.append(f"  {i}. {p['title']} (ID: {p['id']}, {p['page_count']}页)")
                if len(photo_list) > 10:
                    lines.append(f"  ... 共 {len(photo_list)} 章")
            yield event.plain_result("\n".join(lines))
        except Exception as e:
            logger.error(f"查询本子 {album_id} 出错: {e}")
            yield event.plain_result(f"❌ 查询出错: {e}")

    # ---------- 下载命令 ----------
    @filter.regex(r"^(?:jm|JM|本子)\s*\d+(?:\s+(?:full|\d+))?$")
    async def on_jm_command(self, event: AstrMessageEvent):
        if not self._is_group_allowed(event):
            return
        text = event.message_str.strip()
        album_id, chapter = self._parse_jm_command(text)
        if not album_id:
            yield event.plain_result("无法提取有效的 JM ID。")
            return
        # 构造提示
        if chapter is None:
            tip = "第一章"
        elif chapter == 'full':
            tip = "全部章节"
        else:
            tip = f"第 {chapter} 章"
        yield event.plain_result(f"⏳ 正在下载本子 {album_id}（{tip}），请稍候...")
        try:
            downloader = self._get_downloader()
            pdf_path, album_dir = await asyncio.to_thread(
                downloader.download_and_pdf,
                album_id,
                chapter
            )
            if pdf_path and pdf_path.exists():
                yield event.chain_result([
                    Plain(f"✅ 本子 {album_id}（{tip}）下载完成！"),
                    File(file=str(pdf_path), name=pdf_path.name)
                ])
                await asyncio.sleep(1)
                if self.delete_pdf:
                    await self._delete_with_retry(pdf_path)
                if self.auto_delete and album_dir and album_dir.exists():
                    shutil.rmtree(album_dir)
                    logger.debug(f"已删除图片文件夹: {album_dir}")
            else:
                yield event.plain_result(f"❌ 下载本子 {album_id} 失败。")
        except Exception as e:
            logger.error(f"下载本子 {album_id} 出错: {e}")
            yield event.plain_result(f"❌ 出错: {e}")

    async def terminate(self):
        logger.info("JM下载器插件已卸载")