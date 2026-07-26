# -*- coding: utf-8 -*-
import shutil
from pathlib import Path

def cleanup_dir(path: Path):
    """删除目录及其所有内容"""
    if path.exists() and path.is_dir():
        shutil.rmtree(path)