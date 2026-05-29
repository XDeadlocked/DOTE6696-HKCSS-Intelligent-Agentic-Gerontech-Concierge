from __future__ import annotations

import re
from dataclasses import dataclass

from app.schemas.intent import IntentType


@dataclass(slots=True)
class IntentDecision:
    intent: IntentType
    confidence: float
    scores: dict[str, float]


class HeuristicIntentClassifier:
    PRODUCT_KEYWORDS = [
        "轮椅",
        "拐杖",
        "护理床",
        "助行器",
        "手表",
        "定位器",
        "移位机",
        "沐浴椅",
        "坐垫",
        "扶手",
        "餐具",
        "陪伴机器人",
        "眼镜",
        "床",
        "器材",
        "设备",
        "工具",
    ]
    BROWSE_PATTERNS = [
        r"你们有",
        r"有冇",
        r"有没有",
        r"我想看",
        r"我想睇",
        r"我想了解",
        r"了解下",
        r"看看",
        r"睇下",
        r"规格",
        r"型号",
        r"比较",
        r"贵不贵",
        r"会唔会好贵",
        r"多少钱",
        r"价格",
        r"有用吗",
        r"会讲广东话吗",
    ]
    NURSING_PATTERNS = [
        r"如何",
        r"怎么",
        r"怎样",
        r"點樣",
        r"点样",
        r"怎么办",
        r"點算",
        r"点算",
        r"预防",
        r"幫老人",
        r"帮老人",
        r"保养",
        r"清洁",
        r"护理",
        r"训练",
        r"沟通",
        r"固定",
        r"调节",
        r"调角度",
        r"尺寸",
        r"怎么选",
        r"如何选择",
        r"如何评估",
        r"上飞机",
        r"几大空间",
        r"换尿片",
        r"穿衣服",
        r"冲凉",
    ]
    PROBLEM_PATTERNS = [
        r"推荐",
        r"有咩设备",
        r"有什么设备",
        r"边款",
        r"边种",
        r"边只",
        r"起身困难",
        r"走路不稳",
        r"怕.*摔",
        r"经常跌",
        r"常跌",
        r"跌倒",
        r"手震",
        r"吞咽困难",
        r"吞嚥困難",
        r"搬抱",
        r"好攰",
        r"抱.*吃力",
        r"腰好痛",
        r"提醒食药",
        r"提醒食藥",
        r"忘记关火",
        r"走失",
        r"床边扶手",
        r"马桶增高器",
        r"如厕辅助",
        r"如廁輔助",
        r"脚肿",
        r"腳腫",
        r"孤独",
        r"孤獨",
        r"好闷",
        r"好悶",
        r"成日话痛",
        r"成日咳",
        r"食嘢成日咳",
        r"食嘢好慢",
    ]
    UNCLEAR_PATTERNS = [
        r"^床$",
        r"^嗯+$",
        r"^你好$",
        r"^请问$",
        r"^唔该$",
        r"^唔該$",
    ]

    def classify(self, user_input: str) -> IntentDecision:
        text = user_input.strip()
        normalized = text.lower()

        if not text or any(re.search(pattern, text) for pattern in self.UNCLEAR_PATTERNS):
            return IntentDecision(IntentType.unclear, 0.5, {"unclear": 1.0})

        browse_score = 0.0
        nursing_score = 0.0
        problem_score = 0.0

        if len(text) <= 3:
            return IntentDecision(IntentType.unclear, 0.55, {"unclear": 1.0})

        for pattern in self.BROWSE_PATTERNS:
            if re.search(pattern, text, flags=re.IGNORECASE):
                browse_score += 2.0
        for pattern in self.NURSING_PATTERNS:
            if re.search(pattern, text, flags=re.IGNORECASE):
                nursing_score += 1.6
        for pattern in self.PROBLEM_PATTERNS:
            if re.search(pattern, text, flags=re.IGNORECASE):
                problem_score += 2.0

        if any(keyword in text for keyword in self.PRODUCT_KEYWORDS):
            browse_score += 0.8

        if re.search(r"我想(买|睇|看|了解|租借)", text):
            browse_score += 2.2
        if re.search(r"(怕|经常|成日|长期|需要|唔稳|不稳|困难|困難)", text):
            problem_score += 1.4
        if re.search(r"(跌|摔|攰|搬抱|抱老人)", text):
            problem_score += 1.8
        if re.search(r"(如何|怎么|怎样|點樣|点样).*(使用|保养|清洁|选择|評估|评估|固定|调|護理|护理)", text):
            nursing_score += 2.5
        if re.search(r"(怎么|如何|怎样|點樣|点样|怎么办|點算|点算)", text) and not re.search(r"(有冇|有没有|有什么|有咩)", text):
            nursing_score += 0.9
        if re.search(r"(怕.*跌倒|走失|起身困难|手震|腳腫|脚肿|孤独|孤獨|腰好痛|抱動|抱动)", text):
            problem_score += 1.6
        if re.search(r"(規格|规格|型号|比較|比较|價格|价格|介紹|介绍)", text):
            browse_score += 1.8
        if re.search(r"(认知训练游戏|認知訓練遊戲|训练游戏|訓練遊戲)", text):
            browse_score += 2.4

        if re.search(r"(有什么|有咩|有冇|有没有).*(器材|设备|工具|產品|产品)", text):
            problem_score += 1.4
        if re.search(r"(有什么|有咩|有冇|有没有).*(轮椅|床|拐杖|手表|手錶|机器人|機械人|餐具)", text):
            browse_score += 1.8

        scores = {
            IntentType.nursing.value: nursing_score,
            IntentType.problem_solving.value: problem_score,
            IntentType.browsing.value: browse_score,
        }
        best_intent_label = max(scores, key=scores.get)
        best_score = scores[best_intent_label]

        if best_score < 1.3:
            return IntentDecision(IntentType.unclear, 0.45, scores)

        if best_intent_label == IntentType.nursing.value:
            intent = IntentType.nursing
        elif best_intent_label == IntentType.problem_solving.value:
            intent = IntentType.problem_solving
        else:
            intent = IntentType.browsing

        total = max(sum(scores.values()), 1.0)
        confidence = round(best_score / total, 4)
        return IntentDecision(intent, confidence, scores)
