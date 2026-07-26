# -*- coding: utf-8 -*-
import os
import yaml
from pathlib import Path
from typing import Optional
from astrbot.api import logger

class JmDownloader:
    def __init__(self, storage_path: Path, option_file: str = ""):
        self.storage_path = storage_path
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.option_file = option_file
        self.default_option_file = self.storage_path / "default_option.yml"
        # 强制生成或更新配置文件（如果存在且包含插件配置则覆盖）
        self._ensure_config_file()

    def _ensure_config_file(self):
        """确保配置文件存在且不含插件配置"""
        need_create = False
        if not self.default_option_file.exists():
            need_create = True
        else:
            # 检查是否包含 plugins 字段
            try:
                with open(self.default_option_file, "r", encoding="utf-8") as f:
                    content = yaml.safe_load(f)
                if content and 'plugins' in content:
                    logger.warning("旧配置文件包含插件配置，已自动删除并重新生成")
                    self.default_option_file.unlink()
                    need_create = True
            except Exception as e:
                logger.warning(f"读取配置文件失败，将重新生成: {e}")
                self.default_option_file.unlink()
                need_create = True

        if need_create:
            self._create_default_option_file()

    def _create_default_option_file(self):
        """创建不含插件配置的默认配置文件（仅下载图片）"""
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
            # 注意：不包含 plugins 字段
        }
        try:
            with open(self.default_option_file, "w", encoding="utf-8") as f:
                yaml.dump(config, f, allow_unicode=True, default_flow_style=False)
            logger.info(f"已生成干净的默认配置文件: {self.default_option_file}")
        except Exception as e:
            logger.error(f"生成默认配置文件失败: {e}")
            raise

    def _import_jmcomic(self):
        # 阻断 img2pdf 的导入，避免 pikepdf 冲突
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

    def _images_to_pdf(self, image_dir: Path, output_path: Path, album_title: str = "") -> Path:
        """将图片文件夹合并为 PDF（使用 reportlab）"""
        try:
            from PIL import Image
            from reportlab.pdfgen import canvas
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.utils import ImageReader
        except ImportError as e:
            raise ImportError(f"缺少 PDF 合成依赖，请执行: pip install reportlab Pillow。详情: {e}")

        # 收集图片
        image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}
        image_files = []
        for ext in image_extensions:
            image_files.extend(image_dir.glob(f"*{ext}"))
            image_files.extend(image_dir.glob(f"*{ext.upper()}"))
        image_files = sorted(image_files, key=lambda x: int(x.stem.split('_')[0]) if x.stem.isdigit() else 0)
        if not image_files:
            raise ValueError(f"未找到图片文件: {image_dir}")

        # 第一张图决定尺寸
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

    def download_and_pdf(self, album_id: str, temp_dir: Path, auto_delete: bool = True) -> Optional[Path]:
        jmcomic = self._import_jmcomic()
        try:
            option = jmcomic.create_option_by_file(self._get_option_file())
            downloader = jmcomic.JmDownloader(option)
            album = downloader.download_album(album_id)  # 只下载，不触发任何插件
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
                return None

            # 合成 PDF
            pdf_path = self.storage_path / f"{album_id}.pdf"
            album_title = getattr(album, 'name', album_id)
            self._images_to_pdf(album_dir, pdf_path, album_title)
            logger.info(f"PDF 合成完成: {pdf_path}")

            # 删除图片文件夹
            if auto_delete:
                import shutil
                shutil.rmtree(album_dir)
                logger.debug(f"已删除临时文件夹: {album_dir}")

            return pdf_path
        except Exception as e:
            logger.error(f"下载或合成 PDF 失败: {e}")
            raise