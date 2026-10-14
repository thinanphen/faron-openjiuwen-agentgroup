# -*- coding: utf-8 -*-
"""pytest 配置：把 src/ 加入导入路径，使 `pytest` 与直接运行脚本行为一致。"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))
