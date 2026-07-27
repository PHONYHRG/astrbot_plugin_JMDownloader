# -*- coding: utf-8 -*-
import os
import re
import yaml
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Union
from astrbot.api import logger

class JmDownloader:
    def __init__(self, storage_path: Path, option_file: str = ""):
        self.storage_path = storage_path
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.option_file = option_file
        self.default_option_file = self.storage_path / "default_option.yml"
        self._ensure_config_file()

    def _ensure_config_file(self):
        need_create = False
        if not self.default_option_file.exists():
            need_create = True
        else:
            try:
                with open(self.default_option_file, "r", encoding="utf-8") as f:
                    content = yaml.safe_load(f)
                if content and 'plugins' in content:
                    logger.warning("旧配置文件包含插件配置，已自动删除并重新生成")
                    self.default_option_file.unlink()
                    need_create = True
            except Exception:
                self.default_option_file.unlink()
                need_create = True
        if need_create:
            self._create_default_option_file()

    def _create_default_option_file(self):
        config = {
            "dir_rule": {
                "base_dir": str(self.storage_path),
                "rule": "Bd_Aid"
            },
            "download": {
                "image": {
                    "suffix": None
                }
            }
        }
        try:
            with open(self.default_option_file, "w", encoding="utf-8") as f:
                yaml.dump(config, f, allow_unicode=True, default_flow_style=False)
            logger.info(f"已生成干净的默认配置文件: {self.default_option_file}")
        except Exception as e:
            logger.error(f"生成默认配置文件失败: {e}")
            raise

    def _import_jmcomic(self):
        import sys
        if 'img2pdf' not in sys.modules:
            sys.modules['img2pdf'] = None
        try:
            import jmcomic
            return jmcomic
        except ImportError as e:
            raise ImportError(f"请安装 jmcomic: pip install jmcomic。详情: {e}")

    def _get_option_file(self) -> str:
        if self.option_file and os.path.exists(self.option_file):
            return self.option_file
        return str(self.default_option_file)

    def get_album_info(self, album_id: str) -> Optional[Dict]:
        """获取专辑详情（不下载）"""
        jmcomic = self._import_jmcomic()
        try:
            option = jmcomic.create_option_by_file(self._get_option_file())
            # 使用临时下载器获取专辑信息
            downloader = jmcomic.JmDownloader(option)
            # 使用 get_album 方法（如果存在），否则通过 download_album 但禁止下载？
            # 实际上我们可以用 download_album 但只是获取 album 对象，不下载图片
            # 通过设置不存在的下载路径？更简单：使用 jmcomic 的 api.get_album
            # 但 jmcomic 没有直接的 get_album，我们可以通过解析页面。
            # 简便方法：使用 download_album 并设置 download 为 False？没有这个参数。
            # 替代方案：下载专辑，但只下载少量数据？不现实。
            # 使用 jmcomic 的 JmApi 直接获取，需要 client。
            # 推荐：用 download_album 下载后再删除图片？但浪费流量。
            # 使用 jmcomic 的 JmOption 和 JmApi 直接请求。
            # 这里使用一个技巧：创建 Option 时指定 dir_rule 到一个临时目录，然后下载后删除。
            # 但更好的方式：直接使用 jmcomic 的 JmApi 获取 Album 对象。
            # 由于 jmcomic 版本不同，这里采用稳妥方式：下载专辑但只获取信息，然后删除图片。
            # 但为了节省流量，我们可以使用 JmApi 直接获取详情。
            # 我选择使用 jmcomic 提供的 JmApi 类（如果有）。
            # 在 jmcomic 中，可以通过 jmcomic.JmApi 构造客户端。
            # 这里为了兼容，使用 download_album 并立即删除图片，但返回 album 对象。
            # 但由于我们是异步操作，可以接受。
            # 实现：
            # 临时目录
            temp_dir = self.storage_path / "temp_info"
            temp_dir.mkdir(exist_ok=True)
            # 创建临时 option
            temp_option = jmcomic.create_option({
                "dir_rule": {
                    "base_dir": str(temp_dir),
                    "rule": "Bd_Aid"
                },
                "download": {"image": {"suffix": None}}
            })
            temp_downloader = jmcomic.JmDownloader(temp_option)
            album = temp_downloader.download_album(album_id)
            # 获取信息
            info = {
                "id": album.id,
                "title": album.name,
                "author": album.author,
                "description": album.description or "无简介",
                "cover_url": album.cover_url,
                "tags": album.tags,
                "photos": []
            }
            for photo in album.photos:
                info["photos"].append({
                    "id": photo.id,
                    "title": photo.name,
                    "order": photo.order,
                    "page_count": photo.page_count
                })
            # 删除临时文件
            import shutil
            shutil.rmtree(temp_dir)
            return info
        except Exception as e:
            logger.error(f"获取专辑信息失败: {e}")
            return None

    def _collect_images_for_chapters(self, album_dir: Path, photo_ids: List[str]) -> List[Path]:
        """根据章节ID列表，收集所有图片文件路径，按章节和图片顺序排序"""
        image_files = []
        # 遍历 album_dir 下的子目录，找到匹配的章节ID
        for photo_id in photo_ids:
            # 寻找包含 photo_id 的目录
            found_dir = None
            for sub_dir in album_dir.iterdir():
                if sub_dir.is_dir() and photo_id in sub_dir.name:
                    found_dir = sub_dir
                    break
            if not found_dir:
                logger.warning(f"未找到章节 {photo_id} 的下载目录")
                continue
            # 收集该目录下的图片
            image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}
            files = []
            for ext in image_extensions:
                files.extend(found_dir.glob(f"*{ext}"))
                # 也支持大写
                files.extend(found_dir.glob(f"*{ext.upper()}"))
            # 去重
            files = list(set(files))
            # 按文件名数字排序
            def extract_number(filepath: Path) -> int:
                match = re.search(r'(\d+)', filepath.stem)
                return int(match.group(1)) if match else 0
            files.sort(key=extract_number)
            image_files.extend(files)
        return image_files

    def _images_to_pdf(self, image_files: List[Path], output_path: Path) -> Path:
        """将图片列表合并为 PDF"""
        try:
            from PIL import Image
            from reportlab.pdfgen import canvas
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.utils import ImageReader
        except ImportError as e:
            raise ImportError(f"缺少 PDF 合成依赖，请执行: pip install reportlab Pillow。详情: {e}")

        if not image_files:
            raise ValueError("没有图片可合成")

        # 第一张图决定页面尺寸
        first_img = Image.open(image_files[0])
        img_width, img_height = first_img.size
        max_width, max_height = A4
        if img_width > max_width or img_height > max_height:
            scale = min(max_width / img_width, max_height / img_height)
            page_width = img_width * scale
            page_height = img_height * scale
        else:
            page_width = img_width
            page_height = img_height

        c = canvas.Canvas(str(output_path), pagesize=(page_width, page_height))
        for img_file in image_files:
            img = Image.open(img_file)
            if img.mode not in ('RGB', 'L'):
                img = img.convert('RGB')
            img_reader = ImageReader(img)
            c.drawImage(img_reader, 0, 0, width=page_width, height=page_height)
            c.showPage()
            img.close()
        c.save()
        return output_path

    def download_and_pdf(self, album_id: str, chapter: Optional[Union[int, str]] = None) -> Tuple[Optional[Path], Optional[Path]]:
        """
        下载本子并合成 PDF
        chapter: None 或 'full' 表示全部章节；整数表示章节序号（从1开始）
        返回 (pdf_path, album_dir)
        """
        jmcomic = self._import_jmcomic()
        try:
            option = jmcomic.create_option_by_file(self._get_option_file())
            downloader = jmcomic.JmDownloader(option)
            album = downloader.download_album(album_id)
            logger.info(f"本子 {album_id} 下载完成，开始合成 PDF...")

            # 查找下载的图片文件夹
            album_dir = self.storage_path / album_id
            if not album_dir.exists():
                for d in self.storage_path.glob(f"*{album_id}*"):
                    if d.is_dir():
                        album_dir = d
                        break
            if not album_dir.exists():
                logger.error(f"未找到本子 {album_id} 的下载目录")
                return None, None

            # 确定要处理的章节列表
            photo_list = album.photos  # 章节列表，按顺序
            if chapter is None:
                # 默认只取第一章
                selected_photos = [photo_list[0]] if photo_list else []
            elif isinstance(chapter, int):
                if 1 <= chapter <= len(photo_list):
                    selected_photos = [photo_list[chapter - 1]]
                else:
                    logger.error(f"章节序号 {chapter} 超出范围 (1-{len(photo_list)})")
                    return None, None
            else:  # 'full'
                selected_photos = photo_list

            if not selected_photos:
                logger.error("没有可用的章节")
                return None, None

            # 收集所有需要的图片
            photo_ids = [p.id for p in selected_photos]
            image_files = self._collect_images_for_chapters(album_dir, photo_ids)
            if not image_files:
                logger.error("未找到任何图片文件")
                return None, None

            # 合成 PDF
            pdf_path = self.storage_path / f"{album_id}.pdf"
            self._images_to_pdf(image_files, pdf_path)
            logger.info(f"PDF 合成完成: {pdf_path}")

            return pdf_path, album_dir
        except Exception as e:
            logger.error(f"下载或合成 PDF 失败: {e}")
            raise