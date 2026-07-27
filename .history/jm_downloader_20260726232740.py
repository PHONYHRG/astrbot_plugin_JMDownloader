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

    def _scan_chapter_dirs(self, album_dir: Path) -> List[Dict]:
        """
        扫描专辑目录，返回按数字排序的章节列表
        每个章节包含: id, title, path, page_count
        """
        chapters = []
        if not album_dir.exists():
            return chapters
        for sub_dir in album_dir.iterdir():
            if not sub_dir.is_dir():
                continue
            # 提取目录名中的数字作为章节 ID
            match = re.search(r'(\d+)', sub_dir.name)
            if not match:
                continue
            chapter_id = match.group(1)
            # 统计图片数量
            image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}
            image_count = 0
            for ext in image_extensions:
                image_count += len(list(sub_dir.glob(f"*{ext}")))
                image_count += len(list(sub_dir.glob(f"*{ext.upper()}")))
            chapters.append({
                "id": chapter_id,
                "title": sub_dir.name,  # 使用目录名作为标题
                "path": sub_dir,
                "page_count": image_count
            })
        # 按 ID 数字排序
        chapters.sort(key=lambda x: int(x["id"]) if x["id"].isdigit() else 0)
        return chapters

    def get_album_info(self, album_id: str) -> Optional[Dict]:
        """
        获取专辑详情（通过下载到临时目录，然后扫描文件系统）
        """
        jmcomic = self._import_jmcomic()
        temp_dir = self.storage_path / "temp_info"
        temp_config = self.storage_path / "temp_option.yml"
        try:
            temp_dir.mkdir(exist_ok=True)
            temp_config_dict = {
                "dir_rule": {"base_dir": str(temp_dir), "rule": "Bd_Aid"},
                "download": {"image": {"suffix": None}}
            }
            with open(temp_config, "w", encoding="utf-8") as f:
                yaml.dump(temp_config_dict, f, allow_unicode=True, default_flow_style=False)
            option = jmcomic.create_option_by_file(str(temp_config))
            downloader = jmcomic.JmDownloader(option)
            album = downloader.download_album(album_id)
            if not album:
                return None

            # 获取标题、作者等信息（从 album 对象中抽取，这些属性通常存在）
            title = getattr(album, 'name', getattr(album, 'title', '未知标题'))
            author = getattr(album, 'author', getattr(album, 'author_name', '未知作者'))
            description = getattr(album, 'description', getattr(album, 'desc', '无简介'))
            tags = getattr(album, 'tags', getattr(album, 'tag_list', []))

            # 扫描临时目录获取章节列表
            album_dir = temp_dir / album_id
            if not album_dir.exists():
                # 尝试模糊匹配
                for d in temp_dir.glob(f"*{album_id}*"):
                    if d.is_dir():
                        album_dir = d
                        break
            if not album_dir.exists():
                logger.error(f"下载后未找到专辑目录: {album_id}")
                return None

            chapters = self._scan_chapter_dirs(album_dir)

            info = {
                "id": album_id,
                "title": title,
                "author": author,
                "description": description,
                "tags": tags,
                "photos": [
                    {
                        "id": c["id"],
                        "title": c["title"],
                        "order": idx + 1,
                        "page_count": c["page_count"]
                    }
                    for idx, c in enumerate(chapters)
                ]
            }
            return info
        except Exception as e:
            logger.error(f"获取专辑信息失败: {e}")
            return None
        finally:
            if temp_config.exists():
                temp_config.unlink()
            if temp_dir.exists():
                shutil.rmtree(temp_dir)

    def _collect_images_for_chapters(self, album_dir: Path, chapter_ids: List[str]) -> List[Path]:
        """根据章节ID列表，收集所有图片文件路径，按章节和图片顺序排序"""
        # 先扫描所有章节
        all_chapters = self._scan_chapter_dirs(album_dir)
        # 构建 id 到路径的映射
        id_to_path = {c["id"]: c["path"] for c in all_chapters}
        image_files = []
        for cid in chapter_ids:
            if cid not in id_to_path:
                logger.warning(f"未找到章节 ID: {cid}")
                continue
            chap_path = id_to_path[cid]
            # 收集该章节图片
            image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}
            files = []
            for ext in image_extensions:
                files.extend(chap_path.glob(f"*{ext}"))
                files.extend(chap_path.glob(f"*{ext.upper()}"))
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

            # 扫描所有章节
            all_chapters = self._scan_chapter_dirs(album_dir)
            if not all_chapters:
                logger.error(f"本子 {album_id} 没有章节")
                return None, None

            # 确定要处理的章节
            if chapter is None:
                selected = [all_chapters[0]] if all_chapters else []
            elif isinstance(chapter, int):
                if 1 <= chapter <= len(all_chapters):
                    selected = [all_chapters[chapter - 1]]
                else:
                    logger.error(f"章节序号 {chapter} 超出范围 (1-{len(all_chapters)})")
                    return None, None
            else:  # 'full'
                selected = all_chapters

            if not selected:
                logger.error("没有可用的章节")
                return None, None

            photo_ids = [c["id"] for c in selected]
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