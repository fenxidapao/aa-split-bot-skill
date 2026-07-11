#!/usr/bin/env python3
"""
aa-split-bot: 朋友聚餐 AA 算账与催款工具

功能:
  1. 解析自然语言输入的聚餐信息（或接收结构化参数）
  2. 计算每人应付金额
  3. 生成友好的催款消息
  4. 将账单以 Markdown 格式保存到 records/ 目录

用法:
  # 结构化方式（推荐 -- Agent 先用 AI 解析 NL 再调用此脚本）
  python aa-split.py --total 200 --participants 我 张三 李四 --payer 我

  # 自然语言方式（脚本自带简易正则解析，适合 demo）
  python aa-split.py "今天聚餐花了 200 块，我、张三、李四一起吃的，我付的钱"

输出:
  - 控制台打印: 解析结果、每人应付金额、催款消息
  - 文件保存: records/YYYY-MM-DD_HHMMSS.md
"""

import argparse
import datetime
import json
import os
import re
import sys
from pathlib import Path


# --- 配置 ---
RECORDS_DIR = Path(os.environ.get("AA_RECORDS_DIR", Path(__file__).parent.parent / "records"))
DATE_FORMAT = "%Y-%m-%d %H:%M"
FILE_DATE_FORMAT = "%Y-%m-%d_%H%M%S"


# --- 自然语言解析器 ---
def parse_natural(text: str) -> tuple[float, list[str], str]:
    """从自然语言文本中解析出总金额、参与人、付款人。

    注意：此解析器为简易正则版，仅支持常见表述模式。
    对于复杂表述，建议 Agent 先用 AI 解析，再通过 --total/--participants/--payer 结构化调用。
    """
    # 1) 提取金额
    amount_patterns = [
        r"(?:花(?:了|费)?|消费|总共|合计|一共|总价)(?:[：:\s]*)(\d+(?:\.\d+)?)\s*(?:块|元|钱)?",
        r"(\d+(?:\.\d+)?)\s*(?:块|元|钱)(?:\s*(?:\b|$))",
    ]
    amount = 0.0
    for pat in amount_patterns:
        m = re.search(pat, text)
        if m:
            amount = float(m.group(1))
            break

    # 额外兜底：句中任何数字+单位 / "花了{N}" / "吃了{N}" / 纯数字
    if amount == 0.0:
        m = re.search(r"(?:花了?|吃了?|共)[了]?(\d+(?:\.\d+)?)\s*(?:块|元)?", text)
        if m:
            amount = float(m.group(1))
    if amount == 0.0:
        m = re.search(r"(\d+)\s*(?:块|元)\s*", text)
        if m:
            amount = float(m.group(1))

    # 2) 提取参与人
    participants = []

    # Step A: 找明确分隔符列表 "X、Y、Z" 或 "X，Y，Z"
    # 在一句话中找到第一个被 、 或 ， 分隔的序列
    # 使用边界词限制匹配范围
    sep_match = re.search(
        r"(?:(?:我|和|与)[、，,])?([一-鿿]{2,3}[、，,][一-鿿]{2,3}(?:[、，,][一-鿿]{2,3})*)",
        text
    )
    if sep_match:
        raw = sep_match.group(1)
        parts = re.split(r"[、，,]+", raw)
        for p in parts:
            p = p.strip().lstrip("和与")
            if p and len(p) >= 1:
                participants.append(p)
        # 如果文本中有"我"但不在列表最前，插入到最前
        if "我" in text and "我" not in participants:
            participants.insert(0, "我")

    # Step B: "我和X、Y" 或 "X、Y和我"
    if not participants:
        m = re.search(r"我[和与]([一-鿿]{2,3})[、，,]([一-鿿]{2,3})", text)
        if m:
            participants = ["我", m.group(1), m.group(2)]
    if not participants:
        m = re.search(r"([一-鿿]{2,3})[、，,]([一-鿿]{2,3})[和与]我", text)
        if m:
            participants = ["我", m.group(1), m.group(2)]

    # Step C: "我和X" 或 "X和我"
    if not participants:
        m = re.search(r"我[和与]([一-鿿]{2,3})", text)
        if m:
            participants = ["我", m.group(1)]
    if not participants:
        m = re.search(r"([一-鿿]{2,3})[和与]我", text)
        if m:
            participants = ["我", m.group(1)]

    # Step D: 兜底 — 任何 2-3 字词，过滤停用词
    if not participants:
        raw_names = re.findall(r"[一-鿿]{2,3}", text)
        stop_words = {"一起", "吃的", "去的", "付钱", "付款", "请客", "买单",
                      "今天", "晚上", "中午", "大家", "朋友", "我们", "总共",
                      "合计", "消费", "一共", "块钱", "小明", "小红"}
        for n in raw_names:
            if n not in stop_words and n not in participants:
                participants.append(n)

    if "我" in text and "我" not in participants:
        participants.insert(0, "我")

    # 3) 提取付款人
    payer = ""
    payer_patterns = [
        (r"(我)[^，。]*?(?:付[了]?|请客|买单|出[了]?|付款)", 0),
        (r"([一-鿿]{2,})[^，。]*?(?:付[了]?钱|请客|买单|付款)", 0),
        (r"(?:付[了]?钱|请客|买单|付款)[^，。]*?(?:由)?([一-鿿]{2,})", 1),
        (r"([一-鿿]{2,})(?:出[的]?钱|掏[的]?钱)", 0),
    ]
    for pat, group_idx in payer_patterns:
        m = re.search(pat, text)
        if m:
            payer = m.group(group_idx + 1)
            break

    if not payer:
        payer = "我"

    # 清理：过滤不合理条目
    # 停用词表
    stop_words = {"一起", "吃的", "去的", "付钱", "付款", "请客", "买单",
                  "今天", "晚上", "中午", "大家", "朋友", "我们", "总共",
                  "合计", "消费", "一共", "块钱", "同时", "三", "两", "几",
                  "吃了", "花了", "三个", "两个", "块钱"}
    # 修剪后缀：移除常见的非名字后缀
    suffixes_to_strip = ["一", "了", "吃", "和", "与"]
    cleaned = []
    for p in participants:
        p = p.strip().lstrip("和与")
        # 修剪后缀
        for suf in suffixes_to_strip:
            if len(p) > 1 and p.endswith(suf):
                p = p[:-1]
        # 去掉"我"以外的单字
        if p and p not in stop_words and len(p) >= 1:
            cleaned.append(p)
    # 去重保留顺序
    seen = set()
    deduped = []
    for p in cleaned:
        if p not in seen:
            seen.add(p)
            deduped.append(p)
    participants = deduped

    return amount, participants, payer


