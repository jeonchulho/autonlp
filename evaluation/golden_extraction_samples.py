from __future__ import annotations


REFERENCE_DATETIME = "2026-03-04T12:00:00+09:00"


GOLDEN_EXTRACTION_SAMPLES = [
    {
        "lang": "ko",
        "text": "어제,오늘 전철호,이선정,영업팀에게 보낸 쪽지 알려주고 그내용을 참조해서 내일 보낼 쪽지 작성해줘",
        "expected": [
            {
                "predicate": "알려주고",
                "subject": None,
                "object": "쪽지",
                "condition_labels": ["TIME", "RECIPIENT"],
            },
            {
                "predicate": "참조해서",
                "subject": None,
                "object": "쪽지",
                "condition_labels": ["METHOD"],
            },
            {
                "predicate": "작성해줘",
                "subject": None,
                "object": "쪽지",
                "condition_labels": ["TIME"],
            },
        ],
    },
    {
        "lang": "en",
        "text": "Show messages received today, reference that content, and draft a message to send tomorrow.",
        "expected": [
            {"predicate": "Show", "subject": None, "object": "messages", "condition_labels": []},
            {"predicate": "reference", "subject": None, "object": "messages", "condition_labels": ["TIME"]},
            {"predicate": "draft", "subject": None, "object": "a message", "condition_labels": ["RECIPIENT"]},
        ],
    },
    {
        "lang": "ja",
        "text": "今日受信したメッセージを表示して、その内容を参照して、明日送るメッセージを作成して。",
        "expected": [
            {"predicate": "表示", "subject": None, "object": "メッセージ", "condition_labels": ["TIME"]},
            {"predicate": "参照", "subject": None, "object": "メッセージ", "condition_labels": []},
            {"predicate": "作成", "subject": None, "object": "メッセージ", "condition_labels": ["TIME"]},
        ],
    },
    {
        "lang": "zh",
        "text": "显示今天收到的消息，参考那个内容，并编写明天要发送的消息。",
        "expected": [
            {"predicate": "显示", "subject": "消息", "object": "消息", "condition_labels": []},
            {"predicate": "参考", "subject": "消息", "object": "消息", "condition_labels": ["LOC", "TIME"]},
            {"predicate": "编写", "subject": "消息", "object": "消息", "condition_labels": []},
        ],
    },
    {
        "lang": "fr",
        "text": "Montre les messages reçus aujourd'hui, référence ce contenu et rédige un message à envoyer demain.",
        "expected": [
            {"predicate": "Montre", "subject": None, "object": "les messages", "condition_labels": []},
            {"predicate": "référence", "subject": None, "object": "les messages", "condition_labels": ["TIME"]},
            {"predicate": "rédige", "subject": None, "object": "un message", "condition_labels": ["RECIPIENT", "TIME"]},
        ],
    },
    {
        "lang": "de",
        "text": "Zeige heute empfangene Nachrichten, nutze diesen Inhalt und schreibe eine Nachricht für morgen.",
        "expected": [
            {"predicate": "Zeige", "subject": None, "object": "empfangene Nachrichten", "condition_labels": []},
            {"predicate": "nutze", "subject": None, "object": "nachrichten", "condition_labels": ["TIME"]},
            {"predicate": "schreibe", "subject": None, "object": "eine Nachricht", "condition_labels": ["RECIPIENT"]},
        ],
    },
    {
        "lang": "ar",
        "text": "اعرض الرسائل المستلمة اليوم، وارجع إلى هذا المحتوى، واكتب رسالة لإرسالها غدًا.",
        "expected": [
            {"predicate": "اعرض", "subject": None, "object": "الرسائل", "condition_labels": ["POLARITY"]},
            {"predicate": "أرجع", "subject": None, "object": "رسائل", "condition_labels": ["POLARITY", "TIME"]},
            {"predicate": "أكتب", "subject": None, "object": "رسالة", "condition_labels": ["POLARITY", "RECIPIENT", "TIME"]},
        ],
    },
    {
        "lang": "en",
        "text": "The ministry said today a destroyer fired warning shots.",
        "expected": [
            {"predicate": "said", "subject": "The ministry", "object": "ministry", "condition_labels": []},
            {"predicate": "fired", "subject": "a destroyer", "object": "warning shots", "condition_labels": ["TIME"]},
        ],
    },
    {
        "lang": "ja",
        "text": "国防省は今日、駆逐艦が警告射撃を行ったと述べた。",
        "expected": [
            {"predicate": "行っ", "subject": "駆逐 艦", "object": "警告 射撃", "condition_labels": ["TIME"]},
            {"predicate": "述べ", "subject": "国防 省", "object": None, "condition_labels": []},
        ],
    },
    {
        "lang": "zh",
        "text": "国防部称今天驱逐舰进行了警告射击。",
        "expected": [
            {"predicate": "称", "subject": "国防 部", "object": "今天", "condition_labels": []},
            {"predicate": "进行", "subject": "今天 驱逐 舰", "object": "射击", "condition_labels": ["TIME"]},
        ],
    },
    {
        "lang": "fr",
        "text": "Le ministère a déclaré qu'aujourd'hui un destroyer a effectué des tirs d'avertissement.",
        "expected": [
            {"predicate": "déclaré", "subject": "Le ministère", "object": "ministère", "condition_labels": ["TIME"]},
            {"predicate": "effectué", "subject": "un destroyer", "object": "des tirs", "condition_labels": []},
        ],
    },
    {
        "lang": "de",
        "text": "Das Ministerium erklärte, dass heute ein Zerstörer Warnschüsse abgegeben hat.",
        "expected": [
            {"predicate": "erklärte", "subject": "Das Ministerium", "object": "Warnschüsse", "condition_labels": []},
            {"predicate": "abgegeben", "subject": "ein Zerstörer", "object": "Warnschüsse", "condition_labels": ["TIME"]},
        ],
    },
    {
        "lang": "ar",
        "text": "أعلنت الوزارة أن المدمرة أطلقت اليوم طلقات تحذيرية.",
        "expected": [
            {"predicate": "أعلنت", "subject": "الوزارة", "object": None, "condition_labels": ["POLARITY"]},
            {"predicate": "أطلقت", "subject": "المدمرة", "object": "طلقات", "condition_labels": ["POLARITY", "TIME"]},
        ],
    },
    {
        "lang": "ko",
        "text": "해군은 어제 초계기가 조난 신호를 포착했다고 발표했다.",
        "expected": [
            {"predicate": "포착했다", "subject": "초계기", "object": "조난 신호를", "condition_labels": ["TIME"]},
            {"predicate": "발표했다", "subject": "초계기", "object": None, "condition_labels": []},
        ],
    },
    {
        "lang": "en",
        "text": "The navy announced yesterday a patrol aircraft detected a distress signal.",
        "expected": [
            {"predicate": "announced", "subject": "The navy", "object": "patrol", "condition_labels": []},
            {"predicate": "detected", "subject": "a patrol aircraft", "object": "a distress signal", "condition_labels": ["TIME"]},
        ],
    },
    {
        "lang": "ja",
        "text": "海軍は昨日、哨戒機が遭難信号を探知したと発表した。",
        "expected": [
            {"predicate": "探知", "subject": "哨戒 機", "object": "遭難 信号", "condition_labels": ["TIME"]},
            {"predicate": "発表", "subject": "海軍", "object": None, "condition_labels": []},
        ],
    },
    {
        "lang": "zh",
        "text": "海军表示昨天巡逻机探测到了遇险信号。",
        "expected": [
            {"predicate": "表示", "subject": "海军", "object": "昨天", "condition_labels": []},
            {"predicate": "探测", "subject": "昨天 巡逻 机", "object": "信号", "condition_labels": ["TIME"]},
        ],
    },
    {
        "lang": "fr",
        "text": "La marine a annoncé qu'hier un avion de patrouille a détecté un signal de détresse.",
        "expected": [
            {"predicate": "annoncé", "subject": "La marine", "object": "patrouille", "condition_labels": ["DURATION", "POLARITY"]},
            {"predicate": "détecté", "subject": "un avion", "object": "un signal", "condition_labels": ["DURATION", "POLARITY", "TIME"]},
        ],
    },
    {
        "lang": "de",
        "text": "Die Marine gab bekannt, dass gestern ein Patrouillenflugzeug ein Notsignal erkannt hat.",
        "expected": [
            {"predicate": "gab", "subject": "Die Marine", "object": "Marine", "condition_labels": []},
            {"predicate": "bekannt", "subject": "Marine", "object": "ein Notsignal", "condition_labels": []},
            {"predicate": "erkannt", "subject": "ein Patrouillenflugzeug", "object": "ein Notsignal", "condition_labels": ["TIME"]},
        ],
    },
    {
        "lang": "ar",
        "text": "أعلنت البحرية أن طائرة دورية رصدت أمس إشارة استغاثة.",
        "expected": [
            {"predicate": "أعلنت", "subject": "البحرية", "object": None, "condition_labels": ["POLARITY"]},
            {"predicate": "رصدت", "subject": "طائرة", "object": "إشارة", "condition_labels": ["POLARITY", "TIME"]},
        ],
    },
    {
        "lang": "ko",
        "text": "피트 헤그세스 미 국방장관이 4일 미국 잠수함이 어뢰를 발사해 이란 군함을 격침시켰다고 밝혔다.",
        "expected": [
            {"predicate": "발사해", "subject": "미국 잠수함", "object": "어뢰를", "condition_labels": ["TIME"]},
            {"predicate": "격침시켰다", "subject": "잠수함", "object": "이란 군함을", "condition_labels": []},
            {"predicate": "밝혔다", "subject": "국방장관", "object": None, "condition_labels": []},
        ],
    },
]
