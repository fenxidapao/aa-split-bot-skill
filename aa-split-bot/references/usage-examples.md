# aa-split-bot 使用示例

## 示例 1：简单三人聚餐（结构化方式）

Agent 收到用户输入后，先用 AI 解析出结构化数据，然后调用脚本：

```bash
python scripts/aa-split.py --total 200 --participants 我 张三 李四 --payer 我
```

输出：
```
==================================================
  总金额: 200.00 元
  参与人: 我、张三、李四 (3 人)
  每人应付: 66.67 元
  付款人: 我
==================================================

--- 聚餐账单 | 2026-07-11 14:30 ---

各位好，本次聚餐账单已出，请大家看一下~

总金额：200.00 元
参与人：我、张三、李四（共 3 人）
每人应付：66.67 元
付款人：我（已垫付，麻烦大家转给我）

方便的话请尽快转给我哦，谢谢大家！

[记录已保存] ...\\records\\2026-07-11_143000.md
```

---

## 示例 2：自然语言模式（脚本自带解析）

```bash
python scripts/aa-split.py "今天聚餐花了 200 块，我、张三、李四一起吃的，我付的钱"
```

输出结果同上。

---

## 示例 3：四人聚餐，别人请客

```bash
python scripts/aa-split.py --total 360 --participants 我 张三 李四 王五 --payer 张三
```

输出：
```
每人应付: 90.00 元
付款人：张三（已垫付，麻烦大家转给张三）
```

---

## 示例 4：JSON 模式（供其他工具链调用）

```bash
python scripts/aa-split.py --total 200 --participants 我 张三 李四 --payer 我 --json
```

输出：
```json
{
  "total": 200.0,
  "participants": ["我", "张三", "李四"],
  "payer": "我",
  "per_person": 66.67,
  "reminder": "...",
  "record_path": "...",
  "timestamp": "2026-07-11 14:30"
}
```

---

## 示例 5：Dry Run（不保存文件）

```bash
python scripts/aa-split.py --total 180 --participants 我 小红 小明 --payer 小红 --dry-run
```

只打印结果，不写文件。
