#!/usr/bin/env python3
"""导出小说全稿为可读文本文件。"""
import sqlite3
import json
import argparse
from pathlib import Path
from datetime import datetime


def export(db_path: str, out_path: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    lines = []

    # 世界观
    wb = conn.execute("SELECT * FROM world_bible WHERE id=1").fetchone()
    if wb:
        lines += ["=" * 60, "【世界观】", "=" * 60, ""]
        lines.append(wb["setting"])
        lines.append("")
        rules = json.loads(wb["rules"])
        if rules:
            lines.append("规则：")
            for r in rules:
                lines.append(f"  · {r}")
        lines.append("")

    # 角色表
    chars = conn.execute("SELECT * FROM characters").fetchall()
    if chars:
        lines += ["=" * 60, "【角色】", "=" * 60, ""]
        for c in chars:
            lines.append(f"▶ {c['name']}（{c['id']}）")
            lines.append(f"  性格：{c['persona']}")
            lines.append(f"  语气：{c['voice']}")
            lines.append(f"  弧线：{c['arc']}")
            lines.append("")

    # 章节与场景正文
    chapters = conn.execute("SELECT * FROM chapters ORDER BY order_idx").fetchall()
    total_words = 0

    for ch in chapters:
        lines += ["=" * 60, f"【{ch['id']}】目标：{ch['goal']}", f"地点：{ch['location']}", "=" * 60, ""]

        scenes = conn.execute(
            "SELECT s.scene_id, s.location, s.pov, s.order_idx, m.prose, m.word_count "
            "FROM scenes s LEFT JOIN manuscripts m ON s.scene_id = m.scene_id "
            "WHERE s.chapter_id=? ORDER BY s.order_idx",
            (ch["id"],),
        ).fetchall()

        for sc in scenes:
            pov_tag = f"  视角：{sc['pov']}" if sc["pov"] else ""
            lines.append(f"── 场景 {sc['scene_id']} | 地点：{sc['location']}{pov_tag}")
            if sc["prose"]:
                lines.append("")
                lines.append(sc["prose"])
                total_words += sc["word_count"] or 0
            else:
                lines.append("  （未生成）")
            lines.append("")

    # 页脚
    lines += [
        "=" * 60,
        f"导出时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"已完成场景字数合计：约 {total_words} 字",
        "=" * 60,
    ]

    Path(out_path).write_text("\n".join(lines), encoding="utf-8")
    print(f"已导出 → {out_path}（{total_words} 字）")
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="导出小说全稿")
    parser.add_argument("--db", default="novel.db", help="数据库路径")
    parser.add_argument("--out", default="novel_draft.txt", help="输出文件路径")
    args = parser.parse_args()
    export(args.db, args.out)
