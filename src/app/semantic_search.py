"""Standalone semantic-search command flow."""

from __future__ import annotations

from pathlib import Path

from src.cli_output import print_info, print_warning


def run_semantic_search_mode(args: object, query: str) -> None:
    """Run a standalone semantic search against the existing warehouse index."""
    from src.semantic_index import SemanticIndex, _run_search
    from src.warehouse import WAREHOUSE_FILENAME

    output_dir = Path(getattr(args, "output_dir", "output"))
    warehouse_path = output_dir / WAREHOUSE_FILENAME
    if not warehouse_path.exists():
        print_warning(
            f"Warehouse not found at {warehouse_path}. "
            "Run an audit with --reindex first to build the semantic index."
        )
        return

    embedder_name: str = getattr(args, "embedder", "voyage")
    idx = SemanticIndex.from_embedder_name(warehouse_path, embedder_name)
    if idx is None:
        print_warning(
            "Semantic search unavailable — embedder not configured. "
            "Set VOYAGE_API_KEY or use --embedder local."
        )
        return

    results = _run_search(idx, query, k=5)
    if not results:
        print_info("No results found in semantic index. Run --reindex first.")
        return

    print_info(f'Semantic search: "{query}"\n')
    for i, result in enumerate(results, 1):
        print_info(f"  {i}. {result.repo_name}  (distance={result.score:.4f})")
        print_info(f"     {result.snippet}")
