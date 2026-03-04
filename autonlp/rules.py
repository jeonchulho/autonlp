from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable


LABELS = {
    "TIME",
    "DURATION",
    "LOC",
    "RECIPIENT",
    "PURPOSE",
    "METHOD",
    "VALUE",
    "POLARITY",
    "UNKNOWN",
}


SUPPORTED_LANGS = {"ko", "en", "ja", "zh", "fr", "de", "ar"}


LANG_RULES = {
    "ko": {
        "negative": ["안 ", "못 ", "말고", "아니", "없"],
        "recipient": ["에게", "한테", "께", "앞으로"],
        "purpose": ["위해", "위해서", "하려고", "고자", "도록"],
        "method": ["통해", "사용", "써서", "가지고", "로써", "도구로", "참조", "참조해서"],
        "loc": ["에서", "으로", "로", "근처", "밖"],
        "duration": ["동안", "내내", "부터", "까지"],
        "time": ["오늘", "내일", "어제", "지금", "방금", "당일"],
        "value_units": ["원", "만원", "억원", "달러", "usd", "krw", "건", "개", "명", "%", "퍼센트", "시간", "분"],
    },
    "en": {
        "negative": ["not", "never", "no ", "without", "cannot", "can't", "don't", "doesn't", "won't"],
        "recipient": ["to ", "for "],
        "purpose": ["in order to", "so that", "for the purpose of"],
        "method": ["by ", "via ", "using ", "with ", "through "],
        "loc": ["in ", "at ", "on ", "near ", "inside ", "outside ", "from ", "into ", "onto "],
        "duration": ["for ", "during ", "from ", "until ", "till ", "throughout "],
        "time": ["today", "tomorrow", "yesterday", "now", "tonight", "this morning", "this evening"],
        "value_units": ["$", "usd", "eur", "krw", "%", "percent", "hours", "minutes", "items", "people", "kg", "km"],
    },
    "ja": {
        "negative": ["ない", "ません", "ぬ", "無理", "できない"],
        "recipient": ["に", "宛て", "向け"],
        "purpose": ["ため", "ように", "目的で"],
        "method": ["で", "によって", "を使って", "通じて"],
        "loc": ["で", "に", "へ", "から", "まで", "近く", "内", "外"],
        "duration": ["間", "まで", "から", "ずっと"],
        "time": ["今日", "明日", "昨日", "今", "今夜", "午前", "午後"],
        "value_units": ["円", "ドル", "件", "個", "人", "%", "時間", "分"],
    },
    "zh": {
        "negative": ["不", "没", "沒有", "没有", "勿", "别"],
        "recipient": ["给", "向", "对"],
        "purpose": ["为了", "以便", "为", "目的是"],
        "method": ["通过", "使用", "用", "借助", "以"],
        "loc": ["在", "到", "从", "向", "附近", "内", "外"],
        "duration": ["期间", "从", "到", "直到", "一直"],
        "time": ["今天", "明天", "昨天", "现在", "今晚", "上午", "下午"],
        "value_units": ["元", "美元", "件", "个", "人", "%", "小时", "分钟"],
    },
    "fr": {
        "negative": ["ne ", "pas", "jamais", "sans", "aucun"],
        "recipient": ["à ", "pour "],
        "purpose": ["pour ", "afin de", "dans le but de"],
        "method": ["par ", "via ", "avec ", "en utilisant"],
        "loc": ["à ", "dans ", "sur ", "près de", "hors de", "depuis "],
        "duration": ["pendant ", "de ", "jusqu'à", "tout au long"],
        "time": ["aujourd'hui", "demain", "hier", "maintenant", "ce soir", "matin"],
        "value_units": ["€", "eur", "$", "%", "heures", "minutes", "articles", "personnes"],
    },
    "de": {
        "negative": ["nicht", "kein", "keine", "niemals", "ohne"],
        "recipient": ["an ", "für "],
        "purpose": ["um zu", "damit", "zum zweck"],
        "method": ["durch ", "mit ", "via ", "mithilfe"],
        "loc": ["in ", "an ", "auf ", "bei ", "nahe ", "aus ", "nach "],
        "duration": ["während ", "von ", "bis ", "durchgehend"],
        "time": ["heute", "morgen", "gestern", "jetzt", "heute abend"],
        "value_units": ["€", "eur", "$", "%", "stunden", "minuten", "stücke", "personen"],
    },
    "ar": {
        "negative": ["لا", "ليس", "لن", "لم", "بدون"],
        "recipient": ["إلى", "لـ"],
        "purpose": ["من أجل", "لكي", "بغرض"],
        "method": ["بواسطة", "عبر", "باستخدام", "من خلال", "ب"],
        "loc": ["في", "إلى", "من", "عند", "داخل", "خارج", "قرب"],
        "duration": ["خلال", "من", "حتى", "طوال"],
        "time": ["اليوم", "غدًا", "أمس", "الآن", "هذا المساء", "صباحًا"],
        "value_units": ["دولار", "يورو", "%", "ساعة", "دقيقة", "عنصر", "شخص"],
    },
}


