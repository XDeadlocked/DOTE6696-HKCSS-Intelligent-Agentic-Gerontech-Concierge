from __future__ import annotations

import re
from dataclasses import dataclass

from app.intent_router.prompts import BLOCKED_RESPONSE


@dataclass(slots=True)
class GuardrailResult:
    blocked: bool
    message: str | None = None
    reason: str | None = None


class GuardrailService:
    MEDICAL_PATTERNS = [
        r"什么病",
        r"是不是",
        r"严不严重",
        r"能活多久",
        r"会不会遗传",
        r"治疗",
        r"吃什么药",
        r"开什么药",
        r"用什么药",
        r"停用.*药",
        r"停药",
        r"降压药",
        r"安眠药",
        r"止咳药",
        r"泻药",
        r"药膏",
        r"偏方",
        r"针灸",
        r"針灸",
        r"中成药",
        r"化验单",
        r"血压\d",
        r"病因",
        r"诊断",
        r"寿命",
        r"驼背",
    ]
    HARMFUL_PATTERNS = [
        r"自杀",
        r"不想活",
        r"活着没意思",
        r"弄死",
        r"捅人",
        r"电击器",
        r"绑在床上",
        r"下安眠药",
        r"骗老人钱",
        r"怎么打人",
        r"虐待动物",
        r"安乐死",
        r"让老人早点去世",
        r"伪造病历",
        r"偷东西",
        r"报复别人",
        r"垃圾",
        r"骗人的",
        r"拖累全家",
        r"不死",
        r"浪费资源",
        r"铁丝",
        r"胶带固定",
        r"自制",
        r"变傻的药",
        r"老鼠药",
        r"不被人发现",
        r"不吵不闹",
        r"骂人",
    ]
    OFF_TOPIC_PATTERNS = [
        r"股市",
        r"股票",
        r"茶餐厅",
        r"去哪里玩",
        r"天气",
        r"比特币",
        r"基金",
        r"银行理财",
        r"翻译",
        r"Python程序",
        r"电影",
        r"游戏",
        r"世界杯",
        r"曼联",
        r"星座",
        r"八字",
        r"塔罗",
        r"风水",
        r"鬼",
        r"八卦",
        r"明星",
        r"减肥",
        r"穿什么衣服",
        r"1\+1",
        r"吉凶",
        r"打牌运气",
        r"发财",
        r"改运",
        r"辟邪",
        r"旺老人",
        r"过寿",
        r"梦见",
        r"咒语",
        r"男朋友",
        r"喜欢什么颜色",
        r"你吃了吗",
        r"你会生气吗",
        r"无聊吗",
        r"人死了会去哪里",
        r"你叫什么名字",
        r"你几岁",
        r"讲个笑话",
        r"唱首歌",
        r"陪我聊天",
        r"你是机器人",
        r"夸我",
        r"骂我",
    ]

    def check(self, user_input: str) -> GuardrailResult:
        text = user_input.strip()
        if not text:
            return GuardrailResult(False)
        if any(keyword in text for keyword in ["认知训练游戏", "認知訓練遊戲", "训练游戏", "訓練遊戲"]):
            return GuardrailResult(False)

        for pattern in self.MEDICAL_PATTERNS:
            if re.search(pattern, text, flags=re.IGNORECASE):
                return GuardrailResult(True, BLOCKED_RESPONSE, "medical")
        for pattern in self.HARMFUL_PATTERNS:
            if re.search(pattern, text, flags=re.IGNORECASE):
                return GuardrailResult(True, BLOCKED_RESPONSE, "harmful")
        for pattern in self.OFF_TOPIC_PATTERNS:
            if re.search(pattern, text, flags=re.IGNORECASE):
                return GuardrailResult(True, BLOCKED_RESPONSE, "off_topic")
        return GuardrailResult(False)
