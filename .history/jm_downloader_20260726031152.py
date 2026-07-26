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
        if not self.option_file and not self.default_option_file.exists():
            self._create_default_option_file()

    def _create_default_option_file(self):
        """创建默认配置文件（YAML格式），使用正确的 export 插件"""
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
                        "plugin": "export",          # 正确插件名
                        "kwargs": {
                            "type": "pdf",           # 导出类型 PDF
                            "pdf_dir": str(self.storage_path),
                            "filename_rule": "Bd_Aid",
                            "delete_original": False
                        }
                    }
                ]
            }
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
        """获取要使用的配置文件路径"""
        if self.option_file and os.path.exists(self.option_file):
            return self.option_file
        return str(self.default_option_file)

    def download_and_pdf(self, album_id: str, temp_dir: Path, auto_delete: bool = True) -> Optional[Path]:
        jmcomic = self._import_jmcomic()
        try:
            option = jmcomic.create_option_by_file(self._get_option_file())
            downloader = jmcomic.JmDownloader(option)
            downloader.download_album(album_id)
            logger.info(f"本子 {album_id} 下载完成，查找 PDF...")
            # 查找生成的 PDF
            pdf_dir = self.storage_path
            # 尝试多种可能的文件名
            patterns = [f"{album_id}.pdf", f"JM{album_id}.pdf", f"{album_id}_*.pdf"]
            for pattern in patterns:
                for f in pdf_dir.glob(pattern):
                    if f.is_file() and f.suffix == '.pdf':
                        return f
            logger.error(f"未找到 {album_id} 的 PDF 文件")
            return None
        except Exception as e:
            logger.error(f"下载失败: {e}")
            raise