@dataclass(frozen=True)
class SpanCandidate:
    text: str
    start_word_id: int
    end_word_id: int
    features: dict


def _build_children(words: list) -> dict[int, list[int]]:
    children: dict[int, list[int]] = {word.id: [] for word in words}
    for word in words:
        if word.head > 0:
            children[word.head].append(word.id)
    return children


def _collect_subtree_ids(root_id: int, children: dict[int, list[int]]) -> set[int]:
    ids = set()
    stack = [root_id]
    while stack:
        node = stack.pop()
        if node in ids:
            continue
        ids.add(node)
        stack.extend(children.get(node, []))
    return ids


def _words_by_ids(words: list, ids: Iterable[int]) -> list:
    id_set = set(ids)
    return [word for word in words if word.id in id_set]


def _span_text(words: list) -> str:
    if not words:
        return ""
    return " ".join(word.text for word in words)


def _get_lang_rules(lang: str) -> dict:
    return LANG_RULES.get(lang, LANG_RULES["en"])


def detect_sentence_polarity(text: str, lang: str = "ko") -> str | None:
    lowered = text.lower()
    rules = _get_lang_rules(lang)
    if any(token.lower() in lowered for token in rules["negative"]):
        return "NEG"
    return None


def extract_recipients_from_text(text: str, lang: str = "ko") -> list[str]:
    recipients: list[str] = []
    query_like = text.strip()

    def _extend_query_style_recipients(pattern: str) -> None:
        if not ("?" in query_like or "？" in query_like or "؟" in query_like):
            return
        stripped = re.sub(r"[?？؟.!。]+$", "", query_like)
        if not re.search(r"[,，、،]", stripped):
            return
        tokens = [token.strip() for token in re.split(r"[,，、،]", stripped) if token.strip()]
        if 2 <= len(tokens) <= 10 and all(re.match(pattern, token) for token in tokens):
            recipients.extend(tokens)

    if lang == "ko":
        matches = re.finditer(r"([\w가-힣]+(?:\s*,\s*[\w가-힣]+)*)\s*(에게|한테|께)", text)
        for match in matches:
            names = [name.strip() for name in match.group(1).split(",") if name.strip()]
            recipients.extend(names)

        possessive_matches = re.finditer(
            r"([가-힣A-Za-z0-9_]{2,}(?:이사|상무|전무|부장|팀장|과장|차장|대리|매니저|대표|님)?)의\s*(?:매출|실적|내역|합계|보고서|지표|데이터|통계|현황)",
            text,
        )
        for match in possessive_matches:
            candidate = match.group(1).strip()
            if candidate:
                recipients.append(candidate)

        if not re.search(r"(에게|한테|께)", query_like):
            _extend_query_style_recipients(r"^[\w가-힣A-Za-z0-9_]+$")
    elif lang == "en":
        matches = re.finditer(r"(?:to|for)\s+([A-Za-z0-9_]+(?:\s*,\s*[A-Za-z0-9_]+)*)", text, re.IGNORECASE)
        for match in matches:
            names = [name.strip() for name in match.group(1).split(",") if name.strip()]
            recipients.extend(names)
        if not re.search(r"\b(to|for)\b", query_like.lower()):
            _extend_query_style_recipients(r"^[A-Za-z0-9_\-']+$")
    elif lang == "ja":
        matches = re.finditer(r"([\wぁ-んァ-ン一-龥ー]+(?:\s*[、,]\s*[\wぁ-んァ-ン一-龥ー]+)*)\s*(に|宛て|向け)", text)
        for match in matches:
            names = [name.strip() for name in re.split(r"[、,]", match.group(1)) if name.strip()]
            recipients.extend(names)
        _extend_query_style_recipients(r"^[\wぁ-んァ-ン一-龥ーA-Za-z0-9_]+$")
    elif lang == "zh":
        matches = re.finditer(r"(?:给|向|对)\s*([A-Za-z0-9_一-龥㐀-䶿]{1,20}(?:\s*[，,、]\s*[A-Za-z0-9_一-龥㐀-䶿]{1,20})*)", text)
        for match in matches:
            names = [name.strip() for name in re.split(r"[，,、]", match.group(1)) if name.strip()]
            cleaned_names = []
            for name in names:
                name = re.split(r"发送|發送|消息|訊息|给|給|的|邮件|郵件|通知", name, maxsplit=1)[0].strip()
                if re.match(r"^[A-Za-z0-9_]+$", name):
                    cleaned_names.append(name)
                    continue
                cjk_match = re.match(r"^([一-龥㐀-䶿]{1,6})", name)
                if cjk_match:
                    cleaned_names.append(cjk_match.group(1))
            names = cleaned_names
            recipients.extend(names)
        _extend_query_style_recipients(r"^[\w一-龥㐀-䶿A-Za-z0-9_]+$")
    elif lang == "fr":
        matches = re.finditer(r"(?:à|pour)\s+([A-Za-zÀ-ÖØ-öø-ÿ0-9_\-']+(?:\s*,\s*[A-Za-zÀ-ÖØ-öø-ÿ0-9_\-']+)*)", text, re.IGNORECASE)
        for match in matches:
            names = [name.strip() for name in match.group(1).split(",") if name.strip()]
            recipients.extend(names)
        _extend_query_style_recipients(r"^[A-Za-zÀ-ÖØ-öø-ÿ0-9_\-']+$")
    elif lang == "de":
        matches = re.finditer(r"(?:an|für)\s+([A-Za-zÄÖÜäöüß0-9_\-']+(?:\s*,\s*[A-Za-zÄÖÜäöüß0-9_\-']+)*)", text, re.IGNORECASE)
        for match in matches:
            names = [name.strip() for name in match.group(1).split(",") if name.strip()]
            recipients.extend(names)
        _extend_query_style_recipients(r"^[A-Za-zÄÖÜäöüß0-9_\-']+$")
    elif lang == "ar":
        matches = re.finditer(r"(?:إلى|لـ)\s*([\w\u0600-\u06FF]{1,20}(?:\s*[،,]\s*[\w\u0600-\u06FF]{1,20})*)", text)
        for match in matches:
            names = [name.strip() for name in re.split(r"[،,]", match.group(1)) if name.strip()]
            names = [name for name in names if re.match(r"^[\w\u0600-\u06FF]{1,20}$", name)]
            recipients.extend(names)
        _extend_query_style_recipients(r"^[\w\u0600-\u06FFA-Za-z0-9_]+$")

    deduped = []
    seen = set()
    for recipient in recipients:
        if recipient in seen:
            continue
        seen.add(recipient)
        deduped.append(recipient)
    return deduped


