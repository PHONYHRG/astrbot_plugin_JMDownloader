# -*- coding: utf-8 -*-
import os
import subprocess
from pathlib import Path
from typing import Optional
from astrbot.api import logger

class JmDownloader:
    def __init__(self, storage_path: Path, option_file: str = ""):
        self.storage_path = storage_path
        self.storage_path.mkdir(parents=True, exist_ok=True)
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
                        "plugin": "export",          # 使用 export 插件
                        "kwargs": {
                            "type": "pdf",           # 导出 PDF
                            "pdf_dir": str(self.storage_path),
                            "filename_rule": "Bd_Aid",
                            "delete_original": False
                        }
                    }
                ]
            }
        }
        return jmcomic.create_option(config)

    def _generate_default_option_file(self):
        """生成默认配置文件（供命令行使用）"""
        config_path = self.storage_path / "default_option.yml"
        if not config_path.exists():
            content = """
dir_rule:
  base_dir: ./
  rule: Bd_Aid
plugins:
  after_album:
    - plugin: export
      kwargs:
        type: pdf
        pdf_dir: ./
        filename_rule: Bd_Aid
        delete_original: false
"""
            config_path.write_text(content, encoding="utf-8")
            logger.info(f"已生成默认配置文件: {config_path}")
        return config_path

    def download_and_pdf(self, album_id: str, temp_dir: Path, auto_delete: bool = True) -> Optional[Path]:
        """使用 jmcomic API 下载并导出 PDF"""
        try:
            jmcomic = self._import_jmcomic()
            option = self._get_option()
            downloader = jmcomic.JmDownloader(option)
            downloader.download_album(album_id)
            logger.info(f"本子 {album_id} 下载完成，查找 PDF...")

            # 查找生成的 PDF
            pdf_dir = self.storage_path
            # 尝试多种可能的文件名格式
            possible_names = [
                f"{album_id}.pdf",
                f"JM{album_id}.pdf",
                f"{album_id}_*.pdf",
            ]
            for pattern in possible_names:
                for f in pdf_dir.glob(pattern):
                    if f.is_file() and f.suffix == '.pdf':
                        return f
            logger.error(f"未找到 {album_id} 的 PDF 文件")
            return None
        except Exception as e:
            logger.error(f"下载失败: {e}")
            raise