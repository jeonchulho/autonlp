from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path


NAME_TOKEN = {
    "ko": r"[\w가-힣]+",
    "en": r"[A-Za-z0-9_]+",
    "ja": r"[\wぁ-んァ-ン一-龥ー]+",
    "zh": r"[A-Za-z0-9_一-龥㐀-䶿]{1,20}",
    "fr": r"[A-Za-zÀ-ÖØ-öø-ÿ0-9_\-']+",
    "de": r"[A-Za-zÄÖÜäöüß0-9_\-']+",
    "ar": r"[\w\u0600-\u06FF]{1,20}",
}

LIST_SEPARATORS = r"[,，、،]"

RECIPIENT_TO_FORMS = {
    "ko": ["에게", "한테", "께"],
    "en": ["to", "for"],
    "ja": ["に", "宛て", "向け"],
    "zh": ["给", "向", "对"],
    "fr": ["à", "pour"],
    "de": ["an", "für"],
    "ar": ["إلى", "لـ"],
}

SUBJECT_ACTION_FORMS = {
    "ko": ["수신한", "수신했던", "받은", "받았던", "전송한", "전송했던", "보낸", "보냈던"],
    "en": ["received", "got", "sent", "transmitted"],
    "ja": ["受信した", "受け取った", "送った", "送信した"],
    "zh": ["收到了", "收到", "接收了", "接收", "发送了", "發送了", "传送了", "傳送了"],
    "fr": ["reçu", "reçus", "envoyé", "envoyés"],
    "de": ["empfangen", "erhalten", "gesendet", "versendet"],
    "ar": ["استلموا", "تلقوا", "أرسلوا"],
}

ACTION_FILTER_FORMS = {
    "ko": ["보낸", "보냈던", "전송한", "전송했던", "수신한", "수신했던", "받은", "받았던"],
    "en": ["sent", "transmitted", "delivered", "received"],
    "ja": ["送った", "送信した", "受信した", "受け取った"],
    "zh": ["发送的", "發送的", "传送的", "傳送的", "接收的", "收到的"],
    "fr": ["envoyé", "envoyée", "envoyés", "envoyées", "reçu", "reçue", "reçus", "reçues"],
    "de": ["gesendet", "versendet", "empfangen"],
    "ar": ["المرسلة", "المرسل", "المستلمة", "المستلم"],
}

REPORT_VERB_REGEX_BY_LANG = {
    "ko": r"(밝혔|말했|전했|설명했|주장했|언급했|발표했|보도했)",
    "en": r"^(said|stated|announced|reported|noted|added|told)$",
    "fr": r"^(déclaré|indiqué|annoncé|rapporté|affirmé|ajouté)$",
    "de": r"^(sagte|erklärte|berichtete|meldete|fügte)$",
    "ar": r"(قال|صرح|أعلن|ذكر|أفاد)",
    "zh": r"(称|表示|指出|说|宣布)",
    "ja": r"(述べ|語|発表|明らか)",
}

SUBJECT_TIME_STOPWORDS_BY_LANG = {
    "ko": {"이날", "당일", "오늘", "어제", "내일"},
    "en": {"today", "yesterday", "tomorrow"},
    "fr": {"aujourd'hui", "hier", "demain"},
    "de": {"heute", "gestern", "morgen"},
    "zh": {"今天", "昨天", "明天", "当日", "当天"},
    "ja": {"今日", "昨日", "明日", "当日"},
    "ar": {"اليوم", "أمس", "غدًا", "غدا"},
}

SUBJECT_NULL_TOKENS_BY_LANG = {
    "ko": {"쪽지", "메시지", "메일", "이메일", "문자", "내용"},
    "en": {"message", "messages", "mail", "email", "text", "content"},
    "fr": {"message", "messages", "mail", "e-mail", "sms", "contenu"},
    "de": {"nachricht", "nachrichten", "mail", "e-mail", "sms", "inhalt"},
    "ja": {"メッセージ", "メール", "内容"},
    "zh": {"消息", "邮件", "短信", "内容"},
    "ar": {"رسالة", "رسائل", "بريد", "بريد إلكتروني", "رسالة نصية", "المحتوى"},
}

