from __future__ import annotations

import re
from typing import Iterable, Optional

import stanza

from .patterns import (
    AUXILIARIES_BY_LANG,
    PREFERRED_MESSAGE_NOUNS_BY_LANG,
    PREDICATE_ACL_END_REGEX_BY_LANG,
    PREDICATE_CONJ_END_REGEX_BY_LANG,
    PREDICATE_CONNECTOR_STOPWORDS_BY_LANG,
    PREDICATE_EVENT_LIKE_REGEX_BY_LANG,
    PREDICATE_SKIP_NEXT_AUX_TOKENS_BY_LANG,
    PREDICATE_SUPPRESS_TOKENS_BASE_BY_LANG,
    PREDICATE_SUPPRESS_TOKENS_EXTRA_BY_LANG,
    REFERENCE_OBJECT_TOKENS_BY_LANG,
    REFERENTIAL_TOKENS_BY_LANG,
    SUBJECT_NULL_TOKENS_BY_LANG,
    SUBJECT_TIME_STOPWORDS_BY_LANG,
    TIME_LIKE_OBJECT_TOKENS_BY_LANG,
    get_connectors,
    get_pattern,
)
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
                        get_pattern(self.lang, "ko_day_suffix").search(word.text)
                        or word.text in SUBJECT_TIME_STOPWORDS_BY_LANG["ko"]
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
            and get_pattern(self.lang, "ko_subject_particle").search(word.text)
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
        try:
            return bool(get_pattern(self.lang, "report_verb").search(value))
        except KeyError:
            return False

    def _clean_subject_text(self, subject_text: Optional[str]) -> Optional[str]:
        if subject_text is None:
            return None
        value = subject_text.strip()
        if not value:
            return None

        value = get_pattern(self.lang, "quote_edges").sub("", value)
        value = get_pattern(self.lang, "quote_all").sub("", value)

        if self.lang == "ko":
            value = get_pattern(self.lang, "ko_subject_particle").sub("", value).strip()
            if get_pattern(self.lang, "ko_day_token_exact").search(value):
                return None

        subject_null_tokens = SUBJECT_NULL_TOKENS_BY_LANG.get(self.lang, set())
        null_lookup = value.lower() if self.lang in {"en", "fr", "de"} else value
        if null_lookup in subject_null_tokens:
            return None

        stopwords = SUBJECT_TIME_STOPWORDS_BY_LANG.get(self.lang, set())
        lookup_value = value.lower() if self.lang in {"en", "fr", "de"} else value
        if lookup_value in stopwords:
            return None

        return value or None

    def _normalize_predicate_text(self, predicate: Optional[str]) -> Optional[str]:
        if predicate is None:
            return None
        normalized = predicate.strip()
        normalized = get_pattern(self.lang, "quote_edges").sub("", normalized)
        normalized = get_pattern(self.lang, "quote_all").sub("", normalized)
        normalized = get_pattern(self.lang, "trail_punct").sub("", normalized)
        if self.lang == "ko":
            normalized = get_pattern(self.lang, "ko_predicate_dago").sub("다", normalized)
        return normalized or predicate

    def _extract_predicate_words(self, sentence) -> list:
        words = sentence.words
        by_id = {word.id: word for word in words}
        predicate_conj_pattern = PREDICATE_CONJ_END_REGEX_BY_LANG.get(self.lang)
        predicate_acl_pattern = PREDICATE_ACL_END_REGEX_BY_LANG.get(self.lang)
        connector_stopwords = PREDICATE_CONNECTOR_STOPWORDS_BY_LANG.get(self.lang, set())
        skip_next_aux_tokens = PREDICATE_SKIP_NEXT_AUX_TOKENS_BY_LANG.get(self.lang, set())
        connector_stopwords_norm = {
            token.lower() if self.lang in {"en", "fr", "de"} else token
            for token in connector_stopwords
        }
        candidates = []
        for word in words:
            if word.upos in {"VERB", "ADJ"} and word.deprel in {"root", "conj", "advcl", "xcomp", "ccomp"}:
                candidates.append(word)
                continue

            if word.upos == "AUX" and word.deprel == "root":
                candidates.append(word)
                continue

            if self.lang == "ar" and word.upos == "X" and word.deprel in {"root", "conj"} and get_pattern(self.lang, "arabic_script").search(word.text):
                candidates.append(word)
                continue

            if self.lang == "fr" and word.upos == "NOUN" and word.deprel in {"appos", "conj"}:
                prev_word = by_id.get(word.id - 1)
                next_word = by_id.get(word.id + 1)
                if prev_word is not None and prev_word.upos == "PUNCT" and next_word is not None and next_word.upos in {"DET", "PRON", "NOUN", "PROPN"}:
                    candidates.append(word)
                    continue

            if (
                word.upos in {"SCONJ", "CCONJ"}
                and word.deprel in {"root", "conj", "advcl", "ccomp"}
                and predicate_conj_pattern is not None
                and re.search(predicate_conj_pattern, word.text)
                and ((word.text or "").lower() if self.lang in {"en", "fr", "de"} else (word.text or "")) not in connector_stopwords_norm
            ):
                candidates.append(word)

            if (
                word.upos == "VERB"
                and word.deprel == "acl"
                and predicate_acl_pattern is not None
                and re.search(predicate_acl_pattern, word.text)
            ):
                candidates.append(word)

        if candidates and skip_next_aux_tokens:
            filtered_candidates = []
            for word in candidates:
                next_word = by_id.get(word.id + 1)
                next_text = (next_word.text or "") if next_word is not None else ""
                token_key = next_text.lower() if self.lang in {"en", "fr", "de"} else next_text
                if (
                    word.upos == "VERB"
                    and next_word is not None
                    and next_word.upos == "AUX"
                    and token_key in skip_next_aux_tokens
                ):
                    continue
                filtered_candidates.append(word)
            candidates = filtered_candidates

        if self.lang == "ko" and candidates:
            filtered_candidates = []
            for word in candidates:
                next_word = by_id.get(word.id + 1)
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

            candidates = filtered_candidates

        if self.lang in {"en", "fr", "de"} and candidates:
            auxiliaries = set()
            for language in {"en", "fr", "de"}:
                auxiliaries.update(AUXILIARIES_BY_LANG.get(language, set()))
            filtered_candidates = []
            for word in candidates:
                lemma = (word.lemma or "").lower()
                if word.upos == "AUX" and lemma in auxiliaries:
                    continue
                filtered_candidates.append(word)
            candidates = filtered_candidates

        if candidates:
            event_pattern = PREDICATE_EVENT_LIKE_REGEX_BY_LANG.get(self.lang)
            event_like_exists = bool(event_pattern) and any(
                re.search(
                    event_pattern,
                    (word.text or "").lower() if self.lang in {"en", "fr", "de"} else (word.text or ""),
                )
                for word in candidates
            )
            suppress_key = f"suppress_report_verbs_{self.lang}"
            suppress_with_extra = bool(self.config.get(suppress_key, False)) if isinstance(self.config, dict) else False
            always_apply_base = self.lang == "ko"
            if event_like_exists and (always_apply_base or suppress_with_extra):
                base_tokens = PREDICATE_SUPPRESS_TOKENS_BASE_BY_LANG.get(self.lang, set())
                extra_tokens = PREDICATE_SUPPRESS_TOKENS_EXTRA_BY_LANG.get(self.lang, set()) if suppress_with_extra else set()
                suppressible_tokens = set(base_tokens) | set(extra_tokens)
                if self.lang in {"en", "fr", "de"}:
                    suppressible_tokens = {token.lower() for token in suppressible_tokens}
                    candidates = [word for word in candidates if (word.text or "").lower() not in suppressible_tokens]
                else:
                    candidates = [word for word in candidates if (word.text or "") not in suppressible_tokens]

        if candidates and isinstance(self.config, dict):
            suppress_key = f"suppress_report_verbs_{self.lang}"
            if bool(self.config.get(suppress_key, False)):
                non_report_exists = any(not self._is_report_verb(word.text or "") for word in candidates)
                if non_report_exists:
                    candidates = [word for word in candidates if not self._is_report_verb(word.text or "")]

        if not candidates:
            root = next((word for word in words if word.deprel == "root" and word.upos in {"VERB", "AUX", "ADJ"}), None)
            if root is None and self.lang == "ar":
                root = next((word for word in words if word.deprel == "root" and get_pattern(self.lang, "arabic_script").search(word.text or "")), None)
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
            match = re.match(r"(.+?)(?:이|가|은|는|께서)$", subject)
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
                and not (self.lang == "ko" and get_pattern(self.lang, "ko_subject_particle").search(word.text))
            }
            if obj_modifiers:
                start_id = min(obj_modifiers)

            between_words = [word for word in words if start_id <= word.id < predicate_word.id]
            connectors = get_connectors(self.lang)
            has_connector = any(word.text in connectors for word in between_words)
            has_next_noun = any(word.upos == "NOUN" and word.id > start_id for word in between_words)
            if has_connector and has_next_noun:
                obj = " ".join(word.text for word in between_words).strip()

        if obj and predicate_word and predicate_word.id < object_word.id:
            tail_words = [word for word in words if word.id >= object_word.id]
            connectors = get_connectors(self.lang)
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
                match = re.match(r"(.+?)(?:이|가|은|는|께서)$", word.text)
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
        cleaned = self._clean_korean_object_text(obj_text, sentence_text)
        if self.lang == "ko":
            return cleaned
        return self._clean_multilingual_referential_object_text(cleaned, sentence_text, self.lang)

    def _clean_korean_object_text(self, obj_text: str, sentence_text: str) -> str:
        tokens = [token for token in obj_text.split() if token]
        if not tokens:
            return obj_text

        referential_tokens = REFERENCE_OBJECT_TOKENS_BY_LANG.get(self.lang, set())
        collapsed = re.sub(r"\s+", "", obj_text)
        preferred_message_nouns = PREFERRED_MESSAGE_NOUNS_BY_LANG.get(self.lang, [])

        referential_tokens_compact = {re.sub(r"\s+", "", token) for token in referential_tokens}

        def _pick_preferred_message_noun(text: str) -> Optional[str]:
            positions = [(text.find(noun), noun) for noun in preferred_message_nouns if noun in text]
            positions = [item for item in positions if item[0] >= 0]
            if not positions:
                return None
            positions.sort(key=lambda item: item[0])
            return positions[0][1]

        if collapsed in referential_tokens_compact:
            preferred = _pick_preferred_message_noun(sentence_text)
            if preferred:
                return preferred

        if any(token in referential_tokens for token in tokens) or any(
            compact_token in collapsed for compact_token in referential_tokens_compact
        ):
            preferred = _pick_preferred_message_noun(sentence_text)
            if preferred:
                return preferred

        recipient_names = set(extract_recipients_from_text(sentence_text, lang=self.lang))
        time_like_tokens = TIME_LIKE_OBJECT_TOKENS_BY_LANG.get(self.lang, set())
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
        referential_tokens = REFERENTIAL_TOKENS_BY_LANG
        preferred_message_nouns = PREFERRED_MESSAGE_NOUNS_BY_LANG

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
        parts = get_pattern(self.lang, "object_split").split(obj_text)
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
            value = get_pattern(self.lang, "ko_object_particle").sub("", value).strip()

        if self.lang in {"zh", "ja"}:
            value = get_pattern(self.lang, "cjk_inner_space").sub("", value)

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

    def _extract_action_filter_tokens(self, text: str) -> list[str]:
        try:
            pattern = get_pattern(self.lang, "action_filter")
        except KeyError:
            return []

        tokens: list[str] = []
        seen = set()
        for match in pattern.finditer(text):
            token = match.group(1).strip()
            key = token.lower()
            if not token or key in seen:
                continue
            seen.add(key)
            tokens.append(token)
        return tokens

    def _dedupe_conditions(self, conditions: list[Condition]) -> list[Condition]:
        deduped: list[Condition] = []
        seen: set[tuple] = set()

        for condition in conditions:
            value = (condition.value or condition.text or "").strip()
            normalized = condition.normalized or {}
            normalized_key = (
                normalized.get("kind"),
                normalized.get("start"),
                normalized.get("end"),
                normalized.get("point"),
                normalized.get("expression"),
            )

            if condition.label == "TIME" and condition.normalized:
                key = (condition.label, normalized_key)
            else:
                key = (condition.label, value, normalized_key)

            if key in seen:
                continue
            seen.add(key)
            deduped.append(condition)

        return deduped

    def _prune_noisy_time_conditions(self, conditions: list[Condition]) -> list[Condition]:
        if self.lang not in {"en", "fr", "de"}:
            return conditions

        clause_markers = {
            "en": {"that"},
            "fr": {"que", "qu'"},
            "de": {"dass"},
        }.get(self.lang, set())

        pruned: list[Condition] = []
        for condition in conditions:
            if condition.label != "TIME":
                pruned.append(condition)
                continue

            text = (condition.text or "").strip().lower()
            tokens = [token for token in re.split(r"\s+", text) if token]
            if len(tokens) >= 3 and any(token in clause_markers for token in tokens):
                continue
            pruned.append(condition)

        return pruned

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

        if self.lang in {"zh", "ja"}:
            for token in SUBJECT_TIME_STOPWORDS_BY_LANG.get(self.lang, set()):
                if token in sentence.text and not any(cond.label == "TIME" and cond.text == token for cond in conditions):
                    conditions.append(
                        Condition(
                            label="TIME",
                            text=token,
                            value=token,
                            confidence=0.74,
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
            reference_match = get_pattern(self.lang, "ko_reference_method").search(sentence.text)
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
            for match in get_pattern(self.lang, "ko_numeric_day").finditer(sentence.text):
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

        for token in self._extract_action_filter_tokens(sentence.text):
            if any(cond.value and cond.value.lower() == token.lower() for cond in conditions):
                continue
            conditions.append(
                Condition(
                    label="ACTION_FILTER",
                    text=token,
                    value=token,
                    confidence=0.72,
                    source="rule",
                )
            )

        if self.lang == "ko":
            for match in get_pattern(self.lang, "ko_value_people").finditer(sentence.text):
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

            for match in get_pattern(self.lang, "ko_value_tens_people").finditer(sentence.text):
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

            for match in get_pattern(self.lang, "ko_value_ships").finditer(sentence.text):
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

        conditions = self._prune_noisy_time_conditions(conditions)
        return self._dedupe_conditions(conditions)