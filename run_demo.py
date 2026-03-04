from __future__ import annotations

import json
from pathlib import Path
import sys
from datetime import datetime

from autonlp import ConditionExtractorPipeline
from autonlp.config import load_config_file


def main() -> None:
    args = sys.argv[1:]
    lang = "ko"
    reference_datetime = None
    recipient_lexicon = None
    normalize_object_items = True
    object_join_token = None
    config = {}
    if "--lang" in args:
        idx = args.index("--lang")
        if idx + 1 < len(args):
            lang = args[idx + 1]
            args = args[:idx] + args[idx + 2 :]

    if "--ref-datetime" in args:
        idx = args.index("--ref-datetime")
        if idx + 1 < len(args):
            reference_datetime = datetime.fromisoformat(args[idx + 1])
            args = args[:idx] + args[idx + 2 :]

    if "--recipient-lexicon-file" in args:
        idx = args.index("--recipient-lexicon-file")
        if idx + 1 < len(args):
            lexicon_file = args[idx + 1]
            with open(lexicon_file, "r", encoding="utf-8") as f:
                recipient_lexicon = [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]
            args = args[:idx] + args[idx + 2 :]

    if "--disable-object-normalization" in args:
        normalize_object_items = False
        args = [arg for arg in args if arg != "--disable-object-normalization"]

    if "--object-join-token" in args:
        idx = args.index("--object-join-token")
        if idx + 1 < len(args):
            object_join_token = args[idx + 1]
            args = args[:idx] + args[idx + 2 :]

    if "--config-file" in args:
        idx = args.index("--config-file")
        if idx + 1 < len(args):
            config = load_config_file(args[idx + 1])
            args = args[:idx] + args[idx + 2 :]
    elif Path("autonlp.config.json").exists():
        config = load_config_file("autonlp.config.json")

    if args:
        text = " ".join(args)
    else:
        defaults = {
            "ko": "내일 서울에서 고객에게 이메일을 보내기 위해 자동화 도구로 보고서를 3건 전송해.",
            "en": "Send 3 reports to the customer in Seoul tomorrow using an automation tool.",
            "ja": "明日、ソウルで顧客に3件のレポートを自動化ツールで送信してください。",
            "zh": "请在明天于首尔使用自动化工具向客户发送3份报告。",
            "fr": "Envoyez 3 rapports au client à Séoul demain avec un outil d'automatisation.",
            "de": "Sende morgen in Seoul 3 Berichte mit einem Automatisierungstool an den Kunden.",
            "ar": "أرسل 3 تقارير إلى العميل في سيول غدًا باستخدام أداة أتمتة.",
        }
        text = defaults.get(lang.lower(), defaults["en"])

    pipeline = ConditionExtractorPipeline(
        lang=lang,
        reference_datetime=reference_datetime,
        recipient_lexicon=recipient_lexicon,
        normalize_object_items=normalize_object_items,
        object_join_token=object_join_token,
        config=config,
    )
    result = pipeline.extract(text)
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()