OBJECT_SPLIT_SEPARATORS_BY_LANG = {
    "ko": ["및", "와", "과", "또는"],
    "en": ["and", "or"],
    "ja": ["と", "および", "または"],
    "zh": ["和", "及", "以及", "或", "或者"],
    "fr": ["et", "ou"],
    "de": ["und", "oder"],
    "ar": ["و", "أو"],
}

TIME_LIKE_OBJECT_TOKENS_BY_LANG = {
    "ko": {"어제", "오늘", "내일", "지금", "방금", "최근", "이번", "지난"},
    "en": {"yesterday", "today", "tomorrow", "now", "recent", "latest", "this", "last"},
    "fr": {"hier", "aujourd'hui", "demain", "maintenant", "récent", "dernier", "cette", "ce"},
    "de": {"gestern", "heute", "morgen", "jetzt", "aktuell", "letzte", "dies", "diese"},
    "ja": {"昨日", "今日", "明日", "今", "最近", "今回", "前回", "当日"},
    "zh": {"昨天", "今天", "明天", "现在", "最近", "本次", "上次", "当日"},
    "ar": {"أمس", "اليوم", "غدًا", "غدا", "الآن", "مؤخرًا", "الأخيرة", "هذه"},
}

REFERENTIAL_TOKENS_BY_LANG = {
    "en": {"it", "this", "that", "the content", "this content", "that content", "content"},
    "ja": {"内容", "その内容", "これ", "それ"},
    "zh": {"内容", "这个内容", "那个内容", "该内容", "这个", "那个"},
    "fr": {"contenu", "ce contenu", "ceci", "cela", "ça"},
    "de": {"inhalt", "dieser inhalt", "dies", "das", "es"},
    "ar": {"المحتوى", "هذا المحتوى", "ذلك المحتوى", "هذا", "ذلك"},
}

PREFERRED_MESSAGE_NOUNS_BY_LANG = {
    "ko": [
        "쪽지함",
        "메시지함",
        "메일함",
        "이메일함",
        "문자함",
        "쪽지내역",
        "메시지내역",
        "메일내역",
        "이메일내역",
        "문자내역",
        "쪽지",
        "메시지",
        "문자",
        "메일",
        "이메일",
    ],
    "en": ["message history", "message thread", "mailbox", "inbox", "messages", "message", "email", "mail", "text"],
    "ja": ["メッセージ履歴", "メールボックス", "受信箱", "メッセージ", "メール"],
    "zh": ["消息记录", "消息历史", "邮箱", "收件箱", "消息", "邮件", "短信"],
    "fr": [
        "historique des messages",
        "boîte mail",
        "boîte de réception",
        "les messages",
        "des messages",
        "un message",
        "messages",
        "message",
        "e-mail",
        "mail",
        "sms",
    ],
    "de": ["nachrichtenverlauf", "postfach", "eingang", "nachrichten", "nachricht", "e-mail", "mail", "sms"],
    "ar": ["سجل الرسائل", "صندوق البريد", "البريد الوارد", "رسائل", "رسالة", "بريد إلكتروني", "بريد", "رسالة نصية"],
}

REFERENCE_OBJECT_TOKENS_BY_LANG = {
    "ko": {"그내용", "그내용을", "그 내용", "그 내용을", "내용", "내용을", "것", "그것", "그것을"},
    "en": {"content", "the content", "this content", "that content", "it", "this", "that"},
    "fr": {"contenu", "ce contenu", "ceci", "cela", "ça"},
    "de": {"inhalt", "dieser inhalt", "dies", "das", "es"},
    "ja": {"内容", "その内容", "これ", "それ"},
    "zh": {"内容", "这个内容", "那个内容", "该内容", "这个", "那个"},
    "ar": {"المحتوى", "هذا المحتوى", "ذلك المحتوى", "هذا", "ذلك"},
}

CONNECTORS_BY_LANG = {
    "ko": {"및", "와", "과", "또는", ",", "，", "、"},
    "en": {"and", "or", ",", "，", "、"},
    "fr": {"et", "ou", ",", "，", "、"},
    "de": {"und", "oder", ",", "，", "、"},
    "ja": {"と", "および", "または", ",", "，", "、"},
    "zh": {"和", "及", "以及", "或", "或者", ",", "，", "、"},
    "ar": {"و", "أو", ",", "،", "，", "、"},
}


