from __future__ import annotations


REFERENCE_DATETIME = "2026-03-04T12:00:00+09:00"


GOLDEN_PREDICATE_SAMPLES = [
    {
        "lang": "ko",
        "text": "오늘 수신한 쪽지 알려주고 그내용을 참조해서 내일 보내야 할 쪽지 작성해줘",
        "expected_predicates": ["알려주고", "참조해서", "작성해줘"],
        "expected_objects": ["쪽지", "쪽지", "쪽지"],
    },
    {
        "lang": "en",
        "text": "Show messages received today, reference that content, and draft a message to send tomorrow.",
        "expected_predicates": ["Show", "reference", "draft"],
        "expected_objects": ["messages", "messages", "a message"],
    },
    {
        "lang": "ja",
        "text": "今日受信したメッセージを表示して、その内容を参照して、明日送るメッセージを作成して。",
        "expected_predicates": ["表示", "参照", "作成"],
        "expected_objects": ["メッセージ", "メッセージ", "メッセージ"],
    },
    {
        "lang": "zh",
        "text": "显示今天收到的消息，参考那个内容，并编写明天要发送的消息。",
        "expected_predicates": ["显示", "参考", "编写"],
        "expected_objects": ["消息", "消息", "消息"],
    },
    {
        "lang": "fr",
        "text": "Montre les messages reçus aujourd'hui, référence ce contenu et rédige un message à envoyer demain.",
        "expected_predicates": ["Montre", "référence", "rédige"],
        "expected_objects": ["les messages", "les messages", "un message"],
    },
    {
        "lang": "de",
        "text": "Zeige heute empfangene Nachrichten, nutze diesen Inhalt und schreibe eine Nachricht für morgen.",
        "expected_predicates": ["Zeige", "nutze", "schreibe"],
        "expected_objects": ["empfangene Nachrichten", "nachrichten", "eine Nachricht"],
    },
    {
        "lang": "ar",
        "text": "اعرض الرسائل المستلمة اليوم، وارجع إلى هذا المحتوى، واكتب رسالة لإرسالها غدًا.",
        "expected_predicates": ["اعرض", "أرجع", "أكتب"],
        "expected_objects": ["الرسائل", "رسائل", "رسالة"],
    },
]
