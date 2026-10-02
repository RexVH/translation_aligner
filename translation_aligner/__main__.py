"""Headless intake and synthetic API diagnostics."""
import argparse
import json
import os
from dataclasses import asdict
from pathlib import Path

from .intake import extract_body, pair_files
from .systran import probe, SystranError
from .models import MODELS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    intake = commands.add_parser("inspect", help="Pair DOCX files and count body paragraphs without API calls")
    intake.add_argument("folder", type=Path)
    test = commands.add_parser("probe", help="Translate synthetic text using SYSTRAN_API_KEY")
    test.add_argument("--base-url", default=os.getenv("SYSTRAN_BASE_URL", "https://api-translate.systran.net"))
    test.add_argument("--output", type=Path, default=Path("local_data/probes/systran.json"))
    alignment = commands.add_parser('align', help='Align filename-paired DOCX files and save provenance')
    alignment.add_argument('folder', type=Path)
    alignment.add_argument('--backend', choices=['vecalign','portable_dp'], default='vecalign')
    alignment.add_argument('--model', choices=list(MODELS), default='minilm')
    alignment.add_argument('--base-url', default=os.getenv('SYSTRAN_BASE_URL','https://api-translate.systran.net'))
    export=commands.add_parser('export',help='Export a saved alignment and update the versioned master')
    export.add_argument('alignment_file',type=Path)
    args = parser.parse_args()
    try:
        if args.command == 'export':
            from .exports import export_run
            saved=json.loads(args.alignment_file.read_text(encoding='utf-8'))
            print(json.dumps(export_run(saved),ensure_ascii=False,indent=2))
        elif args.command == "probe":
            result = probe(os.getenv("SYSTRAN_API_KEY", ""), args.base_url)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("x", encoding="utf-8") as handle:
                json.dump(result, handle, ensure_ascii=False, indent=2)
            print(f"Synthetic response saved: {args.output}")
        else:
            if not args.folder.is_dir():
                parser.error("Input folder does not exist.")
            pairs, problems = pair_files([p.name for p in args.folder.iterdir() if p.suffix.lower() == ".docx"])
            if args.command == 'align':
                if problems or not pairs:
                    parser.error('; '.join(problems) or 'No document pairs found.')
                from .semantic import SemanticAligner
                from .pipeline import run_pair
                semantic = SemanticAligner(args.backend,model_key=args.model)
                for pair in pairs:
                    _, path = run_pair(pair,(args.folder/pair.source).read_bytes(),(args.folder/pair.target).read_bytes(),
                                       os.getenv('SYSTRAN_API_KEY',''),args.base_url,semantic,
                                       progress=lambda p,t: print(f'{p:.0%} {t}'))
                    print(f'Saved: {path}')
                return
            records = []
            for pair in pairs:
                record = asdict(pair)
                record["source_paragraphs"] = len(extract_body((args.folder / pair.source).read_bytes()))
                record["target_paragraphs"] = len(extract_body((args.folder / pair.target).read_bytes()))
                records.append(record)
            print(json.dumps({"pairs": records, "problems": problems}, ensure_ascii=False, indent=2))
            if problems:
                raise SystemExit(1)
    except (SystranError, ValueError, OSError, RuntimeError) as exc:
        parser.exit(1, f"{exc}\n")


if __name__ == "__main__":
    main()