PATTERN_REGEX_BY_KEY = {
    "quote_edges": r"^[\"'“”‘’`]+|[\"'“”‘’`]+$",
    "quote_all": r"[\"'“”‘’`]+",
    "trail_punct": r"[.,!?;:]+$",
    "ko_subject_particle": r"(이|가|은|는|께서)$",
    "ko_day_suffix": r"\d+일$",
    "ko_day_token_exact": r"^(\d{1,2}일|이날|당일|오늘|어제|내일)$",
    "ko_predicate_dago": r"다고$",
    "ko_reference_method": r"(참조해서|참조해|참조|참고해서|참고해|참고)",
    "ko_numeric_day": r"\b(\d{1,2})일\b",
    "ko_value_people": r"(\d+[여]?[\s]*명)(?:이|가|은|는|을|를)?",
    "ko_value_tens_people": r"수십\s*명",
    "ko_value_ships": r"(\d+[여]?\s*척)(?:이|가|은|는|을|를)?",
    "ko_object_particle": r"(을|를|은|는|이|가)$",
    "cjk_inner_space": r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])",
    "arabic_script": r"[\u0600-\u06FF]",
}

PREDICATE_CONJ_END_REGEX_BY_LANG = {
    "ko": r"(고|서|해|줘|다)$",
    "en": r"(ing|ed|en|s)$",
    "fr": r"(é|ée|és|ées|ant)$",
    "de": r"(en|t|te|end)$",
    "ja": r"(て|で|し|して)$",
    "zh": r"(着|了|过)$",
    "ar": r"(ت|وا|ون|ين)$",
}

PREDICATE_ACL_END_REGEX_BY_LANG = {
    "ko": r"(다|다는|됐다|됐다는|했다|했다는)$",
    "en": r"(ed|ing|en)$",
    "fr": r"(é|ée|és|ées|ant)$",
    "de": r"(en|te|ten)$",
    "ja": r"(た|ている|している)$",
    "zh": r"(的|了|过)$",
    "ar": r"(ت|وا|ون|ين)$",
}

PREDICATE_CONNECTOR_STOPWORDS_BY_LANG = {
    "ko": {"그리고", "또는", "및", "와", "과"},
    "en": {"and", "or", "then", "also"},
    "fr": {"et", "ou", "puis", "aussi"},
    "de": {"und", "oder", "dann", "auch"},
    "ja": {"そして", "または", "および", "また"},
    "zh": {"和", "及", "以及", "或", "而且"},
    "ar": {"و", "أو", "ثم", "أيضًا", "ايضا"},
}

PREDICATE_SKIP_NEXT_AUX_TOKENS_BY_LANG = {
    "ko": {"할", "한", "하는"},
    "en": {"be", "been", "being", "have", "has", "had"},
    "fr": {"être", "été", "ayant", "avoir", "a", "ont"},
    "de": {"sein", "gewesen", "haben", "hat", "haben"},
    "ar": {"كان", "كانت", "يكون", "تكون", "ليس", "ليست"},
}

PREDICATE_EVENT_LIKE_REGEX_BY_LANG = {
    "ko": r"(침몰|격침|실종|발사|전해|밝혔|작성|보내|참조|알려)",
    "en": r"(sink|sank|launch|torpedo|destroy|miss|dead|killed|attack|rescue|explode)",
    "fr": r"(coulé|couler|tiré|tirer|torpille|frapp|détruit|disparu|attaque|explos|produit|produite|survenu|survenue)",
    "de": r"(torpedo|feuer|versenk|sank|explod|angriff|vermisst|getötet)",
    "ar": r"(أطلق|أغر|غرق|هجم|انفجر|فقد|قتل)",
    "ja": r"(沈|沈没|撃沈|爆発|失踪|救助|攻撃)",
    "zh": r"(沉没|击沉|爆炸|失踪|袭击|救援|发生)",
}

