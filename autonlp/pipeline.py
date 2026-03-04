from __future__ import annotations

import re
from typing import Iterable, Optional

import stanza

from .llm import BaseLLMLabeler, NullLLMLabeler
from .rules import collect_condition_candidates, detect_sentence_polarity, extract_recipients_from_text, rule_label_condition
from .schema import Condition, ExtractionResult, SentenceExtraction
from .srl import BaseSRLProvider, NullSRLProvider, map_srl_role_to_label
from .time_normalizer import normalize_time_expression


LANG_ALIASES = {
    "ko": "ko",
    "kr": "ko",
    "ko-kr": "ko",
    "en": "en",
    "en-us": "en",
    "en-gb": "en",
    "ja": "ja",
    "jp": "ja",
    "ja-jp": "ja",
    "zh": "zh",
    "zh-cn": "zh",
    "zh-tw": "zh",
    "fr": "fr",
    "fr-fr": "fr",
    "de": "de",
    "de-de": "de",
    "ar": "ar",
    "ar-sa": "ar",
}


class ConditionExtractorPipeline:
    def __init__(
        self,
        lang: str = "ko",
        srl_provider: Optional[BaseSRLProvider] = None,
        llm_labeler: Optional[BaseLLMLabeler] = None,
        reference_datetime=None,
        recipient_lexicon: Optional[Iterable[str]] = None,
        normalize_object_items: bool = True,
        object_join_token: Optional[str] = None,
        config: Optional[dict] = None,
    ):
        self.lang = LANG_ALIASES.get(lang.lower(), lang.lower())
        self.srl_provider = srl_provider or NullSRLProvider()
        self.llm_labeler = llm_labeler or NullLLMLabeler()
        self.reference_datetime = reference_datetime
        self.recipient_lexicon = self._normalize_recipient_lexicon(recipient_lexicon)
        self.normalize_object_items = normalize_object_items
        self.object_join_token = object_join_token
        self.config = config or {}
        self._nlp = self._build_stanza_pipeline(self.lang)

    def _normalize_recipient_lexicon(self, recipient_lexicon: Optional[Iterable[str]]) -> Optional[set[str]]:
        if recipient_lexicon is None:
            return None
        normalized = set()
        for item in recipient_lexicon:
            value = item.strip()
            if not value:
                continue
            normalized.add(value)
            normalized.add(value.lower())
        return normalized or None

    def _is_allowed_recipient(self, recipient: str) -> bool:
        if self.recipient_lexicon is None:
            return True
        token = recipient.strip()
        return token in self.recipient_lexicon or token.lower() in self.recipient_lexicon

    def _build_stanza_pipeline(self, lang: str):
        fallback_processors = ["tokenize", "pos", "lemma", "depparse"]
        preferred_processors = (
            fallback_processors
            if lang == "ko"
            else ["tokenize", "pos", "lemma", "depparse", "ner"]
        )
        try:
            return stanza.Pipeline(
                lang=lang,
                processors=",".join(preferred_processors),
                use_gpu=False,
                verbose=False,
            )
        except Exception:
            try:
                stanza.download(lang=lang, processors=",".join(preferred_processors), verbose=False)
                return stanza.Pipeline(
                    lang=lang,
                    processors=",".join(preferred_processors),
                    use_gpu=False,
                    verbose=False,
                )
            except Exception:
                stanza.download(lang=lang, processors=",".join(fallback_processors), verbose=False)
                return stanza.Pipeline(
                    lang=lang,
                    processors=",".join(fallback_processors),
                    use_gpu=False,
                    verbose=False,
                )

    def extract(self, text: str) -> ExtractionResult:
        doc = self._nlp(text)
        sentence_results: list[SentenceExtraction] = []
        for sentence in doc.sentences:
            base_predicate, base_subject, base_object = self._extract_svo(sentence)
            conditions = self._extract_conditions(sentence)

            predicate_words = self._extract_predicate_words(sentence)
            if not predicate_words:
                predicate_words = [None]

            predicate_ids = [word.id for word in predicate_words if word is not None]
            conditions_by_predicate = self._assign_conditions_to_predicates(sentence, conditions, predicate_words)
            for predicate_word in predicate_words:
                predicate_text = self._normalize_predicate_text(
                    predicate_word.text if predicate_word is not None else base_predicate
                )
                subject_text = self._extract_subject_for_predicate(
                    sentence,
                    predicate_word.id if predicate_word is not None else None,
                    predicate_ids,
                    base_subject,
                )
                object_text = self._extract_object_for_predicate(
                    sentence,
                    predicate_word.id if predicate_word is not None else None,
                    predicate_ids,
                    base_object,
                )

                predicate_conditions = (
                    conditions_by_predicate.get(predicate_word.id, conditions)
                    if predicate_word is not None
                    else conditions
                )
                recipients = self._collect_recipients_from_conditions(predicate_conditions)

                sentence_result = SentenceExtraction(
                    text=sentence.text,
                    predicate=predicate_text,
                    subject=subject_text,
                    object=object_text,
                    conditions=predicate_conditions,
                    recipients=recipients,
                )
                sentence_result.object_items = self._split_object_items(sentence_result.object)
                sentence_result.object_normalized = self._compose_object_normalized(sentence_result.object_items)
                sentence_results.append(sentence_result)

        return ExtractionResult(text=text, sentences=sentence_results)

    def _extract_subject_for_predicate(
        self,
        sentence,
        predicate_id: Optional[int],
        predicate_ids: list[int],
        fallback_subject: Optional[str],
    ) -> Optional[str]:
        if predicate_id is None:
            return self._clean_subject_text(fallback_subject)

        words = sentence.words
        by_id = {word.id: word for word in words}
        predicate_word = by_id.get(predicate_id)
        predicate_text = predicate_word.text if predicate_word is not None else ""
        is_report_verb = self._is_report_verb(predicate_text)
        previous_predicate_id = max((pid for pid in predicate_ids if pid < predicate_id), default=0)

        direct_subject = next(
            (
                word
                for word in words
                if word.head == predicate_id and word.deprel in {"nsubj", "csubj"}
            ),
            None,
        )
        if direct_subject is not None:
            subject_ids = {direct_subject.id}
            for word in words:
                if (
                    word.head == direct_subject.id
                    and word.id < direct_subject.id
                    and word.deprel in {"compound", "amod", "nummod", "det", "nmod"}
                ):
                    if self.lang == "ko" and (
                        re.search(r"\d+일$", word.text)
                        or word.text in {"이날", "당일", "오늘", "어제", "내일"}
                    ):
                        continue
                    subject_ids.add(word.id)
            subject_words = [by_id[idx] for idx in sorted(subject_ids) if idx in by_id]
            subject_text = " ".join(word.text for word in subject_words).strip()
            subject_text = self._clean_subject_text(subject_text)
            if subject_text:
                return subject_text

        local_subject_candidates = [
            word
            for word in words
            if previous_predicate_id < word.id < predicate_id and word.deprel in {"nsubj", "csubj"}
        ]
        if local_subject_candidates:
            subject_text = self._clean_subject_text(local_subject_candidates[-1].text)
            if subject_text:
                return subject_text

        global_subject_candidates = [
            word
            for word in words
            if word.id < predicate_id and word.deprel in {"nsubj", "csubj"}
        ]
        if global_subject_candidates:
            candidate = global_subject_candidates[0] if is_report_verb else global_subject_candidates[-1]
            subject_text = self._clean_subject_text(candidate.text)
            if subject_text:
                return subject_text

        if self.lang != "ko":
            return self._clean_subject_text(fallback_subject)

        preceding_subjects = [
            word
            for word in words
            if previous_predicate_id < word.id < predicate_id
            and word.upos in {"NOUN", "PROPN"}
            and re.search(r"(이|가|은|는|께서)$", word.text)
        ]
        if preceding_subjects:
            candidate = self._clean_subject_text(preceding_subjects[-1].text)
            if candidate:
                return candidate

        return self._clean_subject_text(fallback_subject)

    def _is_report_verb(self, predicate_text: str) -> bool:
        value = (predicate_text or "").strip().lower()
        if not value:
            return False

        if self.lang == "ko":
            return bool(re.search(r"(밝혔|말했|전했|설명했|주장했|언급했|발표했|보도했)", value))
        if self.lang == "en":
            return value in {"said", "stated", "announced", "reported", "noted", "added", "told"}
        if self.lang == "fr":
            return value in {"déclaré", "indiqué", "annoncé", "rapporté", "affirmé", "ajouté"}
        if self.lang == "de":
            return value in {"sagte", "erklärte", "berichtete", "meldete", "fügte"}
        if self.lang == "ar":
            return bool(re.search(r"(قال|صرح|أعلن|ذكر|أفاد)", value))
        if self.lang == "zh":
            return any(token in value for token in {"称", "表示", "指出", "说", "宣布"})
        if self.lang == "ja":
            return any(token in value for token in {"述べ", "語", "発表", "明らか"})

        return False

    def _clean_subject_text(self, subject_text: Optional[str]) -> Optional[str]:
        if subject_text is None:
            return None
        value = subject_text.strip()
        if not value:
            return None

        value = re.sub(r"^[\"'“”‘’`]+|[\"'“”‘’`]+$", "", value)
        value = re.sub(r"[\"'“”‘’`]+", "", value)

        if self.lang == "ko":
            value = re.sub(r"(이|가|은|는|께서)$", "", value).strip()
            if re.search(r"^(\d{1,2}일|이날|당일|오늘|어제|내일)$", value):
                return None
            if value in {"쪽지", "메시지", "메일", "이메일", "문자", "내용"}:
                return None

        if self.lang == "en":
            if value.lower() in {"today", "yesterday", "tomorrow"}:
                return None
        if self.lang == "fr":
            if value.lower() in {"aujourd'hui", "hier", "demain"}:
                return None
        if self.lang == "de":
            if value.lower() in {"heute", "gestern", "morgen"}:
                return None
        if self.lang == "zh":
            if value in {"今天", "昨天", "明天", "当日", "当天"}:
                return None
        if self.lang == "ja":
            if value in {"今日", "昨日", "明日", "当日"}:
                return None
        if self.lang == "ar":
            if value in {"اليوم", "أمس", "غدًا", "غدا"}:
                return None

        return value or None

    def _normalize_predicate_text(self, predicate: Optional[str]) -> Optional[str]:
        if predicate is None:
            return None
        normalized = predicate.strip()
        normalized = re.sub(r"^[\"'“”‘’`]+|[\"'“”‘’`]+$", "", normalized)
        normalized = re.sub(r"[\"'“”‘’`]+", "", normalized)
        normalized = re.sub(r"[.,!?;:]+$", "", normalized)
        if self.lang == "ko":
            normalized = re.sub(r"다고$", "다", normalized)
        return normalized or predicate

    def _extract_predicate_words(self, sentence) -> list:
        words = sentence.words
        by_id = {word.id: word for word in words}
        candidates = []
        for word in words:
            if word.upos in {"VERB", "ADJ"} and word.deprel in {"root", "conj", "advcl", "xcomp", "ccomp"}:
                candidates.append(word)
                continue

            if word.upos == "AUX" and word.deprel == "root":
                candidates.append(word)
                continue

            if self.lang == "ar" and word.upos == "X" and word.deprel in {"root", "conj"} and re.search(r"[\u0600-\u06FF]", word.text):
                candidates.append(word)
                continue

            if self.lang == "fr" and word.upos == "NOUN" and word.deprel in {"appos", "conj"}:
                prev_word = by_id.get(word.id - 1)
                next_word = by_id.get(word.id + 1)
                if prev_word is not None and prev_word.upos == "PUNCT" and next_word is not None and next_word.upos in {"DET", "PRON", "NOUN", "PROPN"}:
                    candidates.append(word)
                    continue

            if (
                self.lang == "ko"
                and word.upos in {"SCONJ", "CCONJ"}
                and word.deprel in {"root", "conj", "advcl", "ccomp"}
                and re.search(r"(고|서|해|줘|다)$", word.text)
                and word.text not in {"그리고", "또는", "및", "와", "과"}
            ):
                candidates.append(word)

            if (
                self.lang == "ko"
                and word.upos == "VERB"
                and word.deprel == "acl"
                and re.search(r"(다|다는|됐다|됐다는|했다|했다는)$", word.text)
            ):
                candidates.append(word)

        if self.lang == "ko" and candidates:
            filtered_candidates = []
            for word in candidates:
                next_word = by_id.get(word.id + 1)
                if (
                    word.upos == "VERB"
                    and next_word is not None
                    and next_word.upos == "AUX"
                    and next_word.text in {"할", "한", "하는"}
                ):
                    continue
                if (
                    word.upos == "VERB"
                    and word.deprel == "acl"
                    and next_word is not None
                    and next_word.upos in {"NOUN", "PROPN"}
                ):
                    continue
                if (
                    word.upos == "VERB"
                    and word.deprel == "conj"
                    and next_word is not None
                    and next_word.upos in {"NOUN", "PROPN"}
                    and any(later.upos in {"VERB", "AUX", "SCONJ", "CCONJ"} and later.id > next_word.id for later in words)
                ):
                    continue
                filtered_candidates.append(word)

            event_like_exists = any(
                re.search(r"(침몰|격침|실종|발사|전해|밝혔|작성|보내|참조|알려)", word.text)
                for word in filtered_candidates
            )
            if event_like_exists:
                suppress_report_verbs_ko = bool(self.config.get("suppress_report_verbs_ko", False)) if isinstance(self.config, dict) else False
                suppressible_tokens = {"입장이다", "것이다", "나온", "나왔다"}
                if suppress_report_verbs_ko:
                    suppressible_tokens.update({"밝혔다", "전했다", "말했다"})
                filtered_candidates = [
                    word
                    for word in filtered_candidates
                    if word.text not in suppressible_tokens
                ]

            candidates = filtered_candidates

        if self.lang in {"en", "fr", "de"} and candidates:
            auxiliaries = {"be", "do", "have", "être", "avoir", "sein", "haben"}
            filtered_candidates = []
            for word in candidates:
                lemma = (word.lemma or "").lower()
                if word.upos == "AUX" and lemma in auxiliaries:
                    continue
                filtered_candidates.append(word)
            candidates = filtered_candidates

        if self.lang == "en" and candidates:
            suppress_report_verbs_en = bool(self.config.get("suppress_report_verbs_en", False)) if isinstance(self.config, dict) else False
            if suppress_report_verbs_en:
                event_like_exists = any(
                    re.search(r"(sink|sank|launch|torpedo|destroy|miss|dead|killed|attack|rescue|explode)", (word.text or "").lower())
                    for word in candidates
                )
                if event_like_exists:
                    report_tokens = {"said", "stated", "announced", "reported", "added", "noted"}
                    candidates = [word for word in candidates if (word.text or "").lower() not in report_tokens]

        if self.lang == "fr" and candidates:
            suppress_report_verbs_fr = bool(self.config.get("suppress_report_verbs_fr", False)) if isinstance(self.config, dict) else False
            if suppress_report_verbs_fr:
                event_like_exists = any(
                    re.search(r"(coulé|couler|tiré|tirer|torpille|frapp|détruit|disparu|attaque|explos)", (word.text or "").lower())
                    for word in candidates
                )
                if event_like_exists:
                    report_tokens = {"déclaré", "indiqué", "annoncé", "rapporté", "affirmé"}
                    candidates = [word for word in candidates if (word.text or "").lower() not in report_tokens]

        if self.lang == "de" and candidates:
            suppress_report_verbs_de = bool(self.config.get("suppress_report_verbs_de", False)) if isinstance(self.config, dict) else False
            if suppress_report_verbs_de:
                event_like_exists = any(
                    re.search(r"(torpedo|feuer|versenk|sank|explod|angriff|vermisst|getötet)", (word.text or "").lower())
                    for word in candidates
                )
                if event_like_exists:
                    report_tokens = {"sagte", "erklärte", "berichtete", "meldete", "fügte"}
                    candidates = [word for word in candidates if (word.text or "").lower() not in report_tokens]

        if self.lang == "ar" and candidates:
            suppress_report_verbs_ar = bool(self.config.get("suppress_report_verbs_ar", False)) if isinstance(self.config, dict) else False
            if suppress_report_verbs_ar:
                event_like_exists = any(
                    re.search(r"(أطلق|أغر|غرق|هجم|انفجر|فقد|قتل)", (word.text or ""))
                    for word in candidates
                )
                if event_like_exists:
                    report_tokens = {"قال", "صرح", "أعلن", "ذكر", "أفاد"}
                    candidates = [word for word in candidates if (word.text or "") not in report_tokens]

        if not candidates:
            root = next((word for word in words if word.deprel == "root" and word.upos in {"VERB", "AUX", "ADJ"}), None)
            return [root] if root is not None else []

        deduped = []
        seen = set()
        for word in sorted(candidates, key=lambda item: item.id):
            key = (word.id, word.text)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(word)
        return deduped

    def _extract_object_for_predicate(
        self,
        sentence,
        predicate_id: Optional[int],
        predicate_ids: list[int],
        fallback_object: Optional[str],
    ) -> Optional[str]:
        if predicate_id is None:
            return fallback_object

        words = sentence.words
        by_id = {word.id: word for word in words}

        direct_object = next(
            (
                word
                for word in words
                if word.head == predicate_id and word.deprel in {"obj", "iobj"}
            ),
            None,
        )
        if direct_object is not None:
            object_ids = {direct_object.id}
            for word in words:
                if (
                    word.head == direct_object.id
                    and word.id < direct_object.id
                    and word.deprel in {"compound", "amod", "nummod", "det"}
                ):
                    object_ids.add(word.id)
            object_words = [by_id[idx] for idx in sorted(object_ids) if idx in by_id]
            direct_text = " ".join(word.text for word in object_words).strip()
            direct_text = self._clean_object_text(direct_text, sentence.text)
            return direct_text or fallback_object

        previous_predicate_id = max((pid for pid in predicate_ids if pid < predicate_id), default=0)
        next_predicate_id = min((pid for pid in predicate_ids if pid > predicate_id), default=max((word.id for word in words), default=predicate_id + 1) + 1)

        noun_like_labels_by_lang = {
            "ko": {"dep", "obj", "compound", "nmod"},
            "en": {"obj", "iobj", "nmod", "obl", "dep", "compound"},
            "ja": {"obj", "iobj", "nmod", "obl", "dep", "compound"},
            "zh": {"obj", "iobj", "nmod", "obl", "dep", "compound", "nsubj"},
            "fr": {"obj", "iobj", "nmod", "obl", "dep", "compound"},
            "de": {"obj", "iobj", "nmod", "obl", "dep", "compound"},
            "ar": {"obj", "iobj", "nmod", "obl", "dep", "compound", "obl:arg"},
        }
        noun_like_labels = noun_like_labels_by_lang.get(self.lang, {"obj", "iobj", "nmod", "obl", "dep", "compound"})

        preceding_nouns = [
            word
            for word in words
            if previous_predicate_id < word.id < predicate_id
            and word.upos in {"NOUN", "PROPN", "PRON"}
            and word.deprel in noun_like_labels
        ]

        following_nouns = [
            word
            for word in words
            if predicate_id < word.id < next_predicate_id
            and word.upos in {"NOUN", "PROPN", "PRON"}
            and word.deprel in noun_like_labels
        ]

        def _materialize_noun_phrase(nearest_word):
            nearest = nearest_word
            object_ids = {nearest.id}
            for word in words:
                if (
                    word.head == nearest.id
                    and word.id < nearest.id
                    and word.deprel in {"compound", "amod", "nummod", "det", "nmod"}
                ):
                    object_ids.add(word.id)
            object_words = [by_id[idx] for idx in sorted(object_ids) if idx in by_id]
            phrase = " ".join(word.text for word in object_words).strip()
            phrase = self._clean_object_text(phrase, sentence.text)
            return phrase

        if self.lang == "ko":
            if preceding_nouns:
                phrase = _materialize_noun_phrase(preceding_nouns[-1])
                if phrase:
                    return phrase
            if following_nouns:
                phrase = _materialize_noun_phrase(following_nouns[0])
                if phrase:
                    return phrase
        else:
            if following_nouns:
                phrase = _materialize_noun_phrase(following_nouns[0])
                if phrase:
                    return phrase
            if preceding_nouns:
                phrase = _materialize_noun_phrase(preceding_nouns[-1])
                if phrase:
                    return phrase

        span_words = [
            word
            for word in words
            if previous_predicate_id < word.id < predicate_id and word.upos in {"NOUN", "PROPN", "PRON", "ADJ", "CCONJ", "SYM"}
        ]
        if not span_words:
            return None

        if self.lang == "ko":
            if len(span_words) > 4:
                return None
            if any(re.search(r"(이|가)$", word.text) for word in span_words):
                return None

        text = " ".join(word.text for word in span_words).strip()
        if not text:
            return None

        text = self._clean_object_text(text, sentence.text)

        return text or None

    def _extract_svo(self, sentence) -> tuple[Optional[str], Optional[str], Optional[str]]:
        words = sentence.words
        predicate_word = next(
            (
                word
                for word in words
                if word.deprel == "root" and word.upos in {"VERB", "AUX", "ADJ"}
            ),
            None,
        )
        predicate = predicate_word.text if predicate_word else None

        subject_word = next((word for word in words if word.deprel in {"nsubj", "csubj"}), None)
        object_word = next((word for word in words if word.deprel == "obj"), None)
        if object_word is None:
            object_word = next((word for word in words if word.deprel == "iobj"), None)

        subject = subject_word.text if subject_word else None
        obj = object_word.text if object_word else None

        if self.lang == "ko" and subject:
            match = re.match(r"(.+?)(이|가|은|는|께서)$", subject)
            if match:
                subject = match.group(1).strip()

        if obj and predicate_word and predicate_word.id > object_word.id:
            start_id = object_word.id
            obj_modifiers = {
                word.id
                for word in words
                if word.head == object_word.id
                and word.id < object_word.id
                and word.deprel in {"compound", "amod", "nummod", "det"}
                and not (self.lang == "ko" and re.search(r"(이|가|은|는|께서)$", word.text))
            }
            if obj_modifiers:
                start_id = min(obj_modifiers)

            between_words = [word for word in words if start_id <= word.id < predicate_word.id]
            connectors = {"및", "와", "과", "또는", "and", "et", "und", "ou", "oder", "و", "أو", "和", "及", ",", "，", "、"}
            has_connector = any(word.text in connectors for word in between_words)
            has_next_noun = any(word.upos == "NOUN" and word.id > start_id for word in between_words)
            if has_connector and has_next_noun:
                obj = " ".join(word.text for word in between_words).strip()

        if obj and predicate_word and predicate_word.id < object_word.id:
            tail_words = [word for word in words if word.id >= object_word.id]
            connectors = {
                "및",
                "와",
                "과",
                "또는",
                "and",
                "or",
                "et",
                "ou",
                "und",
                "oder",
                "和",
                "及",
                "以及",
                "或",
                "或者",
                "و",
                "أو",
                ",",
                "，",
                "、",
            }
            has_connector = any(word.text in connectors for word in tail_words)
            has_next_noun = any(word.upos == "NOUN" and word.id > object_word.id for word in tail_words)
            if has_connector and has_next_noun:
                obj = " ".join(word.text for word in tail_words).strip()

        if obj is None and self.lang == "ko" and predicate_word:
            start_id = (subject_word.id + 1) if subject_word else 1
            span_words = [
                word
                for word in words
                if start_id <= word.id < predicate_word.id and word.upos in {"NOUN", "ADJ", "CCONJ", "SYM"}
            ]
            if span_words:
                obj = " ".join(word.text for word in span_words).strip()

        if subject is None and self.lang == "ko":
            for word in words:
                if word.upos != "NOUN":
                    continue
                match = re.match(r"(.+?)(이|가|은|는|께서)$", word.text)
                if match:
                    candidate = match.group(1).strip()
                    if candidate:
                        subject = candidate
                        break

        if self.lang == "ko" and obj:
            recipient_names = extract_recipients_from_text(sentence.text, lang=self.lang)
            if recipient_names and obj in recipient_names and re.search(r"(에게|한테|께)", sentence.text):
                obj = None

        if obj:
            obj = self._clean_object_text(obj, sentence.text)

        return predicate, subject, obj

    def _clean_object_text(self, obj_text: str, sentence_text: str) -> str:
        if self.lang == "ko":
            return self._clean_korean_object_text(obj_text, sentence_text)
        return self._clean_multilingual_referential_object_text(obj_text, sentence_text, self.lang)

    def _clean_korean_object_text(self, obj_text: str, sentence_text: str) -> str:
        tokens = [token for token in obj_text.split() if token]
        if not tokens:
            return obj_text

        referential_tokens = {"그내용", "그내용을", "그 내용", "그 내용을", "내용", "내용을", "것", "그것", "그것을"}
        collapsed = re.sub(r"\s+", "", obj_text)
        preferred_message_nouns = [
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
        ]

        def _pick_preferred_message_noun(text: str) -> Optional[str]:
            positions = [(text.find(noun), noun) for noun in preferred_message_nouns if noun in text]
            positions = [item for item in positions if item[0] >= 0]
            if not positions:
                return None
            positions.sort(key=lambda item: item[0])
            return positions[0][1]

        if collapsed in {"그내용", "그내용을", "내용", "내용을", "그것", "그것을", "것"}:
            preferred = _pick_preferred_message_noun(sentence_text)
            if preferred:
                return preferred

        if any(token in referential_tokens for token in tokens):
            preferred = _pick_preferred_message_noun(sentence_text)
            if preferred:
                return preferred

        recipient_names = set(extract_recipients_from_text(sentence_text, lang="ko"))
        time_like_tokens = {
            "어제",
            "오늘",
            "내일",
            "지금",
            "방금",
            "최근",
            "이번",
            "지난",
        }
        removable = recipient_names | time_like_tokens

        filtered = [token for token in tokens if token not in removable]
        if not filtered:
            return obj_text

        cleaned = " ".join(filtered)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" \t\n\r.,，、")
        return cleaned or obj_text

    def _assign_conditions_to_predicates(self, sentence, conditions: list[Condition], predicate_words: list) -> dict[int, list[Condition]]:
        predicate_ids = [word.id for word in predicate_words if word is not None]
        if not predicate_ids:
            return {}

        assigned: dict[int, list[Condition]] = {pid: [] for pid in predicate_ids}
        for condition in conditions:
            if condition.label in {"POLARITY"}:
                for pid in predicate_ids:
                    assigned[pid].append(condition)
                continue

            anchor_id = self._find_condition_anchor_id(sentence, condition)
            if anchor_id is None:
                for pid in predicate_ids:
                    assigned[pid].append(condition)
                continue

            later_or_equal = [pid for pid in predicate_ids if pid >= anchor_id]
            if later_or_equal:
                target_pid = min(later_or_equal)
            else:
                target_pid = min(predicate_ids, key=lambda pid: abs(pid - anchor_id))
            assigned[target_pid].append(condition)

        return assigned

    def _find_condition_anchor_id(self, sentence, condition: Condition) -> Optional[int]:
        text = (condition.text or condition.value or "").strip()
        if not text:
            return None

        normalized = re.sub(r"\s+", "", text)
        for word in sentence.words:
            word_text = word.text.strip()
            if not word_text:
                continue
            compact_word = re.sub(r"\s+", "", word_text)
            if word_text == text or compact_word == normalized:
                return word.id
            if compact_word and (compact_word in normalized or normalized in compact_word):
                return word.id

        return None

    def _clean_multilingual_referential_object_text(self, obj_text: str, sentence_text: str, lang: str) -> str:
        referential_tokens = {
            "en": {"it", "this", "that", "the content", "this content", "that content", "content"},
            "ja": {"内容", "その内容", "これ", "それ"},
            "zh": {"内容", "这个内容", "那个内容", "该内容", "这个", "那个"},
            "fr": {"contenu", "ce contenu", "ceci", "cela", "ça"},
            "de": {"inhalt", "dieser inhalt", "dies", "das", "es"},
            "ar": {"المحتوى", "هذا المحتوى", "ذلك المحتوى", "هذا", "ذلك"},
        }

        preferred_message_nouns = {
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

        refs = referential_tokens.get(lang)
        nouns = preferred_message_nouns.get(lang)
        if not refs or not nouns:
            return obj_text

        obj = obj_text.strip()
        if not obj:
            return obj_text

        sentence_compact = re.sub(r"\s+", " ", sentence_text).strip()

        if lang in {"en", "fr", "de"}:
            lowered_obj = obj.lower()
            lowered_sentence = sentence_compact.lower()

            has_reference = any(token in lowered_obj for token in refs)
            if not has_reference:
                return obj_text

            positions = [(lowered_sentence.find(noun.lower()), noun) for noun in nouns if noun.lower() in lowered_sentence]
        else:
            compact_obj = re.sub(r"\s+", "", obj)
            compact_sentence = re.sub(r"\s+", "", sentence_compact)

            has_reference = any(token in obj or token in compact_obj for token in refs)
            if not has_reference:
                return obj_text

            positions = [(compact_sentence.find(noun.replace(" ", "")), noun) for noun in nouns if noun.replace(" ", "") in compact_sentence]

        positions = [item for item in positions if item[0] >= 0]
        if not positions:
            return obj_text
        positions.sort(key=lambda item: item[0])
        return positions[0][1]

    def _split_object_items(self, obj_text: Optional[str]) -> list[str]:
        if not obj_text:
            return []
        lang_separators = {
            "ko": ["및", "와", "과", "또는"],
            "en": ["and", "or"],
            "ja": ["と", "および", "または"],
            "zh": ["和", "及", "以及", "或", "或者"],
            "fr": ["et", "ou"],
            "de": ["und", "oder"],
            "ar": ["و", "أو"],
        }
        separators = lang_separators.get(self.lang, []) + ["/", "／", "·", "・", "&", ",", "，", "、", "|"]
        token_pattern = "|".join(sorted((re.escape(token) for token in separators), key=len, reverse=True))
        parts = re.split(rf"\s*(?:{token_pattern})\s*", obj_text)
        items = [part.strip(" \t\n\r.,，、") for part in parts if part.strip(" \t\n\r.,，、")]

        if self.normalize_object_items:
            normalized = []
            for item in items:
                normalized_item = self._normalize_object_item(item)
                if normalized_item:
                    normalized.append(normalized_item)
            items = normalized

        return items if len(items) > 1 else ([] if not obj_text else [obj_text])

    def _normalize_object_item(self, item: str) -> str:
        value = item.strip()
        if not value:
            return ""

        if self.lang == "ko":
            value = re.sub(r"(을|를|은|는|이|가)$", "", value).strip()

        if self.lang in {"zh", "ja"}:
            value = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", value)

        return value

    def _compose_object_normalized(self, object_items: list[str]) -> Optional[str]:
        if not object_items:
            return None
        if len(object_items) == 1:
            return object_items[0]

        if self.object_join_token is not None:
            return self.object_join_token.join(object_items)

        configured_tokens = self.config.get("object_join_token_by_lang")
        if isinstance(configured_tokens, dict):
            lang_token = configured_tokens.get(self.lang)
            if isinstance(lang_token, str):
                return lang_token.join(object_items)

        configured_global_token = self.config.get("object_join_token")
        if isinstance(configured_global_token, str):
            return configured_global_token.join(object_items)

        join_token = {
            "ko": " / ",
            "en": " / ",
            "fr": " / ",
            "de": " / ",
            "ja": "・",
            "zh": "、",
            "ar": " / ",
        }.get(self.lang, " / ")

        return join_token.join(object_items)

    def _collect_recipients_from_conditions(self, conditions: list[Condition]) -> list[str]:
        recipients: list[str] = []
        seen = set()
        for condition in conditions:
            if condition.label != "RECIPIENT":
                continue
            value = (condition.value or condition.text or "").strip()
            if not value or value in seen:
                continue
            seen.add(value)
            recipients.append(value)
        return recipients

    def _extract_conditions(self, sentence) -> list[Condition]:
        conditions: list[Condition] = []
        candidates = collect_condition_candidates(sentence)

        for candidate in candidates:
            label, value, confidence = rule_label_condition(candidate, sentence, lang=self.lang)
            source = "rule"

            if label == "UNKNOWN" or confidence < 0.55:
                decision = self.llm_labeler.classify(
                    sentence_text=sentence.text,
                    candidate_text=candidate.text,
                    evidence=candidate.features,
                )
                if decision and decision.label:
                    label = decision.label
                    value = decision.value or candidate.text
                    confidence = max(confidence, decision.confidence)
                    source = "llm"

            if label == "UNKNOWN" and source == "rule":
                continue

            if (
                label == "RECIPIENT"
                and self.lang == "ko"
                and "," in candidate.text
                and re.search(r"(에게|한테|께)\s*$", candidate.text)
            ):
                continue

            normalized_time = normalize_time_expression(
                candidate.text,
                lang=self.lang,
                reference_dt=self.reference_datetime,
            )

            if normalized_time:
                label = "TIME"
                confidence = max(confidence, 0.9)

            if normalized_time and len(normalized_time) > 1:
                for normalized in normalized_time:
                    conditions.append(
                        Condition(
                            label="TIME",
                            text=normalized.expression,
                            value=normalized.expression,
                            normalized=normalized.to_dict(),
                            confidence=float(min(max(confidence, 0.0), 1.0)),
                            source=source,
                        )
                    )
            else:
                normalized_dict = normalized_time[0].to_dict() if normalized_time else None
                normalized_value = normalized_time[0].expression if normalized_time else value
                conditions.append(
                    Condition(
                        label=label,
                        text=normalized_value if normalized_time else candidate.text,
                        value=normalized_value,
                        normalized=normalized_dict,
                        confidence=float(min(max(confidence, 0.0), 1.0)),
                        source=source,
                    )
                )

        srl_arguments = self.srl_provider.predict(sentence.text)
        for arg in srl_arguments:
            mapped_label = map_srl_role_to_label(arg.role)
            if mapped_label == "UNKNOWN":
                continue
            if any(existing.text == arg.text and existing.label == mapped_label for existing in conditions):
                continue
            conditions.append(
                Condition(
                    label=mapped_label,
                    text=arg.text,
                    value=arg.text,
                    confidence=float(min(max(arg.score, 0.0), 1.0)),
                    source="srl",
                )
            )

        sentence_level_time = normalize_time_expression(
            sentence.text,
            lang=self.lang,
            reference_dt=self.reference_datetime,
        )
        for normalized in sentence_level_time:
            if any(
                cond.label == "TIME"
                and cond.normalized
                and cond.normalized.get("kind") == normalized.kind
                and cond.normalized.get("start") == normalized.start
                and cond.normalized.get("end") == normalized.end
                and cond.normalized.get("point") == normalized.point
                for cond in conditions
            ):
                continue
            conditions.append(
                Condition(
                    label="TIME",
                    text=normalized.expression,
                    value=normalized.expression,
                    normalized=normalized.to_dict(),
                    confidence=0.9,
                    source="rule",
                )
            )

        recipient_names = extract_recipients_from_text(sentence.text, lang=self.lang)
        for recipient in recipient_names:
            if not self._is_allowed_recipient(recipient):
                continue
            if any(
                cond.label == "RECIPIENT"
                and cond.value
                and (cond.value == recipient or recipient in cond.value)
                for cond in conditions
            ):
                continue
            conditions.append(
                Condition(
                    label="RECIPIENT",
                    text=recipient,
                    value=recipient,
                    normalized=None,
                    confidence=0.85,
                    source="rule",
                )
            )

        if self.recipient_lexicon is not None:
            conditions = [
                cond
                for cond in conditions
                if cond.label != "RECIPIENT" or (cond.value is not None and self._is_allowed_recipient(cond.value))
            ]

        sentence_polarity = detect_sentence_polarity(sentence.text, lang=self.lang)
        if sentence_polarity == "NEG":
            if not any(cond.label == "POLARITY" for cond in conditions):
                conditions.append(
                    Condition(
                        label="POLARITY",
                        text=sentence.text,
                        value=sentence_polarity,
                        confidence=0.75,
                        source="rule",
                    )
                )

        if self.lang == "ko" and not any(cond.label == "METHOD" for cond in conditions):
            reference_match = re.search(r"(참조해서|참조해|참조|참고해서|참고해|참고)", sentence.text)
            if reference_match:
                phrase = reference_match.group(1)
                conditions.append(
                    Condition(
                        label="METHOD",
                        text=phrase,
                        value=phrase,
                        confidence=0.82,
                        source="rule",
                    )
                )

        if self.lang == "ko":
            for match in re.finditer(r"\b(\d{1,2})일\b", sentence.text):
                token = match.group(0)
                if any(cond.label == "TIME" and cond.text == token for cond in conditions):
                    continue
                conditions.append(
                    Condition(
                        label="TIME",
                        text=token,
                        value=token,
                        confidence=0.75,
                        source="rule",
                    )
                )

            for token in ["이날", "당일"]:
                if token in sentence.text and not any(cond.label == "TIME" and cond.text == token for cond in conditions):
                    conditions.append(
                        Condition(
                            label="TIME",
                            text=token,
                            value=token,
                            confidence=0.78,
                            source="rule",
                        )
                    )

        if self.lang == "ko":
            for match in re.finditer(r"(\d+[여]?[\s]*명)(?:이|가|은|는|을|를)?", sentence.text):
                token = re.sub(r"\s+", "", match.group(1))
                if any(cond.label == "VALUE" and cond.value == token for cond in conditions):
                    continue
                conditions.append(
                    Condition(
                        label="VALUE",
                        text=token,
                        value=token,
                        confidence=0.78,
                        source="rule",
                    )
                )

            for match in re.finditer(r"수십\s*명", sentence.text):
                token = re.sub(r"\s+", "", match.group(0))
                if any(cond.label == "VALUE" and cond.value == token for cond in conditions):
                    continue
                conditions.append(
                    Condition(
                        label="VALUE",
                        text=token,
                        value=token,
                        confidence=0.78,
                        source="rule",
                    )
                )

            for match in re.finditer(r"(\d+[여]?\s*척)(?:이|가|은|는|을|를)?", sentence.text):
                token = re.sub(r"\s+", "", match.group(1))
                if any(cond.label == "VALUE" and cond.value == token for cond in conditions):
                    continue
                conditions.append(
                    Condition(
                        label="VALUE",
                        text=token,
                        value=token,
                        confidence=0.78,
                        source="rule",
                    )
                )

        return conditions