# --- 计算 ---
def calculate_split(total: float, participants: list[str]) -> tuple[float, list[dict]]:
    count = len(participants)
    if count == 0:
        return 0.0, []
    per_person = round(total / count, 2)
    details = [{"name": name, "amount": per_person} for name in participants]
    return per_person, details


# --- 生成催款消息 ---
def generate_payment_reminder(
    total: float,
    per_person: float,
    participants: list[str],
    payer: str,
    date_str: str = "",
) -> str:
    if not date_str:
        date_str = datetime.datetime.now().strftime(DATE_FORMAT)

    participant_list = "、".join(participants)

    lines = [
        "--- 聚餐账单 | {} ---".format(date_str),
        "",
        "各位好，本次聚餐账单已出，请大家看一下~",
        "",
        "总金额：{:.2f} 元".format(total),
        "参与人：{}（共 {} 人）".format(participant_list, len(participants)),
        "每人应付：{:.2f} 元".format(per_person),
        "付款人：{}（已垫付，麻烦大家转给 {}）".format(payer, payer),
        "",
        "方便的话请尽快转给 {} 哦，谢谢大家！".format(payer),
        "",
    ]
    return "\n".join(lines)


# --- 保存记录 ---
def save_record(
    total: float,
    per_person: float,
    participants: list[str],
    payer: str,
    raw_input: str = "",
) -> Path:
    now = datetime.datetime.now()
    filename = now.strftime(FILE_DATE_FORMAT) + ".md"
    filepath = RECORDS_DIR / filename
    RECORDS_DIR.mkdir(parents=True, exist_ok=True)

    date_str = now.strftime(DATE_FORMAT)
    participant_list = "、".join(participants)

    content = "# 聚餐账单 | {}\n\n".format(date_str)
    content += "## 基本信息\n\n"
    content += "| 项目 | 内容 |\n"
    content += "|------|------|\n"
    content += "| 日期 | {} |\n".format(date_str)
    content += "| 总金额 | {:.2f} 元 |\n".format(total)
    content += "| 参与人 | {}（共 {} 人） |\n".format(participant_list, len(participants))
    content += "| 每人应付 | {:.2f} 元 |\n".format(per_person)
    content += "| 付款人 | {} |\n".format(payer)
    content += "\n"
    content += "## 明细\n\n"
    content += "| 姓名 | 应付金额（元） |\n"
    content += "|------|---------------|\n"
    for p in participants:
        content += "| {} | {:.2f} |\n".format(p, per_person)

    content += "\n## 催款消息\n\n```\n"
    content += generate_payment_reminder(total, per_person, participants, payer, date_str)
    content += "\n```\n"

    if raw_input:
        content += "\n## 原始输入\n\n> {}\n".format(raw_input)

    filepath.write_text(content, encoding="utf-8")
    return filepath