PREDICATE_SUPPRESS_TOKENS_BASE_BY_LANG = {
    "ko": {"입장이다", "것이다", "나온", "나왔다"},
    "en": {"said", "stated", "announced", "reported", "added", "noted"},
    "fr": {"déclaré", "indiqué", "annoncé", "rapporté", "affirmé"},
    "de": {"sagte", "erklärte", "berichtete", "meldete", "fügte"},
    "ar": {"قال", "صرح", "أعلن", "ذكر", "أفاد"},
    "ja": {"述べ", "述べた", "語", "語った", "発表"},
    "zh": {"表示", "称", "指出", "宣布", "提到"},
}

PREDICATE_SUPPRESS_TOKENS_EXTRA_BY_LANG = {
    "ko": {"밝혔다", "전했다", "말했다"},
    "en": {"told", "says", "saying"},
    "fr": {"dit", "ajouté", "ajoute"},
    "de": {"gesagt", "sagt", "hinzugefügt"},
    "ja": {"述べた", "語った", "付け加えた"},
    "zh": {"表示", "称", "补充"},
    "ar": {"أضاف", "أوضح", "قالت"},
}

AUXILIARIES_BY_LANG = {
    "en": {"be", "do", "have"},
    "fr": {"être", "avoir"},
    "de": {"sein", "haben"},
}


def _normalize_str_map(value: object, default: dict[str, str]) -> dict[str, str]:
    if not isinstance(value, dict):
        return default
    normalized: dict[str, str] = {}
    for key, item in value.items():
        if isinstance(key, str) and isinstance(item, str):
            normalized[key.lower()] = item
    return normalized or default


def _normalize_list_map(value: object, default: dict[str, list[str]]) -> dict[str, list[str]]:
    if not isinstance(value, dict):
        return default
    normalized: dict[str, list[str]] = {}
    for key, item in value.items():
        if isinstance(key, str) and isinstance(item, list):
            tokens = [token for token in item if isinstance(token, str) and token.strip()]
            if tokens:
                normalized[key.lower()] = tokens
    return normalized or default


def _normalize_set_map(value: object, default: dict[str, set[str]]) -> dict[str, set[str]]:
    if not isinstance(value, dict):
        return default
    normalized: dict[str, set[str]] = {}
    for key, item in value.items():
        if isinstance(key, str) and isinstance(item, list):
            tokens = {token for token in item if isinstance(token, str) and token.strip()}
            if tokens:
                normalized[key.lower()] = tokens
    return normalized or default