def collect_condition_candidates(sentence) -> list[SpanCandidate]:
    words = sentence.words
    children = _build_children(words)
    heads = [
        word
        for word in words
        if word.deprel in {"obl", "advcl", "nmod", "advmod", "iobj", "ccomp"}
    ]

    raw_candidates: list[SpanCandidate] = []
    for head in heads:
        ids = _collect_subtree_ids(head.id, children)
        span_words = _words_by_ids(words, ids)
        span_words = sorted(span_words, key=lambda word: word.id)
        if len(span_words) > 6:
            continue
        text = _span_text(span_words).strip()
        if not text:
            continue
        raw_candidates.append(
            SpanCandidate(
                text=text,
                start_word_id=span_words[0].id,
                end_word_id=span_words[-1].id,
                features={
                    "head_deprel": head.deprel,
                    "head_upos": head.upos,
                },
            )
        )

    seen = set()
    deduped = []
    for candidate in raw_candidates:
        key = (candidate.start_word_id, candidate.end_word_id, candidate.text)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return deduped


def rule_label_condition(candidate: SpanCandidate, sentence, lang: str = "ko") -> tuple[str, str | None, float]:
    text = candidate.text
    lowered = text.lower()
    token_count = len(text.split())
    rules = _get_lang_rules(lang)

    if any(token.lower() in lowered for token in rules["negative"]):
        return "POLARITY", "NEG", 0.9

    recipient_token_limit = 4 if lang in {"ko", "ja", "zh"} else 8
    if lang == "ko" and re.search(r"(에게|한테|께)\s*$", text):
        return "RECIPIENT", text, 0.92
    if any(token.lower() in lowered for token in rules["recipient"]) and token_count <= recipient_token_limit:
        return "RECIPIENT", text, 0.9

    if any(token.lower() in lowered for token in rules["purpose"]):
        return "PURPOSE", text, 0.88

    if any(token.lower() in lowered for token in rules["method"]):
        return "METHOD", text, 0.86
    if lang == "ko" and re.search(r"(이메일|메일|문자|전화|채팅|도구)로\s*$", text):
        return "METHOD", text, 0.86

    if any(token.lower() in lowered for token in rules["loc"]):
        if any(token.lower() in lowered for token in rules["time"]):
            return "TIME", text, 0.6
        return "LOC", text, 0.72
    if lang == "ko" and token_count <= 2 and text.endswith("에"):
        return "LOC", text, 0.72

    if lang == "ko" and ("참조" in text or "참고" in text):
        return "METHOD", text, 0.82

    if any(token.lower() in lowered for token in rules["duration"]):
        return "DURATION", text, 0.9

    if any(token.lower() in lowered for token in rules["time"]):
        return "TIME", text, 0.92

    if re.search(r"\d", text):
        if any(token.lower() in lowered for token in rules["value_units"]):
            return "VALUE", text, 0.92

    for ent in getattr(sentence, "ents", []) or []:
        if ent.text in text:
            if ent.type in {"DATE", "TIME"}:
                return "TIME", ent.text, 0.9
            if ent.type in {"LOC", "GPE", "FAC"}:
                return "LOC", ent.text, 0.9
            if ent.type in {"MONEY", "PERCENT", "QUANTITY", "CARDINAL"}:
                return "VALUE", ent.text, 0.9
            if ent.type in {"ORG", "PERSON"} and any(x.lower() in lowered for x in rules["recipient"]):
                return "RECIPIENT", ent.text, 0.85

    return "UNKNOWN", None, 0.35