# --- CLI ---
def main():
    parser = argparse.ArgumentParser(
        description="AA 算账与催款助手",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  # 自然语言模式:\n"
            '  python aa-split.py "今天聚餐花了200块，我、张三、李四一起吃的，我付的钱"\n'
            "\n"
            "  # 结构化模式:\n"
            "  python aa-split.py --total 200 --participants 我 张三 李四 --payer 我\n"
        ),
    )
    parser.add_argument("text", nargs="?", help="自然语言输入的聚餐信息")
    parser.add_argument("--total", type=float, help="总金额（元）")
    parser.add_argument("--participants", nargs="+", help="参与人列表")
    parser.add_argument("--payer", type=str, help="付款人")
    parser.add_argument("--dry-run", action="store_true", help="仅输出，不保存文件")
    parser.add_argument("--records-dir", type=str, default=None, help="账单保存目录")
    parser.add_argument("--json", action="store_true", help="JSON 格式输出")

    args = parser.parse_args()

    total = args.total
    participants = args.participants
    payer = args.payer
    raw_input = ""

    if args.text:
        raw_input = args.text
        total, participants, payer = parse_natural(args.text)
        if participants:
            seen = set()
            deduped = []
            for p in participants:
                if p not in seen:
                    seen.add(p)
                    deduped.append(p)
            participants = deduped

    if total is None or total <= 0:
        print("错误: 无法解析总金额，请检查输入", file=sys.stderr)
        sys.exit(1)
    if not participants or len(participants) < 2:
        print("错误: 参与人不足 2 人，请检查输入", file=sys.stderr)
        sys.exit(1)
    if not payer:
        payer = participants[0]

    per_person, details = calculate_split(total, participants)
    now_str = datetime.datetime.now().strftime(DATE_FORMAT)
    reminder = generate_payment_reminder(total, per_person, participants, payer, now_str)

    filepath = None
    if not args.dry_run:
        if args.records_dir:
            os.environ["AA_RECORDS_DIR"] = args.records_dir
        filepath = save_record(total, per_person, participants, payer, raw_input)

    if args.json:
        output = {
            "total": total,
            "participants": participants,
            "payer": payer,
            "per_person": per_person,
            "reminder": reminder,
            "record_path": str(filepath) if filepath else None,
            "timestamp": now_str,
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        print("=" * 50)
        print("  总金额: {:.2f} 元".format(total))
        print("  参与人: {} ({} 人)".format("、".join(participants), len(participants)))
        print("  每人应付: {:.2f} 元".format(per_person))
        print("  付款人: {}".format(payer))
        print("=" * 50)
        print()
        print(reminder)
        print()
        if filepath:
            print("[记录已保存] {}".format(filepath))
        else:
            print("[DRY RUN] 未保存文件")


if __name__ == "__main__":
    main()
