"""数字溯源：报告里出现的每个关键数字，记下它是哪张表、哪个口径算出来的。"""
import pandas as pd


class FactLog:
    def __init__(self):
        self.rows = []

    def add(self, name, value, source, note=""):
        self.rows.append({"数字": name, "取值": value, "来源": source, "备注": note})
        return value

    def frame(self):
        return pd.DataFrame(self.rows, columns=["数字", "取值", "来源", "备注"])