def _apply_patterns_data_overrides() -> None:
    global NAME_TOKEN
    global LIST_SEPARATORS
    global RECIPIENT_TO_FORMS
    global SUBJECT_ACTION_FORMS
    global ACTION_FILTER_FORMS
    global REPORT_VERB_REGEX_BY_LANG
    global SUBJECT_TIME_STOPWORDS_BY_LANG
    global SUBJECT_NULL_TOKENS_BY_LANG
    global OBJECT_SPLIT_SEPARATORS_BY_LANG
    global TIME_LIKE_OBJECT_TOKENS_BY_LANG
    global REFERENTIAL_TOKENS_BY_LANG
    global PREFERRED_MESSAGE_NOUNS_BY_LANG
    global REFERENCE_OBJECT_TOKENS_BY_LANG
    global CONNECTORS_BY_LANG
    global PATTERN_REGEX_BY_KEY
    global PREDICATE_CONJ_END_REGEX_BY_LANG
    global PREDICATE_ACL_END_REGEX_BY_LANG
    global PREDICATE_CONNECTOR_STOPWORDS_BY_LANG
    global PREDICATE_SKIP_NEXT_AUX_TOKENS_BY_LANG
    global PREDICATE_EVENT_LIKE_REGEX_BY_LANG
    global PREDICATE_SUPPRESS_TOKENS_BASE_BY_LANG
    global PREDICATE_SUPPRESS_TOKENS_EXTRA_BY_LANG
    global AUXILIARIES_BY_LANG

    path = Path(__file__).with_name("patterns_data.json")
    if not path.exists():
        return

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return

    if not isinstance(payload, dict):
        return

    NAME_TOKEN = _normalize_str_map(payload.get("NAME_TOKEN"), NAME_TOKEN)
    list_separators = payload.get("LIST_SEPARATORS")
    if isinstance(list_separators, str) and list_separators:
        LIST_SEPARATORS = list_separators

    RECIPIENT_TO_FORMS = _normalize_list_map(payload.get("RECIPIENT_TO_FORMS"), RECIPIENT_TO_FORMS)
    SUBJECT_ACTION_FORMS = _normalize_list_map(payload.get("SUBJECT_ACTION_FORMS"), SUBJECT_ACTION_FORMS)
    ACTION_FILTER_FORMS = _normalize_list_map(payload.get("ACTION_FILTER_FORMS"), ACTION_FILTER_FORMS)
    REPORT_VERB_REGEX_BY_LANG = _normalize_str_map(payload.get("REPORT_VERB_REGEX_BY_LANG"), REPORT_VERB_REGEX_BY_LANG)
    SUBJECT_TIME_STOPWORDS_BY_LANG = _normalize_set_map(payload.get("SUBJECT_TIME_STOPWORDS_BY_LANG"), SUBJECT_TIME_STOPWORDS_BY_LANG)
    SUBJECT_NULL_TOKENS_BY_LANG = _normalize_set_map(payload.get("SUBJECT_NULL_TOKENS_BY_LANG"), SUBJECT_NULL_TOKENS_BY_LANG)
    OBJECT_SPLIT_SEPARATORS_BY_LANG = _normalize_list_map(payload.get("OBJECT_SPLIT_SEPARATORS_BY_LANG"), OBJECT_SPLIT_SEPARATORS_BY_LANG)
    TIME_LIKE_OBJECT_TOKENS_BY_LANG = _normalize_set_map(payload.get("TIME_LIKE_OBJECT_TOKENS_BY_LANG"), TIME_LIKE_OBJECT_TOKENS_BY_LANG)
    REFERENTIAL_TOKENS_BY_LANG = _normalize_set_map(payload.get("REFERENTIAL_TOKENS_BY_LANG"), REFERENTIAL_TOKENS_BY_LANG)
    PREFERRED_MESSAGE_NOUNS_BY_LANG = _normalize_list_map(payload.get("PREFERRED_MESSAGE_NOUNS_BY_LANG"), PREFERRED_MESSAGE_NOUNS_BY_LANG)
    REFERENCE_OBJECT_TOKENS_BY_LANG = _normalize_set_map(payload.get("REFERENCE_OBJECT_TOKENS_BY_LANG"), REFERENCE_OBJECT_TOKENS_BY_LANG)
    CONNECTORS_BY_LANG = _normalize_set_map(payload.get("CONNECTORS_BY_LANG"), CONNECTORS_BY_LANG)
    PATTERN_REGEX_BY_KEY = _normalize_str_map(payload.get("PATTERN_REGEX_BY_KEY"), PATTERN_REGEX_BY_KEY)
    PREDICATE_CONJ_END_REGEX_BY_LANG = _normalize_str_map(payload.get("PREDICATE_CONJ_END_REGEX_BY_LANG"), PREDICATE_CONJ_END_REGEX_BY_LANG)
    PREDICATE_ACL_END_REGEX_BY_LANG = _normalize_str_map(payload.get("PREDICATE_ACL_END_REGEX_BY_LANG"), PREDICATE_ACL_END_REGEX_BY_LANG)
    PREDICATE_CONNECTOR_STOPWORDS_BY_LANG = _normalize_set_map(payload.get("PREDICATE_CONNECTOR_STOPWORDS_BY_LANG"), PREDICATE_CONNECTOR_STOPWORDS_BY_LANG)
    PREDICATE_SKIP_NEXT_AUX_TOKENS_BY_LANG = _normalize_set_map(payload.get("PREDICATE_SKIP_NEXT_AUX_TOKENS_BY_LANG"), PREDICATE_SKIP_NEXT_AUX_TOKENS_BY_LANG)
    PREDICATE_EVENT_LIKE_REGEX_BY_LANG = _normalize_str_map(payload.get("PREDICATE_EVENT_LIKE_REGEX_BY_LANG"), PREDICATE_EVENT_LIKE_REGEX_BY_LANG)
    PREDICATE_SUPPRESS_TOKENS_BASE_BY_LANG = _normalize_set_map(payload.get("PREDICATE_SUPPRESS_TOKENS_BASE_BY_LANG"), PREDICATE_SUPPRESS_TOKENS_BASE_BY_LANG)
    PREDICATE_SUPPRESS_TOKENS_EXTRA_BY_LANG = _normalize_set_map(payload.get("PREDICATE_SUPPRESS_TOKENS_EXTRA_BY_LANG"), PREDICATE_SUPPRESS_TOKENS_EXTRA_BY_LANG)
    AUXILIARIES_BY_LANG = _normalize_set_map(payload.get("AUXILIARIES_BY_LANG"), AUXILIARIES_BY_LANG)


