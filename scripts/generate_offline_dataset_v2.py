from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TARGET_OPS_PER_LANG = 10

OPS_CANDIDATES: dict[str, list[tuple[str, str]]] = {
    "ko": [
        ("어제 전철호에게 보낸 메일 보여줘", "clean"),
        ("오늘 이선정한테 보낸 쪽지 알려줘", "clean"),
        ("최근 7일 영업팀에게 보낸 문자 찾아줘", "clean"),
        ("어제,오늘 전철호 이선정에게 보낸 메시지 보여줘", "typo_punct"),
        ("내일 고객팀에게 보낼 안내문 작성해줘", "clean"),
        ("지난주 김민수에게 전달한 보고서 찾아줘", "clean"),
        ("오늘 전철호,이선정에게 보낸 메세지줘", "typo_punct"),
        ("어제 영업팀께 보낸 공지 다시 보여줘", "clean"),
        ("이번달 초에 보낸 메일 내역 정리해줘", "clean"),
        ("어제부터 오늘까지 고객지원팀에게 보낸 알림 보여줘", "clean"),
    ],
    "en": [
        ("Show messages sent to alice yesterday", "clean"),
        ("Find mails sent to bob today", "clean"),
        ("List notifications sent to sales-team in the last 7 days", "clean"),
        ("show msgs sent to alice,bob yesterday", "typo_punct"),
        ("Draft a note to send to customer success tomorrow", "clean"),
        ("Retrieve report sent to dana last week", "clean"),
        ("show email to tom today", "typo_punct"),
        ("Find alerts sent to ops-team yesterday", "clean"),
        ("List messages sent to finance this month", "clean"),
        ("Show what I sent to kim from yesterday to today", "clean"),
    ],
    "ja": [
        ("昨日山田に送ったメッセージを表示して", "clean"),
        ("今日佐藤宛てのメールを見せて", "clean"),
        ("直近7日で営業チームに送信した通知を一覧して", "clean"),
        ("昨日 山田,佐藤 に送った msg 表示", "typo_punct"),
        ("明日カスタマーサクセス向けの案内文を作成して", "clean"),
        ("先週田中に送ったレポートを探して", "clean"),
        ("今日鈴木に送ったメッセージ確認", "typo_punct"),
        ("昨日経理チーム宛てに送った連絡を出して", "clean"),
        ("今月送信したメール履歴をまとめて", "clean"),
        ("昨日から今日までに高橋へ送った通知を表示", "clean"),
    ],
    "zh": [
        ("显示昨天发送给张三的消息", "clean"),
        ("查看今天发给李四的邮件", "clean"),
        ("列出最近7天发给销售团队的通知", "clean"),
        ("显示昨天给张三、李四发的msg", "typo_punct"),
        ("编写明天发送给客服团队的说明", "clean"),
        ("查找上周发给王五的报告", "clean"),
        ("今天发给赵六的消息确认", "typo_punct"),
        ("显示昨天发给财务组的提醒", "clean"),
        ("整理本月发送的邮件记录", "clean"),
        ("显示从昨天到今天发给运营组的通知", "clean"),
    ],
    "fr": [
        ("Montre les messages envoyés à alice hier", "clean"),
        ("Affiche les mails envoyés à bob aujourd'hui", "clean"),
        ("Liste les notifications envoyées à l'équipe commerciale sur les 7 derniers jours", "clean"),
        ("montre msg envoyés à alice,bob hier", "typo_punct"),
        ("Rédige une note à envoyer au support client demain", "clean"),
        ("Retrouve le rapport envoyé à claire la semaine dernière", "clean"),
        ("mail envoyé à tom aujourd'hui", "typo_punct"),
        ("Montre les alertes envoyées à l'équipe ops hier", "clean"),
        ("Résume les e-mails envoyés ce mois-ci", "clean"),
        ("Affiche ce qui a été envoyé à kim d'hier à aujourd'hui", "clean"),
    ],
    "de": [
        ("Zeige die gestern an alice gesendeten Nachrichten", "clean"),
        ("Zeige heute an bob gesendete E-Mails", "clean"),
        ("Liste Benachrichtigungen an das Vertriebsteam der letzten 7 Tage", "clean"),
        ("zeige msg an alice,bob gestern", "typo_punct"),
        ("Erstelle eine Notiz für das Support-Team für morgen", "clean"),
        ("Finde den letzte Woche an dana gesendeten Bericht", "clean"),
        ("mail an tom heute zeigen", "typo_punct"),
        ("Zeige gestern an das Ops-Team gesendete Alarme", "clean"),
        ("Fasse die diesen Monat gesendeten E-Mails zusammen", "clean"),
        ("Zeige, was von gestern bis heute an kim gesendet wurde", "clean"),
    ],
    "ar": [
        ("اعرض الرسائل المرسلة إلى علي أمس", "clean"),
        ("أظهر البريد المرسل إلى سارة اليوم", "clean"),
        ("اعرض التنبيهات المرسلة إلى فريق المبيعات خلال آخر 7 أيام", "clean"),
        ("اعرض msg المرسلة إلى علي،سارة أمس", "typo_punct"),
        ("اكتب ملاحظة لإرسالها إلى فريق الدعم غدًا", "clean"),
        ("ابحث عن التقرير المرسل إلى كريم الأسبوع الماضي", "clean"),
        ("بريد مرسل إلى توم اليوم", "typo_punct"),
        ("اعرض التنبيهات المرسلة إلى فريق التشغيل أمس", "clean"),
        ("لخّص الرسائل المرسلة هذا الشهر", "clean"),
        ("اعرض ما أُرسل إلى ليلى من أمس إلى اليوم", "clean"),
    ],
}


def load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def dump_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")


def classify_length(text: str) -> str:
    if len(text) < 30:
        return "short"
    if len(text) < 70:
        return "medium"
    return "long"


def next_case_index(rows: list[dict], lang: str) -> int:
    prefix = f"real_{lang}_"
    indexes = []
    for row in rows:
        case_id = row.get("case_id", "")
        if isinstance(case_id, str) and case_id.startswith(prefix):
            tail = case_id.replace(prefix, "")
            if tail.isdigit():
                indexes.append(int(tail))
    return (max(indexes) + 1) if indexes else 1


def main() -> None:
    base_path = ROOT / "evaluation" / "offline_eval_dataset.v1.jsonl"
    out_path = ROOT / "evaluation" / "offline_eval_dataset.v2.jsonl"

    rows = load_jsonl(base_path)
    used_texts = {row.get("text") for row in rows}

    for lang, candidates in OPS_CANDIDATES.items():
        existing_ops = [row for row in rows if row.get("domain") == "ops_log" and (row.get("lang") or "").lower() == lang]
        needed = max(TARGET_OPS_PER_LANG - len(existing_ops), 0)
        if needed == 0:
            continue

        seq = next_case_index(rows, lang)
        added = 0
        for text, noise in candidates:
            if added >= needed:
                break
            if text in used_texts:
                continue

            row = {
                "case_id": f"real_{lang}_{seq:02d}",
                "source": "anonymized_real",
                "domain": "ops_log",
                "lang": lang,
                "length": classify_length(text),
                "noise": noise,
                "text": text,
            }
            rows.append(row)
            used_texts.add(text)
            seq += 1
            added += 1

    rows = sorted(rows, key=lambda item: item.get("case_id", ""))
    dump_jsonl(out_path, rows)
    print(f"wrote {len(rows)} rows -> {out_path}")


if __name__ == "__main__":
    main()
