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
    "通过 JM ID 下载禁漫本子，支持 PDF/ZIP 传输方式和多章节",
    "0.0.4"
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
        self.delete_output = self.config.get("delete_output_after_send", True)
        self.clear_on_startup = self.config.get("clear_on_startup", False)
        self._downloader = None

    def _get_downloader(self):
        if self._downloader is None:
            try:
                from .jm_downloader import JmDownloader
                self._downloader = JmDownloader(
                    self.storage_path,
                    self.config.get("option_file", ""),
                    self.config
                )
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

    async def _delete_with_retry(self, path: Path, max_retries: int = 5, delay: float = 0.5):
        for i in range(max_retries):
            try:
                if path.exists():
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

    async def _clean_temp_dirs(self):
        if not self.clear_on_startup:
            return
        logger.info("执行启动清理，释放空间...")
        try:
            temp_info = self.storage_path / "temp_info"
            if temp_info.exists():
                shutil.rmtree(temp_info, ignore_errors=True)
                logger.debug(f"已删除临时目录: {temp_info}")
            for item in self.storage_path.iterdir():
                if item.is_dir() and item.name.isdigit():
                    shutil.rmtree(item, ignore_errors=True)
                    logger.debug(f"已删除残留目录: {item}")
        except Exception as e:
            logger.warning(f"启动清理时出错: {e}")

    async def initialize(self):
        logger.info("JM下载器插件已加载")
        await self._clean_temp_dirs()

    # ---------- 查询命令 ----------
    @filter.regex(r"^查询jm\s*(\d+)\s*$")
    async def on_query_jm(self, event: AstrMessageEvent):
        if not self._is_group_allowed(event):
            return
        match = re.match(r"^查询jm\s*(\d+)\s*$", event.message_str)
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
            lines = [
                f"📖 标题：{info['title']}",
                f"✍️ 作者：{info['author']}",
                f"📝 简介：{info['description'][:200]}{'...' if len(info['description']) > 200 else ''}",
                f"🏷️ 标签：{', '.join(info['tags'])}",
                f"📄 章节数：{len(info['photos'])}",
            ]
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
    @filter.regex(r"^(?:jm|JM|本子)\s*(\d+)(?:\s+(pdf|zip))?(?:\s+(full|\d+))?\s*$")
    async def on_jm_command(self, event: AstrMessageEvent):
        if not self._is_group_allowed(event):
            return

        match = re.match(r"^(?:jm|JM|本子)\s*(\d+)(?:\s+(pdf|zip))?(?:\s+(full|\d+))?\s*$", event.message_str)
        if not match:
            yield event.plain_result("无法解析命令格式。")
            return

        album_id = match.group(1)
        transport = match.group(2) if match.group(2) else 'pdf'
        chapter = match.group(3)

        if chapter == 'full':
            chapter = 'full'
        elif chapter is not None and chapter.isdigit():
            chapter = int(chapter)

        transport_label = "PDF" if transport == 'pdf' else "ZIP压缩包"
        if chapter is None:
            tip = "第一章"
        elif chapter == 'full':
            tip = "全部章节"
        else:
            tip = f"第 {chapter} 章"

        yield event.plain_result(f"⏳ 正在下载本子 {album_id}（{transport_label}，{tip}），请稍候...")
        try:
            downloader = self._get_downloader()
            if transport == 'zip':
                output_path, album_dir = await asyncio.to_thread(
                    downloader.download_and_zip,
                    album_id,
                    chapter
                )
            else:
                output_path, album_dir = await asyncio.to_thread(
                    downloader.download_and_pdf,
                    album_id,
                    chapter
                )

            if output_path and output_path.exists():
                # 文件大小检查
                file_size_mb = output_path.stat().st_size / (1024 * 1024)
                max_size = self.config.get("max_file_size_mb", 100)
                if file_size_mb > max_size:
                    yield event.plain_result(
                        f"⚠️ 文件大小 {file_size_mb:.1f} MB 超过限制（{max_size} MB），无法发送。\n"
                        f"建议：\n"
                        f"1. 使用 `{album_id} pdf` 尝试 PDF 格式（通常更小）\n"
                        f"2. 使用 `{album_id} zip 2` 下载单章测试\n"
                        f"3. 联系管理员调整 `max_file_size_mb` 配置"
                    )
                    if self.delete_output:
                        await self._delete_with_retry(output_path)
                    if self.auto_delete and album_dir and album_dir.exists():
                        shutil.rmtree(album_dir, ignore_errors=True)
                    return

                # 发送文件（直接传递消息链列表）
                try:
                    await event.send([
                        Plain(f"✅ 本子 {album_id}（{tip}）下载完成！"),
                        File(file=str(output_path), name=output_path.name)
                    ])
                    # 发送成功后清理
                    await asyncio.sleep(1)
                    if self.delete_output:
                        await self._delete_with_retry(output_path)
                    if self.auto_delete and album_dir and album_dir.exists():
                        for _ in range(3):
                            try:
                                shutil.rmtree(album_dir, ignore_errors=True)
                                logger.debug(f"已删除图片文件夹: {album_dir}")
                                break
                            except Exception as e:
                                logger.warning(f"删除图片文件夹失败，重试: {e}")
                                await asyncio.sleep(0.5)
                except Exception as send_error:
                    logger.error(f"发送文件失败: {send_error}")
                    yield event.plain_result(
                        f"❌ 文件发送失败，错误: {str(send_error)}\n"
                        f"文件已保存在 {output_path}，请手动发送。"
                    )
                    # 发送失败不删除文件
            else:
                yield event.plain_result(f"❌ 下载本子 {album_id} 失败。")
        except Exception as e:
            logger.error(f"下载本子 {album_id} 出错: {e}")
            yield event.plain_result(f"❌ 出错: {e}")

    async def terminate(self):
        logger.info("JM下载器插件已卸载")