import argparse
import sys
from novel_pipeline.orchestrator import Orchestrator
from novel_pipeline.config import load_config
from novel_pipeline.persistence import Persistence


def main():
    parser = argparse.ArgumentParser(
        prog="novel_pipeline",
        description="自主中文小说生成 pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
子命令说明：
  run       启动或继续生成（已完成的场景自动跳过）
  status    查看当前进度（各场景状态 / 总字数）
  export    将已生成内容导出为可读文本文件
  rollback  回滚到指定 checkpoint

快速开始：
  cd ~/writing
  export DEEPSEEK_API_KEY=sk-...
  PYTHONPATH=. python -m novel_pipeline run \\
      --config config.yaml \\
      --premise "有一串螃蟹被挂到了冷清角落的路灯上" \\
      --characters 3

中途查看进度：
  PYTHONPATH=. python -m novel_pipeline status --config config.yaml

导出全稿：
  PYTHONPATH=. python -m novel_pipeline export --config config.yaml
  # 输出到 novel_draft.txt，用任意编辑器打开
        """,
    )
    sub = parser.add_subparsers(dest="command")

    run_p = sub.add_parser("run", help="启动或继续生成小说")
    run_p.add_argument("--config", default="config.yaml", help="配置文件路径（默认 config.yaml）")
    run_p.add_argument("--premise", required=True, help="故事前提，一句话描述")
    run_p.add_argument("--characters", type=int, default=4, help="角色数量（默认 4）")

    rb_p = sub.add_parser("rollback", help="回滚到指定 checkpoint")
    rb_p.add_argument("--config", default="config.yaml")
    rb_p.add_argument("--checkpoint", required=True, help="checkpoint ID（见 status 输出）")

    st_p = sub.add_parser("status", help="查看当前生成进度")
    st_p.add_argument("--config", default="config.yaml")

    ex_p = sub.add_parser("export", help="导出全稿为文本文件")
    ex_p.add_argument("--config", default="config.yaml")
    ex_p.add_argument("--out", default="novel_draft.txt", help="输出文件路径（默认 novel_draft.txt）")

    ch_p = sub.add_parser("characters", help="角色档案管理（一人一档 YAML）")
    ch_sub = ch_p.add_subparsers(dest="char_command")
    ch_list = ch_sub.add_parser("list", help="列出全部角色及其填充情况")
    ch_list.add_argument("--config", default="config.yaml")
    ch_sync = ch_sub.add_parser("sync", help="将 characters/ 目录的增删改对账进数据库")
    ch_sync.add_argument("--config", default="config.yaml")
    ch_sync.add_argument("--premise", default=None, help="可选，用于自动补全时的故事前提")
    ch_regen = ch_sub.add_parser("regen", help="重写某个角色的设计模块")
    ch_regen.add_argument("--config", default="config.yaml")
    ch_regen.add_argument("--id", required=True, help="角色 ID（见 characters list）")
    ch_regen.add_argument("--premise", default=None, help="可选，故事前提")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command in ("run", "rollback"):
        orch = Orchestrator(config_path=args.config)
        if args.command == "run":
            orch.run(premise=args.premise, num_characters=args.characters)
        else:
            orch.rollback(args.checkpoint)

    elif args.command == "status":
        import json
        cfg = load_config(args.config)
        db = Persistence(cfg.db.path)
        cp = db.get_latest_checkpoint()
        scenes = db.get_all_scenes()
        done = [s for s in scenes if db.get_manuscript(s.scene_id)]
        print(json.dumps({
            "stage": cp.stage if cp else "INIT",
            "latest_checkpoint": cp.id if cp else None,
            "scenes_total": len(scenes),
            "scenes_done": len(done),
        }, ensure_ascii=False, indent=2))

    elif args.command == "export":
        from novel_pipeline.exporter import export
        cfg = load_config(args.config)
        export(db_path=cfg.db.path, out_path=args.out)

    elif args.command == "characters":
        import json
        if not args.char_command:
            ch_p.print_help()
            sys.exit(1)
        orch = Orchestrator(config_path=args.config)
        if args.char_command == "list":
            print(json.dumps(orch.characters_list(), ensure_ascii=False, indent=2))
        elif args.char_command == "sync":
            report = orch.characters_sync(premise=args.premise)
            print(json.dumps(report.__dict__, ensure_ascii=False, indent=2))
            for w in report.warnings:
                print(f"[警告] {w}")
        elif args.char_command == "regen":
            char = orch.characters_regen(args.id, premise=args.premise)
            print(json.dumps(char.model_dump(exclude_none=True), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
