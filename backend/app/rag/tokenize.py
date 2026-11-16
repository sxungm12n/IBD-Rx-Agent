from __future__ import annotations

import re

_TOKEN = re.compile(r"[가-힣]+|[A-Za-z][A-Za-z0-9+\-./]*|\d+(?:\.\d+)?")


def tokenize(text: str) -> list[str]:
    """한글은 단어와 2글자 조각으로, 영문·숫자는 소문자로 나눈다.

    형태소 분석기 없이 '인플릭시맙'과 '인플릭시맵'처럼 겹치는 음절이
    맞물리게 하려고 2글자 조각을 같이 넣는다.
    """
    tokens: list[str] = []
    for match in _TOKEN.finditer(text):
        token = match.group(0)
        if "가" <= token[0] <= "힣":
            tokens.append(token)
            if len(token) >= 2:
                tokens.extend(token[index : index + 2] for index in range(len(token) - 1))
        else:
            tokens.append(token.lower())
    return tokens
