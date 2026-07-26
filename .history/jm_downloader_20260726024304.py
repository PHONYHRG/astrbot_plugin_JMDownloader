# -*- coding: utf-8 -*-
import os
from pathlib import Path
from typing import Optional
from astrbot.api import logger

class JmDownloader:
    def __init__(self, storage_path: Path, option_file: str = ""):
        self.storage_path = storage_path
        self.option_file = option_file
        self._option = None

    def _import_jmcomic(self):
        try:
            import jmcomic
            return jmcomic
        except ImportError as e:
            raise ImportError(f"请安装 jmcomic: pip install jmcomic。详情: {e}")

    def _get_option(self):
        if self._option is None:
            jmcomic = self._import_jmcomic()
            if self.option_file and os.path.exists(self.option_file):
                self._option = jmcomic.create_option_by_file(self.option_file)
            else:
                self._option = self._create_default_option()
        return self._option

    def _create_default_option(self):
        jmcomic = self._import_jmcomic()
        config = {
            "dir_rule": {
                "base_dir": str(self.storage_path),
                "rule": "Bd_Aid"
            },
            "download": {
                "image": {
                    "suffix": None
                }
            },
            "plugins": {
                "after_album": [
                    {
                        "plugin": "export_pdf",
                        "kwargs": {
                            "pdf_dir": str(self.storage_path),   # 确保 PDF 生成到该目录
                            "filename_rule": "Bd_Aid",
                            "delete_original": False
                        }
                    }
                ]
            }
        }
        return jmcomic.create_option(config)

    def download_and_pdf(self, album_id: str, temp_dir: Path, auto_delete: bool = True) -> Optional[Path]:
        jmcomic = self._import_jmcomic()
        option = self._get_option()
        downloader = jmcomic.JmDownloader(option)
        try:
            downloader.download_album(album_id)
            logger.info(f"本子 {album_id} 下载完成，查找 PDF...")
            # 直接使用 storage_path 作为 PDF 目录，与配置一致
            pdf_dir = self.storage_path
            pdf_filename = f"{album_id}.pdf"
            pdf_path = pdf_dir / pdf_filename
            if pdf_path.exists():
                return pdf_path
            # 可能生成的文件名带额外后缀，尝试模糊搜索
            for f in pdf_dir.glob(f"{album_id}*.pdf"):
                return f
            logger.error(f"PDF 未找到: {pdf_path}")
            return None
        except Exception as e:
            logger.error(f"下载失败: {e}")
            raise