# -*- coding: utf-8 -*-
import os
import re
import yaml
import shutil
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
            # 使用 JmApi 直接获取专辑信息
            api = jmcomic.JmApi(option)
            album = api.get_album(album_id)
            if not album:
                return None
            info = {
                "id": album.id,
                "title": album.name,
                "author": album.author,
                "description": album.description or "无简介",
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
            return info
        except Exception as e:
            logger.error(f"获取专辑信息失败: {e}")
            return None

    def _collect_images_for_chapters(self, album_dir: Path, photo_ids: List[str]) -> List[Path]:
        """根据章节ID列表，收集所有图片文件路径，按章节和图片顺序排序"""
        image_files = []
        for photo_id in photo_ids:
            found_dir = None
            for sub_dir in album_dir.iterdir():
                if sub_dir.is_dir() and photo_id in sub_dir.name:
                    found_dir = sub_dir
                    break
            if not found_dir:
                logger.warning(f"未找到章节 {photo_id} 的下载目录")
                continue
            image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}
            files = []
            for ext in image_extensions:
                files.extend(found_dir.glob(f"*{ext}"))
                files.extend(found_dir.glob(f"*{ext.upper()}"))
            files = list(set(files))
            def extract_number(filepath: Path) -> int:
                match = re.search(r'(\d+)', filepath.stem)
                return int(match.group(1)) if match else 0
            files.sort(key=extract_number)
            image_files.extend(files)
        return image_files

    def _images_to_pdf(self, image_files: List[Path], output_path: Path) -> Path:
        try:
            from PIL import Image
            from reportlab.pdfgen import canvas
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.utils import ImageReader
        except ImportError as e:
            raise ImportError(f"缺少 PDF 合成依赖，请执行: pip install reportlab Pillow。详情: {e}")
        if not image_files:
            raise ValueError("没有图片可合成")
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
        jmcomic = self._import_jmcomic()
        try:
            option = jmcomic.create_option_by_file(self._get_option_file())
            downloader = jmcomic.JmDownloader(option)
            album = downloader.download_album(album_id)
            logger.info(f"本子 {album_id} 下载完成，开始合成 PDF...")

            album_dir = self.storage_path / album_id
            if not album_dir.exists():
                for d in self.storage_path.glob(f"*{album_id}*"):
                    if d.is_dir():
                        album_dir = d
                        break
            if not album_dir.exists():
                logger.error(f"未找到本子 {album_id} 的下载目录")
                return None, None

            photo_list = album.photos
            if chapter is None:
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

            photo_ids = [p.id for p in selected_photos]
            image_files = self._collect_images_for_chapters(album_dir, photo_ids)
            if not image_files:
                logger.error("未找到任何图片文件")
                return None, None

            pdf_path = self.storage_path / f"{album_id}.pdf"
            self._images_to_pdf(image_files, pdf_path)
            logger.info(f"PDF 合成完成: {pdf_path}")

            return pdf_path, album_dir
        except Exception as e:
            logger.error(f"下载或合成 PDF 失败: {e}")
            raise