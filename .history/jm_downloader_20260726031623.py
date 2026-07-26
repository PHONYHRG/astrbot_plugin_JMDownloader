# -*- coding: utf-8 -*-
import os
import subprocess
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
        # 如果未指定 option_file 且默认配置文件不存在，则生成
        if not self.option_file and not self.default_option_file.exists():
            self._create_default_option_file()

    def _create_default_option_file(self):
        """创建默认配置文件，仅下载图片，不启用导出插件"""
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
            # 不配置 plugins，只下载图片
        }
        try:
            with open(self.default_option_file, "w", encoding="utf-8") as f:
                yaml.dump(config, f, allow_unicode=True, default_flow_style=False)
            logger.info(f"已生成默认配置文件: {self.default_option_file}")
        except Exception as e:
            logger.error(f"生成默认配置文件失败: {e}")
            raise

    def _import_jmcomic(self):
        try:
            import jmcomic
            return jmcomic
        except ImportError as e:
            raise ImportError(f"请安装 jmcomic: pip install jmcomic。详情: {e}")

    def _get_option_file(self) -> str:
        if self.option_file and os.path.exists(self.option_file):
            return self.option_file
        return str(self.default_option_file)

    def _find_image_folder(self, album_id: str) -> Optional[Path]:
        """查找下载的图片文件夹"""
        # jmcomic 按照 Bd_Aid 规则，路径为 storage_path/album_id/
        possible_paths = [
            self.storage_path / album_id,
            self.storage_path / f"JM{album_id}",
        ]
        for p in possible_paths:
            if p.exists() and p.is_dir():
                # 检查是否包含图片文件
                files = list(p.glob("*.jpg")) + list(p.glob("*.png")) + list(p.glob("*.gif"))
                if files:
                    return p
        return None

    def download_and_pdf(self, album_id: str, temp_dir: Path, auto_delete: bool = True) -> Optional[Path]:
        jmcomic = self._import_jmcomic()
        try:
            # 1. 下载图片
            option = jmcomic.create_option_by_file(self._get_option_file())
            downloader = jmcomic.JmDownloader(option)
            downloader.download_album(album_id)
            logger.info(f"本子 {album_id} 下载完成")

            # 2. 查找图片文件夹
            image_folder = self._find_image_folder(album_id)
            if not image_folder:
                logger.error(f"未找到 {album_id} 的图片文件夹")
                return None

            # 3. 使用 img2pdf 命令行生成 PDF
            pdf_path = self.storage_path / f"{album_id}.pdf"
            # 获取所有图片文件（按文件名自然排序）
            image_files = sorted(
                [f for f in image_folder.glob("*") if f.suffix.lower() in ['.jpg', '.jpeg', '.png', '.gif']],
                key=lambda x: x.name
            )
            if not image_files:
                logger.error(f"图片文件夹 {image_folder} 中没有图片")
                return None

            # 构建 img2pdf 命令
            # 注意：img2pdf 命令行接受文件列表，输出 PDF
            cmd = ["img2pdf"] + [str(f) for f in image_files] + ["-o", str(pdf_path)]
            logger.info(f"执行命令: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if result.returncode != 0:
                logger.error(f"img2pdf 失败: {result.stderr}")
                return None

            if pdf_path.exists() and pdf_path.stat().st_size > 0:
                logger.info(f"PDF 生成成功: {pdf_path}")
                # 可选：删除图片文件夹以释放空间
                if auto_delete:
                    import shutil
                    shutil.rmtree(image_folder)
                    logger.info(f"已删除图片文件夹: {image_folder}")
                return pdf_path
            else:
                logger.error("PDF 生成失败，文件不存在或为空")
                return None

        except subprocess.TimeoutExpired:
            logger.error("img2pdf 超时")
            return None
        except Exception as e:
            logger.error(f"下载或转换失败: {e}")
            raise