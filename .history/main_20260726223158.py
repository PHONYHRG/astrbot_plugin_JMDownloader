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
    "通过 JM ID 下载禁漫本子并导出为 PDF 发送到群聊",
    "0.0.2"
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

    def _extract_jm_id(self, text: str):
        patterns = [
            r'(?:jm|JM|本子)\s*(\d{3,})',
            r'(\d{3,})',
        ]
        for pat in patterns:
            match = re.search(pat, text)
            if match:
                return match.group(1)
        return None

    async def _delete_with_retry(self, path: Path, max_retries: int = 5, delay: float = 0.5):
        """带重试的文件删除，处理文件占用"""
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

    @filter.regex(r"^(?:jm|JM|本子)\s*\d+$")
    async def on_jm_command(self, event: AstrMessageEvent):
        if not self._is_group_allowed(event):
            return
        text = event.message_str.strip()
        album_id = self._extract_jm_id(text)
        if not album_id:
            yield event.plain_result("无法提取有效的 JM ID。")
            return
        yield event.plain_result(f"⏳ 正在下载本子 {album_id}，请稍候...")
        try:
            downloader = self._get_downloader()
            pdf_path, album_dir = await asyncio.to_thread(
                downloader.download_and_pdf,
                album_id
            )
            if pdf_path and pdf_path.exists():
                # 使用链式消息发送文字和文件
                yield event.chain_result([
                    Plain(f"✅ 本子 {album_id} 下载完成！"),
                    File(file=str(pdf_path), name=pdf_path.name)
                ])
                # 等待文件发送完成（给系统一点时间释放文件句柄）
                await asyncio.sleep(1)
                # 发送后清理
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

    @filter.regex(r"^\d{4,}$")
    async def on_pure_digit(self, event: AstrMessageEvent):
        if not self._is_group_allowed(event):
            return
        album_id = event.message_str.strip()
        yield event.plain_result(f"⏳ 正在下载本子 {album_id}，请稍候...")
        try:
            downloader = self._get_downloader()
            pdf_path, album_dir = await asyncio.to_thread(
                downloader.download_and_pdf,
                album_id
            )
            if pdf_path and pdf_path.exists():
                yield event.chain_result([
                    Plain(f"✅ 本子 {album_id} 下载完成！"),
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