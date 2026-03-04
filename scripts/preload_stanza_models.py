from __future__ import annotations

import argparse

import stanza


def _processors_for_lang(lang: str) -> str:
    if lang == "ko":
        return "tokenize,pos,lemma,depparse"
    return "tokenize,pos,lemma,depparse,ner"


def main() -> None:
    parser = argparse.ArgumentParser(description="Pre-download stanza models for selected languages")
    parser.add_argument(
        "--langs",
        default="ko,en,ja,zh,fr,de,ar",
        help="Comma-separated language list (default: ko,en,ja,zh,fr,de,ar)",
    )
    args = parser.parse_args()

    langs = [lang.strip().lower() for lang in args.langs.split(",") if lang.strip()]
    for lang in langs:
        processors = _processors_for_lang(lang)
        print(f"[download] lang={lang} processors={processors}")
        try:
            stanza.download(lang=lang, processors=processors, verbose=True)
        except Exception as exc:
            print(f"[warn] failed to download preferred processors for {lang}: {exc}")
            fallback = "tokenize,pos,lemma,depparse"
            print(f"[fallback] lang={lang} processors={fallback}")
            stanza.download(lang=lang, processors=fallback, verbose=True)

    print("done")


if __name__ == "__main__":
    main()