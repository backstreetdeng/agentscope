"""BCI-006 车系标准名与动力形式的统一规则。

两件事，供映射库生成脚本与分析服务共用：

1. `strip_power_suffix`：车系标准名一律去动力/能源后缀，只留简称
   （海狮05 EV → 海狮05、宋PLUS新能源 → 宋PLUS、领克08 EM-P → 领克08），
   保留车系本名里的非动力词（PLUS、型号字母）。拉丁后缀必须有空格分隔才剥离，
   避免把「宏光MINIEV」这类本名误删。
2. `normalize_power_form`：把接口入参、问卷取值统一到五个中文动力类别
   （纯电 / 插混 / 增程 / 纯燃油 / 油电混动）；认不出才算 `未标注`。
   动力形式不从车名推断，一律按问卷题项取值。
"""

from __future__ import annotations

import re
import unicodedata

POWER_FORMS: tuple[str, ...] = ("纯电", "插混", "增程", "纯燃油", "油电混动")
UNLABELED = "未标注"

# 问卷原始写法 → 五个中文类别（购买侧 Q2_2、对比侧 Q3_22_2_1/2/3 共用）。
# 先精确匹配再按前缀匹配（允许「纯电（BEV）」这类带注写法），前缀按长键优先，
# 避免「增程式」被「增程」截断。裸「混动」不认，因为分不清插混与油电混动。
POWER_FORM_ALIASES: dict[str, str] = {
    "纯电": "纯电",
    "纯电动": "纯电",
    "ev": "纯电",
    "bev": "纯电",
    "插混": "插混",
    "插电混动": "插混",
    "插电式混合动力": "插混",
    "插电式混动": "插混",
    "phev": "插混",
    "dm-i": "插混",
    "dmi": "插混",
    "增程": "增程",
    "增程式": "增程",
    "增程式电动": "增程",
    "erev": "增程",
    "纯燃油": "纯燃油",
    "燃油": "纯燃油",
    "燃油车": "纯燃油",
    "汽油": "纯燃油",
    "油电混动": "油电混动",
    "油电混合": "油电混动",
    "hev": "油电混动",
}

_LATIN_SUFFIX = r"(?:EV|DM-i|DMi|DM|PHEV|BEV|EREV|EM-P|EM|Hi4-T|Hi4|Hi4-Z)"
_CN_SUFFIX = (
    r"(?:新能源版|新能源|插电式混合动力|插电式混动|插电混动|插混|纯电动|纯电|增程版|增程)"
)
_SUFFIX_RE = re.compile(
    rf"(?:(?:(?<=\s)|(?<=[0-9\u4e00-\u9fff])){_LATIN_SUFFIX}|{_CN_SUFFIX})$", re.IGNORECASE
)

# 购买侧 Q2_2「您接受调研的燃料类型是？」只有三个取值，按前缀做 SQL 过滤。
# 纯燃油 / 油电混动 在购买侧没有对应取值，传这两类时定量样本为 0（不是接口错误）。
SURVEY_POWER_FORM = {"纯电": "纯电动", "插混": "插电混动", "增程": "增程式"}


def norm_key(value: str) -> str:
    """归一键：全角转半角、去大小写、去标点空白。"""
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]", "", text)


def strip_power_suffix(name: str) -> str:
    """去掉车系名末尾的动力/能源后缀，可连续剥离（如「XX EV 新能源」）。"""
    text = re.sub(r"\s+", " ", str(name or "")).strip()
    for _ in range(3):
        stripped = _SUFFIX_RE.sub("", text).strip()
        if not stripped or stripped == text:
            break
        text = stripped
    return text


def normalize_power_form(value: str | None) -> str | None:
    """把接口入参或问卷取值归一到五个中文动力类别；空值或认不出返回 None。

    认不出的值由调用方记 `未标注`，不做猜测。
    """
    text = unicodedata.normalize("NFKC", str(value or "")).strip().casefold()
    if not text:
        return None
    exact = POWER_FORM_ALIASES.get(text)
    if exact:
        return exact
    for alias in sorted(POWER_FORM_ALIASES, key=len, reverse=True):
        if text.startswith(alias):
            return POWER_FORM_ALIASES[alias]
    return None

