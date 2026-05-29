"""
Synchronize product master data after editing 01_PRODUCT_MASTER_BASE.csv.

This script treats 01_PRODUCT_MASTER_BASE.csv as the source of truth for
product names, stock fields, categories, descriptions, dimensions, and weight.
It can:

1. Validate the CSV structure and common data issues.
2. Sync CSV rows into 03_PRODUCT_INFO.json while preserving supplemental fields
   such as Sales Price, Quantity On Hand, and Introduction Video URL.
3. Optionally rebuild a Chroma product vector store from the latest CSV rows.

Typical usage:
    python update_product_data.py

Useful options:
    python update_product_data.py --dry-run
    python update_product_data.py --rebuild-vector
    python update_product_data.py --prune-json
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any


PRODUCT_CSV = Path("01_PRODUCT_MASTER_BASE.csv")
PRODUCT_JSON = Path("03_PRODUCT_INFO.json")
VECTOR_DIR = Path("chroma_db") / "product_vectors"
COLLECTION_NAME = "erent_products"
EMBEDDING_MODEL = "BAAI/bge-m3"
MODEL_CACHE_DIR = Path("model_cache")

REQUIRED_COLUMNS = [
    "product_name",
    "stock_status",
    "in_stock",
    "description",
    "net_weight",
    "dimension_height",
    "dimension_length",
    "dimension_width",
    "category_name",
    "category_id",
]

REQUIRED_NON_EMPTY = ["product_name", "category_name", "category_id"]
VALID_STOCK_STATUS = {"", "available", "unavailable"}
VALID_IN_STOCK = {"", "true", "false"}


def normalize_name(text: str) -> str:
    text = (text or "").strip().lower()
    replacements = {
        "（": "(",
        "）": ")",
        "-": "",
        "_": "",
        "，": "",
        ",": "",
        " ": "",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return "".join(text.split())


def read_csv_rows(csv_path: Path) -> list[dict[str, str]]:
    if not csv_path.exists():
        raise FileNotFoundError(f"找不到产品主数据文件: {csv_path}")

    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError(f"{csv_path} 没有表头")

        missing = [col for col in REQUIRED_COLUMNS if col not in reader.fieldnames]
        if missing:
            raise ValueError(
                f"{csv_path} 缺少必要字段: {', '.join(missing)}\n"
                f"当前字段: {', '.join(reader.fieldnames)}"
            )

        return [{col: (row.get(col) or "").strip() for col in REQUIRED_COLUMNS} for row in reader]


def is_number_or_blank(value: str) -> bool:
    if value == "":
        return True
    try:
        float(value)
        return True
    except ValueError:
        return False


def validate_rows(rows: list[dict[str, str]]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    seen_names: dict[str, int] = {}

    for idx, row in enumerate(rows, start=2):
        for col in REQUIRED_NON_EMPTY:
            if not row.get(col):
                errors.append(f"第 {idx} 行缺少必要字段 {col}")

        name_key = normalize_name(row.get("product_name", ""))
        if name_key:
            if name_key in seen_names:
                warnings.append(
                    f"第 {idx} 行产品名称与第 {seen_names[name_key]} 行重复: {row.get('product_name')}"
                )
            else:
                seen_names[name_key] = idx

        stock_status = row.get("stock_status", "").lower()
        if stock_status not in VALID_STOCK_STATUS:
            warnings.append(
                f"第 {idx} 行 stock_status 建议使用 available/unavailable: {row.get('stock_status')}"
            )

        in_stock = row.get("in_stock", "").lower()
        if in_stock not in VALID_IN_STOCK:
            warnings.append(
                f"第 {idx} 行 in_stock 建议使用 True/False: {row.get('in_stock')}"
            )

        for col in ["net_weight", "dimension_height", "dimension_length", "dimension_width"]:
            if not is_number_or_blank(row.get(col, "")):
                warnings.append(f"第 {idx} 行 {col} 建议填写数字或留空: {row.get(col)}")

    return errors, warnings


def backup_file(path: Path, backup_dir: Path) -> Path | None:
    if not path.exists():
        return None
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"{path.stem}_{timestamp}{path.suffix}"
    shutil.copy2(path, backup_path)
    return backup_path


def load_product_json(json_path: Path) -> list[dict[str, Any]]:
    if not json_path.exists():
        return []
    with json_path.open("r", encoding="utf-8-sig") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"{json_path} 顶层结构应为 JSON 数组")
    return [item for item in data if isinstance(item, dict)]


def to_number_or_none(value: str) -> float | None:
    if value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def strip_html(text: str) -> str:
    if not text:
        return ""
    cleaned = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"</p>|</li>|</h\d>", "\n", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"<[^>]+>", "", cleaned)
    cleaned = html.unescape(cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def sync_detail_from_row(
    detail: dict[str, Any],
    row: dict[str, str],
    *,
    overwrite_commerce_description: bool = False,
) -> dict[str, Any]:
    synced = dict(detail)

    synced["Name"] = row["product_name"]
    synced["Product/Description"] = row.get("description") or synced.get("Product/Description")
    synced["Category Name"] = row.get("category_name", "")
    synced["Category ID"] = row.get("category_id", "")
    synced["Stock Status"] = row.get("stock_status", "")
    synced["In Stock"] = row.get("in_stock", "")

    if overwrite_commerce_description and row.get("description"):
        synced["eCommerce Description"] = row["description"]
    else:
        synced.setdefault("eCommerce Description", None)

    for csv_col, json_col in [
        ("net_weight", "Net Weight"),
        ("dimension_height", "Dimension Height"),
        ("dimension_length", "Dimension Length"),
        ("dimension_width", "Dimension Width"),
    ]:
        number = to_number_or_none(row.get(csv_col, ""))
        if number is not None:
            synced[json_col] = number
        else:
            synced.setdefault(json_col, None)

    synced.setdefault("Sales Price", None)
    synced.setdefault("Quantity On Hand", None)
    synced.setdefault("Hashtags/Hashtag Name", None)
    synced.setdefault("Product/All Product Tag", row.get("category_name") or None)
    synced.setdefault("Introduction Video URL", None)

    return synced


def sync_product_json(
    rows: list[dict[str, str]],
    json_path: Path,
    *,
    prune_json: bool = False,
    overwrite_commerce_description: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    existing = load_product_json(json_path)

    existing_by_name: dict[str, dict[str, Any]] = {}
    duplicate_existing = 0
    for item in existing:
        key = normalize_name(str(item.get("Name", "")))
        if not key:
            continue
        if key in existing_by_name:
            duplicate_existing += 1
            continue
        existing_by_name[key] = item

    used_keys: set[str] = set()
    synced: list[dict[str, Any]] = []
    created = 0
    updated = 0

    for row in rows:
        key = normalize_name(row["product_name"])
        detail = existing_by_name.get(key, {})
        if detail:
            updated += 1
            used_keys.add(key)
        else:
            created += 1
        synced.append(
            sync_detail_from_row(
                detail,
                row,
                overwrite_commerce_description=overwrite_commerce_description,
            )
        )

    kept_extra = 0
    if not prune_json:
        for item in existing:
            key = normalize_name(str(item.get("Name", "")))
            if key and key in used_keys:
                continue
            synced.append(item)
            kept_extra += 1

    stats = {
        "csv_rows": len(rows),
        "existing_json_rows": len(existing),
        "json_updated_from_csv": updated,
        "json_created_from_csv": created,
        "json_extra_kept": kept_extra,
        "json_duplicate_existing_ignored": duplicate_existing,
        "json_output_rows": len(synced),
    }
    return synced, stats


def write_product_json(json_path: Path, data: list[dict[str, Any]]) -> None:
    with json_path.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def product_document_text(row: dict[str, str]) -> str:
    dimensions = " x ".join(
        part
        for part in [
            row.get("dimension_length", ""),
            row.get("dimension_width", ""),
            row.get("dimension_height", ""),
        ]
        if part
    )
    if not dimensions:
        dimensions = "暂无尺寸"

    return "\n".join(
        [
            f"产品名称: {row.get('product_name', '')}",
            f"所属分类: {row.get('category_name', '')}",
            f"分类编号: {row.get('category_id', '')}",
            f"库存状态: {row.get('stock_status', '')}",
            f"是否有货: {row.get('in_stock', '')}",
            f"净重: {row.get('net_weight', '')}",
            f"尺寸: {dimensions}",
            f"产品描述: {strip_html(row.get('description', ''))}",
        ]
    )


def rebuild_product_vectorstore(
    rows: list[dict[str, str]],
    vector_dir: Path,
    *,
    collection_name: str = COLLECTION_NAME,
    model_name: str = EMBEDDING_MODEL,
    cache_dir: Path = MODEL_CACHE_DIR,
) -> dict[str, Any]:
    try:
        from langchain_chroma import Chroma
        from langchain_core.documents import Document
        from langchain_huggingface import HuggingFaceEmbeddings
    except ImportError as exc:
        raise RuntimeError(
            "当前 Python 环境缺少产品向量库依赖。请在安装 langchain_chroma、"
            "langchain_core、langchain_huggingface 后重新运行。日常只同步 JSON 时，"
            "不要使用 --rebuild-vector。"
        ) from exc

    documents = []
    for row in rows:
        metadata = {
            "source": "01_PRODUCT_MASTER_BASE",
            "product_name": row.get("product_name", ""),
            "category_name": row.get("category_name", ""),
            "category_id": row.get("category_id", ""),
            "stock_status": row.get("stock_status", ""),
            "in_stock": row.get("in_stock", ""),
        }
        documents.append(Document(page_content=product_document_text(row), metadata=metadata))

    if vector_dir.exists():
        shutil.rmtree(vector_dir)
    vector_dir.mkdir(parents=True, exist_ok=True)

    embeddings = HuggingFaceEmbeddings(
        model_name=model_name,
        cache_folder=str(cache_dir),
    )
    vectorstore = Chroma.from_documents(
        documents=documents,
        embedding=embeddings,
        persist_directory=str(vector_dir),
        collection_name=collection_name,
    )
    if hasattr(vectorstore, "persist"):
        vectorstore.persist()

    return {
        "documents": len(documents),
        "vector_dir": str(vector_dir),
        "collection_name": collection_name,
        "embedding_model": model_name,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="同步产品 CSV 到 03_PRODUCT_INFO.json")
    parser.add_argument("--csv", type=Path, default=PRODUCT_CSV, help="产品主数据 CSV 路径")
    parser.add_argument("--json", type=Path, default=PRODUCT_JSON, help="产品详情 JSON 路径")
    parser.add_argument("--vector-dir", type=Path, default=VECTOR_DIR, help="产品向量库目录")
    parser.add_argument("--collection-name", default=COLLECTION_NAME, help="Chroma collection 名称")
    parser.add_argument("--model-name", default=EMBEDDING_MODEL, help="Embedding 模型名称")
    parser.add_argument("--cache-dir", type=Path, default=MODEL_CACHE_DIR, help="Embedding 模型缓存目录")
    parser.add_argument("--backup-dir", type=Path, default=Path("backups"), help="备份目录")
    parser.add_argument("--dry-run", action="store_true", help="只检查和预览，不写入文件")
    parser.add_argument("--skip-json", action="store_true", help="跳过 JSON 同步")
    parser.add_argument(
        "--rebuild-vector",
        action="store_true",
        help="同步 JSON 后额外重建产品向量库。默认不执行，避免下载 embedding 模型。",
    )
    parser.add_argument("--prune-json", action="store_true", help="移除 JSON 中不在 CSV 内的旧产品")
    parser.add_argument("--no-backup", action="store_true", help="写入前不备份旧 JSON/向量库")
    parser.add_argument(
        "--overwrite-commerce-description",
        action="store_true",
        help="用 CSV description 覆盖 JSON 的 eCommerce Description",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    rows = read_csv_rows(args.csv)
    errors, warnings = validate_rows(rows)

    print("=== 产品数据同步检查 ===")
    print(f"CSV 文件: {args.csv}")
    print(f"产品行数: {len(rows)}")

    if warnings:
        print("\n警告:")
        for msg in warnings[:30]:
            print(f"- {msg}")
        if len(warnings) > 30:
            print(f"- 还有 {len(warnings) - 30} 条警告未显示")

    if errors:
        print("\n错误:")
        for msg in errors:
            print(f"- {msg}")
        print("\n存在必要字段错误，已停止同步。")
        return 1

    if not args.skip_json:
        synced_json, stats = sync_product_json(
            rows,
            args.json,
            prune_json=args.prune_json,
            overwrite_commerce_description=args.overwrite_commerce_description,
        )
        print("\n=== JSON 同步预览 ===")
        for key, value in stats.items():
            print(f"{key}: {value}")

        if not args.dry_run:
            if not args.no_backup:
                backup_path = backup_file(args.json, args.backup_dir)
                if backup_path:
                    print(f"已备份旧 JSON: {backup_path}")
            write_product_json(args.json, synced_json)
            print(f"已写入 JSON: {args.json}")
    else:
        print("\n已跳过 JSON 同步。")

    if args.rebuild_vector:
        print("\n=== 产品向量库重建 ===")
        if args.dry_run:
            print(f"dry-run: 将重建 {args.vector_dir}，文档数 {len(rows)}")
        else:
            if args.vector_dir.exists() and not args.no_backup:
                backup_path = args.backup_dir / f"{args.vector_dir.name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                backup_path.parent.mkdir(parents=True, exist_ok=True)
                if backup_path.exists():
                    shutil.rmtree(backup_path)
                shutil.copytree(args.vector_dir, backup_path)
                print(f"已备份旧向量库: {backup_path}")

            try:
                vector_stats = rebuild_product_vectorstore(
                    rows,
                    args.vector_dir,
                    collection_name=args.collection_name,
                    model_name=args.model_name,
                    cache_dir=args.cache_dir,
                )
            except RuntimeError as exc:
                print(f"向量库未重建: {exc}")
                return 2
            print(f"已重建产品向量库: {vector_stats}")
    else:
        print("\n已跳过产品向量库重建。如确实需要重建，请使用 --rebuild-vector。")

    print("\n同步流程完成。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