_apply_patterns_data_overrides()


def get_connectors(lang: str) -> set[str]:
    lang_key = (lang or "en").lower()
    return set(CONNECTORS_BY_LANG.get(lang_key, CONNECTORS_BY_LANG.get("en", set())))


def _alts(values: list[str]) -> str:
    escaped = [re.escape(value) for value in values]
    escaped.sort(key=len, reverse=True)
    return "(?:" + "|".join(escaped) + ")"


@lru_cache(maxsize=256)
def get_pattern(lang: str, key: str) -> re.Pattern:
    lang = (lang or "en").lower()
    name_token = NAME_TOKEN.get(lang, NAME_TOKEN["en"])
    name_list = rf"({name_token}(?:\s*{LIST_SEPARATORS}\s*{name_token})*)"
    name_list_at_least_two = rf"({name_token}(?:\s*{LIST_SEPARATORS}\s*{name_token})+)"

    if key == "query_split":
        return re.compile(LIST_SEPARATORS)

    if key == "recipient_to":
        forms = _alts(RECIPIENT_TO_FORMS.get(lang, []))
        if lang == "ko":
            return re.compile(rf"{name_list}\s*{forms}")
        if lang in {"ja", "zh", "ar"}:
            return re.compile(rf"{forms}\s*{name_list}")
        return re.compile(rf"{forms}\s+{name_list}", re.IGNORECASE)

    if key == "subject_action_recipient":
        forms = _alts(SUBJECT_ACTION_FORMS.get(lang, []))
        if lang == "ko":
            return re.compile(rf"{name_list_at_least_two}\s*(?:이|가)\s*{forms}")
        if lang == "en":
            return re.compile(rf"{name_list_at_least_two}\s+{forms}\b", re.IGNORECASE)
        if lang == "ja":
            return re.compile(rf"{name_list_at_least_two}\s*(?:が|は)\s*{forms}")
        if lang == "zh":
            return re.compile(rf"{name_list_at_least_two}\s*{forms}")
        if lang == "fr":
            return re.compile(rf"{name_list_at_least_two}\s+ont\s+{forms}", re.IGNORECASE)
        if lang == "de":
            return re.compile(
                rf"{name_list_at_least_two}\s+haben(?:\s+{name_token}){{0,4}}\s+{forms}",
                re.IGNORECASE,
            )
        if lang == "ar":
            return re.compile(rf"{name_list_at_least_two}\s*{forms}")

    if key == "action_filter":
        forms = _alts(ACTION_FILTER_FORMS.get(lang, []))
        if lang in {"en", "fr", "de"}:
            return re.compile(rf"\b({forms})\b", re.IGNORECASE)
        return re.compile(rf"({forms})")

    if key == "report_verb":
        pattern = REPORT_VERB_REGEX_BY_LANG.get(lang)
        if not pattern:
            raise KeyError(f"Unsupported report_verb lang: {lang}")
        flags = re.IGNORECASE if lang in {"en", "fr", "de"} else 0
        return re.compile(pattern, flags)

    if key in PATTERN_REGEX_BY_KEY:
        return re.compile(PATTERN_REGEX_BY_KEY[key])

    if key == "object_split":
        separators = OBJECT_SPLIT_SEPARATORS_BY_LANG.get(lang, []) + ["/", "／", "·", "・", "&", ",", "，", "、", "|"]
        token_pattern = "|".join(sorted((re.escape(token) for token in separators), key=len, reverse=True))
        return re.compile(rf"\s*(?:{token_pattern})\s*")

    raise KeyError(f"Unsupported pattern key: {key} (lang={lang})")
